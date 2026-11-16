"""Benchmark matrix: dataset × separator × transcriber, with a content-based cache.

Built-in separators:
- `none`: the original mix goes straight into the transcriber
- `oracle`: the dataset's isolated drum stem (upper bound for perfect separation)
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import logging
import sys
import threading
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Protocol

import yaml

from stickler import adapters
from stickler import audio as audio_mod
from stickler.audio import duration as audio_duration
from stickler.classes import Scheme, onsets_from_notes
from stickler.evaluate import PRF, score
from stickler.midi import read_drum_notes

log = logging.getLogger(__name__)

BUILTIN_SEPARATORS = ("none", "oracle")
CACHE_KEY_VERSION = "v2"  # v1: raw file bytes and the device were part of the key


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
    # Notes already in memory (combined pipelines); otherwise they are read from `midi`
    notes: tuple[tuple[float, int], ...] | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _sha1_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha1").hexdigest()


# Python 3.13 stopped printing empty fields in ast.dump; show_empty=True gives 3.12's output, so a
# harness on 3.13 or 3.14 (the GTK app) computes the same cache keys as one on 3.12.
_DUMP_AS_312 = {"show_empty": True} if sys.version_info >= (3, 13) else {}


def _canonical(path: Path) -> bytes:
    """What defines an adapter's behaviour: Python as syntax tree without docstrings (comments
    are not part of it), TOML (pyproject.toml, uv.lock) as parsed data. Comments and
    translations do not change it."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        tree = ast.parse(text)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (
                isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
        return ast.dump(tree, **_DUMP_AS_312).encode()
    if path.suffix == ".toml" or path.name == "uv.lock":
        return json.dumps(tomllib.loads(text), sort_keys=True).encode()
    return text.strip().encode()


# Since 2026-11-16 (Task 87). Snapshots of digests (cachemigration) record it, so a snapshot of
# another definition is never used to rekey.
DIGEST_DEFINITION = 2
SKIPPED_PARTS = {"__pycache__", ".venv", "weights", "build"}


def _common_dir(spec: adapters.AdapterSpec) -> Path | None:
    """The shared adapter package (adapters/_common) as the adapter's pyproject.toml names it."""
    pyproject = spec.path / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    source = data.get("tool", {}).get("uv", {}).get("sources", {}).get("stickler-adapter")
    entries = source if isinstance(source, list) else [source]
    path = next((e["path"] for e in entries if isinstance(e, dict) and "path" in e), None)
    folder = (spec.path / path).resolve() if path else None
    return folder if folder and folder.is_dir() else None


def _local_modules(folder: Path, entry_points: list[Path]) -> list[Path]:
    """The adapter's own modules that its entry points import, directly or through each
    other. A stray file nothing imports (a scratch script) does not count."""
    seen: dict[str, Path] = {}
    todo = [p for p in entry_points if p.exists()]
    while todo:
        tree = ast.parse(todo.pop().read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module.split(".")[0]]
            for name in names:
                module = folder / f"{name}.py"
                if name not in seen and module.is_file() and module not in entry_points:
                    seen[name] = module
                    todo.append(module)
    return [seen[n] for n in sorted(seen)]


def _behaviour_files(spec: adapters.AdapterSpec) -> list[tuple[str, Path]]:
    """Every file that defines what the adapter computes (since 2026-11-16; before, only
    run.py, pyproject.toml and setup.py counted, so a changed helper kept old results valid):
    the entry points and the modules they import, pyproject.toml, uv.lock and .python-version
    (the model's and its libraries' versions), and the shared adapter package. Names are
    relative, so the digest is the same wherever the adapters live."""
    entry = [spec.path / "run.py", spec.path / "setup.py"]
    files = [(name, spec.path / name) for name in ("run.py", "pyproject.toml", "setup.py")]
    files += [(p.name, p) for p in _local_modules(spec.path, entry)]
    files += [(name, spec.path / name) for name in ("uv.lock", ".python-version")]
    common = _common_dir(spec)
    if common:
        files += [
            (f"_common/{rel.as_posix()}", p)
            for p in sorted(common.rglob("*.py"))
            for rel in [p.relative_to(common)]
            if not SKIPPED_PARTS.intersection(rel.parts)
        ]
        files.append(("_common/pyproject.toml", common / "pyproject.toml"))
    return [(name, p) for name, p in files if p.is_file()]


def code_digest(spec: adapters.AdapterSpec) -> str:
    h = hashlib.sha1()
    for name, p in _behaviour_files(spec):
        h.update(name.encode() + b"\0" + _canonical(p) + b"\0")
    return h.hexdigest()


EQUIVALENTS = Path(__file__).with_name("digests.yaml")


