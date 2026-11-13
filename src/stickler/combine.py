"""Combined pipelines: every instrument class is taken from the pipeline that is best at it.

Configured under `combos` in a benchmark config, with classes of the 5-class scheme:

    combos:
      quality:
        demucs+muscriptor_m: [KD, SD, TT]
        none+adtof: [HH, CY]

Nothing is computed: the parts' transcriptions come from the cache, and a combined record is
scored like any other pipeline (separator "combo", transcriber = the combo's name).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stickler.classes import Scheme
from stickler.runner import Record

COMBO_SEPARATOR = "combo"

Pipeline = tuple[str, str]  # (separator, transcriber)


@dataclass(frozen=True)
class Combo:
    name: str
    parts: dict[Pipeline, frozenset[str]]  # pipeline → classes it contributes


def parse_combos(raw: dict | None, scheme: Scheme) -> list[Combo]:
    """`{name: {"sep+trans": [classes]}}` → combos; each class comes from at most one part."""
    combos = []
    for name, parts in (raw or {}).items():
        taken: dict[str, str] = {}
        parsed: dict[Pipeline, frozenset[str]] = {}
        for pipeline, classes in parts.items():
            pair = str(pipeline).split("+")
            if len(pair) != 2:
                raise ValueError(
                    f"combo {name}: expected 'separator+transcriber', got {pipeline!r}"
                )
            for cls in classes:
                if cls not in scheme.classes:
                    raise ValueError(f"combo {name}: unknown class {cls!r} in {pipeline}")
                if cls in taken:
                    raise ValueError(
                        f"combo {name}: class {cls} taken from more than one pipeline "
                        f"({taken[cls]}, {pipeline})"
                    )
                taken[cls] = pipeline
            parsed[(pair[0], pair[1])] = frozenset(classes)
        combos.append(Combo(str(name), parsed))
    return combos


def _label(pipeline: Pipeline) -> str:
    return "+".join(pipeline)


def combine_records(
    records: list[Record],
    combos: list[Combo],
    scheme: Scheme,
    read_notes: Callable[[Path], list[tuple[float, int]]],
) -> list[Record]:
    """One combined record per combo and track that has at least one part in `records`.
    Runtime: every distinct separator and transcriber run counts once."""
    index = {(r.dataset, r.track, r.separator, r.transcriber): r for r in records}
    tracks = list(dict.fromkeys((r.dataset, r.track) for r in records))
    out = []
    for combo in combos:
        for dataset, track in tracks:
            parts = {p: index.get((dataset, track, *p)) for p in combo.parts}
            if not any(parts.values()):
                continue
            missing = [_label(p) for p, r in parts.items() if r is None]
            failed = [_label(p) for p, r in parts.items() if r is not None and not r.ok]
            present = [r for r in parts.values() if r is not None]
            sep_metas = {r.separator: r.separator_meta or {} for r in present}
            trans_metas = [r.transcriber_meta or {} for r in present]
            all_metas = [*sep_metas.values(), *trans_metas]
            error = None
            if missing:
                error = f"missing part: {', '.join(missing)}"
            elif failed:
                error = f"failed part: {', '.join(failed)}"
            notes = None
            if error is None:
                notes = tuple(
                    (time, pitch)
                    for p, r in parts.items()
                    for time, pitch in (r.notes if r.notes is not None else read_notes(r.midi))
                    if scheme.class_of(pitch) in combo.parts[p]
                )
            devices = sorted({m["device"] for m in trans_metas if m.get("device")})
            out.append(
                Record(
                    dataset,
                    track,
                    COMBO_SEPARATOR,
                    combo.name,
                    None,
                    None,
                    {"seconds": sum(m.get("seconds", 0.0) for m in sep_metas.values())},
                    {
                        "seconds": sum(m.get("seconds", 0.0) for m in trans_metas),
                        "peak_rss_mb": max(
                            (float(m.get("peak_rss_mb", 0.0)) for m in all_metas), default=0.0
                        ),
                        "device": "+".join(devices),
                    },
                    error,
                    notes,
                )
            )
    return out
