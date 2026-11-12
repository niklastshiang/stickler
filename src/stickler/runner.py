"""Benchmark matrix: dataset × separator × transcriber, with a content-based cache.

Built-in separators:
- `none`: the original mix goes straight into the transcriber
- `oracle`: the dataset's isolated drum stem (upper bound for perfect separation)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from stickler import adapters
from stickler.audio import duration as audio_duration
from stickler.classes import Scheme, onsets_from_notes
from stickler.evaluate import PRF, score
from stickler.midi import read_drum_notes

log = logging.getLogger(__name__)

BUILTIN_SEPARATORS = ("none", "oracle")


@dataclass(frozen=True)
class RelativeLimit:
    """Time limit relative to the input length: factor × duration, at least `minimum` seconds.
    Fair for slow models on long songs, yet still stops outliers."""

    factor: float
    minimum: float = 0.0

    def seconds(self, duration: float) -> float:
        return max(self.minimum, self.factor * duration)


# Time limit: one number (seconds) for all stages or per stage {"separators": ..., ...},
# per stage also relative to the audio duration
Timeout = float | dict[str, float | RelativeLimit] | None


def _stage_timeout(timeout: Timeout, stage: str, audio_in: Path) -> float | None:
    limit = timeout.get(stage) if isinstance(timeout, dict) else timeout
    if isinstance(limit, RelativeLimit):
        return limit.seconds(audio_duration(audio_in))
    return limit


Progress = Callable[[int, int, str], None]


class Track(Protocol):
    id: str
    mix: Path
    drums: Path | None
    excluded: tuple[tuple[float, float], ...]  # audio-time intervals without scoring

    def reference_notes(self) -> list[tuple[float, int]]: ...


@dataclass(frozen=True)
class Record:
    dataset: str
    track: str
    separator: str
    transcriber: str
    stem: Path | None
    midi: Path | None
    separator_meta: dict | None
    transcriber_meta: dict | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


def _sha1_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha1").hexdigest()


def _adapter_digest(spec: adapters.AdapterSpec) -> str:
    h = hashlib.sha1()
    for name in ("run.py", "pyproject.toml", "setup.py"):
        p = spec.path / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def cache_dir_for(cache: Path, spec: adapters.AdapterSpec, audio: Path, device: str) -> Path:
    """Cache folder: depends on the input content, the adapter code, the device and the
    environment (cpu/rocm), because GPU and CPU results can differ slightly."""
    variant = (
        adapters.env_variant(spec, device) or "fehlt"
    )  # German literal kept: it is part of the cache key
    env = device if variant == "cpu" else f"{device}|{variant}"  # CPU key as before
    key = hashlib.sha1(
        f"{_sha1_file(audio)}|{spec.id}|{_adapter_digest(spec)}|{env}".encode()
    ).hexdigest()[:16]
    return cache / spec.id / key


def cached_or_run(
    spec: adapters.AdapterSpec,
    audio: Path,
    cache: Path,
    device: str,
    execute: bool,
    timeout: Timeout = None,
) -> adapters.AdapterResult:
    out_dir = cache_dir_for(cache, spec, audio, device)
    output, meta = out_dir / spec.expected_output, out_dir / "meta.json"
    if output.exists() and meta.exists():
        return adapters.AdapterResult(True, output, json.loads(meta.read_text()), None)
    if not execute:
        return adapters.AdapterResult(False, None, None, f"{spec.id}: not computed")
    try:
        limit = _stage_timeout(timeout, spec.stage, audio)
    except RuntimeError as exc:
        return adapters.AdapterResult(False, None, None, f"{spec.id}: {exc}")
    return adapters.run_adapter(spec, audio, out_dir, device=device, timeout=limit)


def _separate(
    track: Track,
    separator: str,
    registry: dict[str, adapters.AdapterSpec],
    cache: Path,
    device: str,
    execute: bool,
    timeout: Timeout,
) -> adapters.AdapterResult:
    if separator == "none":
        return adapters.AdapterResult(True, track.mix, None, None)
    if separator == "oracle":
        if track.drums is None or not track.drums.exists():
            return adapters.AdapterResult(False, None, None, "oracle: dataset has no stem")
        return adapters.AdapterResult(True, track.drums, None, None)
    return cached_or_run(registry[separator], track.mix, cache, device, execute, timeout)


def _check_ids(ids: list[str], stage: str, registry: dict[str, adapters.AdapterSpec]) -> None:
    builtin = BUILTIN_SEPARATORS if stage == "separators" else ()
    for i in ids:
        if i not in builtin and (i not in registry or registry[i].stage != stage):
            raise ValueError(f"{stage}: adapter {i!r} unknown")


def run_matrix(
    tracks: dict[str, list[Track]],
    separators: list[str],
    transcribers: list[str],
    registry: dict[str, adapters.AdapterSpec],
    cache: Path,
    device: str = "auto",
    execute: bool = True,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
    timeout: Timeout = None,
) -> list[Record]:
    """Computes (or reads from the cache) all combinations; errors end up in the Record.

    Transcribers that only accept drum stems (input="stem") do not run on `none`.
    `timeout` limits each single adapter call (seconds, overall or per stage)."""
    _check_ids(separators, "separators", registry)
    _check_ids(transcribers, "transcribers", registry)
    jobs = [
        (ds, t, sep, tr)
        for ds, ts in tracks.items()
        for t in ts
        for sep in separators
        for tr in transcribers
        if not (sep == "none" and registry[tr].needs_stem)
    ]
    records: list[Record] = []
    for n, (ds, track, sep, tr) in enumerate(jobs, start=1):
        if cancel is not None and cancel.is_set():
            break
        stem = _separate(track, sep, registry, cache, device, execute, timeout)
        if stem.ok:
            trans = cached_or_run(registry[tr], stem.output, cache, device, execute, timeout)
            error = trans.error
        else:
            trans, error = None, stem.error
        records.append(
            Record(
                dataset=ds,
                track=track.id,
                separator=sep,
                transcriber=tr,
                stem=stem.output,
                midi=trans.output if trans and trans.ok else None,
                separator_meta=stem.meta,
                transcriber_meta=trans.meta if trans else None,
                error=error,
            )
        )
        if progress is not None:
            progress(n, len(jobs), f"{ds}/{track.id}: {sep} → {tr}")
    return records


def _row(base: dict, scheme: str, cls: str, prf: PRF | None, f1: float | None = None) -> dict:
    counts = {"tp": prf.tp, "fp": prf.fp, "fn": prf.fn} if prf else {"tp": 0, "fp": 0, "fn": 0}
    return {
        **base,
        "scheme": scheme,
        "class": cls,
        **counts,
        "precision": prf.precision if prf else 0.0,
        "recall": prf.recall if prf else 0.0,
        "f1": f1 if f1 is not None else (prf.f1 if prf else 0.0),
    }


def _outside(notes: list[tuple[float, int]], excluded) -> list[tuple[float, int]]:
    return [(t, p) for t, p in notes if not any(a <= t < b for a, b in excluded)]


def score_records(
    records: list[Record],
    tracks: dict[str, list[Track]],
    schemes: dict[str, Scheme],
    read_notes: Callable[[Path], list[tuple[float, int]]] = read_drum_notes,
) -> list[dict]:
    """One row per record × scheme × class (plus 'micro'/'macro'); errors as their own rows.
    Notes in excluded regions of the track count neither as hits nor as errors."""
    by_id = {(ds, t.id): t for ds, ts in tracks.items() for t in ts}
    rows: list[dict] = []
    for rec in records:
        base = {
            "dataset": rec.dataset,
            "track": rec.track,
            "separator": rec.separator,
            "transcriber": rec.transcriber,
            "device": (rec.transcriber_meta or {}).get("device", ""),
            "sep_seconds": (rec.separator_meta or {}).get("seconds", 0.0),
            "trans_seconds": (rec.transcriber_meta or {}).get("seconds", 0.0),
            "error": rec.error or "",
        }
        if not rec.ok:
            rows.extend(_row(base, name, "", None) for name in schemes)
            continue
        track = by_id[(rec.dataset, rec.track)]
        ref_notes = _outside(track.reference_notes(), track.excluded)
        est_notes = _outside(read_notes(rec.midi), track.excluded)
        for name, scheme in schemes.items():
            s = score(onsets_from_notes(ref_notes, scheme), onsets_from_notes(est_notes, scheme))
            for cls, prf in [*s.per_class.items(), ("micro", s.micro)]:
                rows.append(_row(base, name, cls, prf))
            rows.append(_row(base, name, "macro", None, f1=s.macro_f1))
    return rows