@cache
def load_equivalents(path: Path = EQUIVALENTS) -> dict[str, tuple[tuple[str, str], ...]]:
    """Adapter id → (earlier digest, later digest) pairs whose results are the same."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return {
        str(spec_id): tuple((str(p["from"]), str(p["to"])) for p in pairs)
        for spec_id, pairs in ((raw or {}).get("equivalent") or {}).items()
    }


def equivalent_digests(spec: adapters.AdapterSpec) -> tuple[str, ...]:
    """Earlier digests whose results equal the current code's: those with a chain of pairs
    that ends at the current digest. After a real change the chain no longer reaches it, so
    nothing earlier counts any more."""
    pairs = load_equivalents().get(spec.id, ())
    reached, found = {code_digest(spec)}, []
    changed = True
    while changed:
        changed = False
        for old, new in pairs:
            if new in reached and old not in reached:
                reached.add(old)
                found.append(old)
                changed = True
    return tuple(found)


def cache_dir_for(cache: Path, spec: adapters.AdapterSpec, audio: Path) -> Path:
    """Cache folder: depends only on the input content and the adapter's code (ignoring
    comments and docstrings). The device is recorded in meta.json, not in the key, so results
    computed on a rented GPU count as cache hits on the laptop (decided 2026-11-12).

    If there is no folder under the current key but one under an equivalent earlier digest
    (digests.yaml), that folder is renamed to the current key: results survive edits that do
    not change behaviour, in the benchmark and in the app, without a migration step."""
    sha = _sha1_file(audio)
    current = cache / spec.id / cache_key(spec, sha)
    if not current.exists():
        for digest in equivalent_digests(spec):
            earlier = cache / spec.id / cache_key(spec, sha, digest)
            if earlier.is_dir():
                with contextlib.suppress(OSError):  # another process renamed it first
                    earlier.rename(current)
                break
    return current


def cache_key(spec: adapters.AdapterSpec, audio_sha1: str, digest: str | None = None) -> str:
    """Folder name for an input with the given SHA-1 (see cache_dir_for); `digest` overrides
    the adapter's current code digest (used to find entries made before a cosmetic edit)."""
    text = f"{CACHE_KEY_VERSION}|{audio_sha1}|{spec.id}|{digest or code_digest(spec)}"
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def cached_or_run(
    spec: adapters.AdapterSpec,
    audio: Path,
    cache: Path,
    device: str,
    execute: bool,
    timeout: Timeout = None,
    cancel: threading.Event | None = None,
) -> adapters.AdapterResult:
    out_dir = cache_dir_for(cache, spec, audio)
    output, meta = out_dir / spec.expected_output, out_dir / "meta.json"
    if output.exists() and meta.exists():
        return adapters.AdapterResult(True, output, json.loads(meta.read_text()), None, cached=True)
    if not execute:
        return adapters.AdapterResult(False, None, None, f"{spec.id}: not computed")
    try:
        limit = _stage_timeout(timeout, spec.stage, audio)
        # the key stays with the original file; the model gets a format it can read
        model_input = audio_mod.readable(audio, cache)
    except RuntimeError as exc:
        return adapters.AdapterResult(False, None, None, f"{spec.id}: {exc}")
    return adapters.run_adapter(
        spec, model_input, out_dir, device=device, timeout=limit, cancel=cancel
    )


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
    skip: set[tuple[str, str]] | frozenset[tuple[str, str]] = frozenset(),
) -> list[Record]:
    """Computes (or reads from the cache) all combinations; errors end up in the Record.

    Transcribers that only accept drum stems (input="stem") do not run on `none`; the
    (separator, transcriber) pairs in `skip` do not run at all.
    `timeout` limits each single adapter call (seconds, overall or per stage)."""
    _check_ids(separators, "separators", registry)
    _check_ids(transcribers, "transcribers", registry)
    jobs = [
        (ds, t, sep, tr)
        for ds, ts in tracks.items()
        for t in ts
        for sep in separators
        for tr in transcribers
        if not (sep == "none" and registry[tr].needs_stem) and (sep, tr) not in skip
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


def record_notes(
    rec: Record, track: Track, read_notes: Callable[[Path], list[tuple[float, int]]] = None
) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
    """Reference and estimated notes of a successful record, without the excluded regions."""
    read = read_notes or read_drum_notes
    notes = rec.notes if rec.notes is not None else read(rec.midi)
    return _outside(track.reference_notes(), track.excluded), _outside(notes, track.excluded)


def score_records(
    records: list[Record],
    tracks: dict[str, list[Track]],
    schemes: dict[str, Scheme],
    read_notes: Callable[[Path], list[tuple[float, int]]] = read_drum_notes,
    duration: Callable[[Path], float] = audio_duration,
) -> list[dict]:
    """One row per record × scheme × class (plus 'micro'/'macro'); errors as their own rows.
    Notes in excluded regions of the track count neither as hits nor as errors.
    `audio_seconds` is the mix duration (cached per track, 0.0 if unreadable); `peak_rss_mb`
    is the larger peak RAM of the two stages (0.0 if the adapters reported none)."""
    by_id = {(ds, t.id): t for ds, ts in tracks.items() for t in ts}
    durations: dict[tuple[str, str], float] = {}

    def audio_seconds(key: tuple[str, str]) -> float:
        if key not in durations:
            try:
                durations[key] = float(duration(by_id[key].mix))
            except (RuntimeError, OSError):
                log.warning("duration of %s/%s unreadable", *key)
                durations[key] = 0.0
        return durations[key]

    rows: list[dict] = []
    for rec in records:
        metas = (rec.separator_meta or {}, rec.transcriber_meta or {})
        base = {
            "dataset": rec.dataset,
            "track": rec.track,
            "separator": rec.separator,
            "transcriber": rec.transcriber,
            "device": (rec.transcriber_meta or {}).get("device", ""),
            "sep_seconds": (rec.separator_meta or {}).get("seconds", 0.0),
            "trans_seconds": (rec.transcriber_meta or {}).get("seconds", 0.0),
            "audio_seconds": audio_seconds((rec.dataset, rec.track)) if rec.ok else 0.0,
            "peak_rss_mb": max(float(m.get("peak_rss_mb", 0.0)) for m in metas),
            "error": rec.error or "",
        }
        if not rec.ok:
            rows.extend(_row(base, name, "", None) for name in schemes)
            continue
        ref_notes, est_notes = record_notes(rec, by_id[(rec.dataset, rec.track)], read_notes)
        for name, scheme in schemes.items():
            s = score(onsets_from_notes(ref_notes, scheme), onsets_from_notes(est_notes, scheme))
            for cls, prf in [*s.per_class.items(), ("micro", s.micro)]:
                rows.append(_row(base, name, cls, prf))
            rows.append(_row(base, name, "macro", None, f1=s.macro_f1))
    return rows
