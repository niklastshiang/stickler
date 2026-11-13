"""Scoring the end product: notes snapped to the beat grid exactly as the sheet music shows them.

The benchmark scores onset times. The app, however, writes notes on a grid (notation.quantize
on the Beat This! beats). Snapping a pipeline's notes to that grid and mapping the grid
positions back to audio time shows whether the grid corrects timing jitter or adds errors
(a wrong subdivision, a beat tracker that drifts). Configured per benchmark config:

    grid: [none+adtof, combo+quality]   # also scored as "<transcriber>@grid"

`stickler run` computes the beats of every track when a config has `grid` entries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from stickler.notation import QNote, quantize
from stickler.runner import Record

SUFFIX = "@grid"
VELOCITY = 100  # transcriptions in the benchmark carry no velocities that matter here

Pipeline = tuple[str, str]


def parse_pipelines(raw: Sequence[str] | None) -> list[Pipeline]:
    out = []
    for item in raw or []:
        parts = str(item).split("+")
        if len(parts) != 2:
            raise ValueError(f"grid: expected 'separator+transcriber', got {item!r}")
        out.append((parts[0], parts[1]))
    return out


def to_times(notes: Sequence[QNote], beats: Sequence[float]) -> list[tuple[float, int]]:
    """Grid positions → audio times (linear between the two surrounding beats)."""
    out = []
    for q in notes:
        start, end = beats[q.beat], beats[q.beat + 1]
        slot, per_beat = q.position
        out.append((start + (end - start) * slot / per_beat, q.pitch))
    return out


def snap(notes: Sequence[tuple[float, int]], beats: Sequence[float]) -> list[tuple[float, int]]:
    """Quantises like the sheet music export and maps the result back to audio time."""
    q = quantize([(t, p, VELOCITY) for t, p in notes], list(beats))
    return sorted(to_times(q, beats))


def grid_records(
    records: Sequence[Record],
    pipelines: Sequence[Pipeline],
    beats: Mapping[tuple[str, str], Sequence[float] | None],
    read_notes: Callable[[Path], list[tuple[float, int]]],
) -> list[Record]:
    """One snapped record per record of a configured pipeline (combos and fusions included)."""
    wanted = set(pipelines)
    out = []
    for r in records:
        if (r.separator, r.transcriber) not in wanted:
            continue
        track_beats = beats.get((r.dataset, r.track))
        error, notes = r.error, None
        if error is None and not track_beats:
            error = "beats missing: run `stickler run` for this config"
        if error is None:
            source = r.notes if r.notes is not None else read_notes(r.midi)
            notes = tuple(snap(source, track_beats))
        out.append(
            Record(
                r.dataset,
                r.track,
                r.separator,
                r.transcriber + SUFFIX,
                r.stem,
                r.midi,
                r.separator_meta,
                r.transcriber_meta,
                error,
                notes,
            )
        )
    return out
