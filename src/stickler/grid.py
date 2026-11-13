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
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from stickler.notation import QNote, quantize
from stickler.runner import Record

SUFFIX = "@grid"
CONSENSUS_SUFFIX = "@rep"
VELOCITY = 100  # transcriptions in the benchmark carry no velocities that matter here

Pipeline = tuple[str, str]


@dataclass(frozen=True)
class BeatGrid:
    beats: list[float]
    downbeats: list[float]


@dataclass(frozen=True)
class Consensus:
    similarity: float  # minimum Jaccard index of two bars' hit sets
    add: float  # share of similar bars that must have a hit for it to be added
    remove: float  # share at or below which a hit is removed (0 = never)


def downbeat_indices(beats: Sequence[float], downbeats: Sequence[float]) -> list[int]:
    """Index of the nearest beat for every downbeat time."""
    b = np.asarray(beats, dtype=float)
    return sorted({int(np.argmin(np.abs(b - t))) for t in downbeats})


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
    beats: Mapping[tuple[str, str], BeatGrid | None],
    read_notes: Callable[[Path], list[tuple[float, int]]],
    consensus_params: Consensus | None = None,
) -> list[Record]:
    """One snapped record per record of a configured pipeline (combos and fusions included),
    plus one with consensus across repeated bars if `consensus_params` is given."""
    wanted = set(pipelines)
    out = []
    for r in records:
        if (r.separator, r.transcriber) not in wanted:
            continue
        bg = beats.get((r.dataset, r.track))
        error, snapped, voted = r.error, None, None
        if error is None and not bg:
            error = "beats missing: run `stickler run` for this config"
        if error is None:
            source = r.notes if r.notes is not None else read_notes(r.midi)
            q = quantize([(t, p, VELOCITY) for t, p in source], bg.beats)
            snapped = tuple(sorted(to_times(q, bg.beats)))
            if consensus_params:
                c = consensus_params
                q = consensus(
                    q,
                    downbeat_indices(bg.beats, bg.downbeats),
                    similarity=c.similarity,
                    add=c.add,
                    remove=c.remove,
                    n_beats=len(bg.beats) - 1,
                )
                voted = tuple(sorted(to_times(q, bg.beats)))
        variants = [(SUFFIX, snapped)]
        if consensus_params:
            variants.append((CONSENSUS_SUFFIX, voted))
        for suffix, notes in variants:
            out.append(
                Record(
                    r.dataset,
                    r.track,
                    r.separator,
                    r.transcriber + suffix,
                    r.stem,
                    r.midi,
                    r.separator_meta,
                    r.transcriber_meta,
                    error,
                    notes,
                )
            )
    return out


# --- Consensus across repeated bars -------------------------------------------------------
#
# A groove usually repeats many times. Bars whose hit patterns are nearly the same vote per
# grid position: a hit that most of them have but one lacks was probably missed; a hit that
# almost none of them have was probably a false detection. Real variations (a crash at the
# start of a section) look like the latter, so adding and removing have separate thresholds.

DIVISIONS = 12  # common grid for sixteenths (3) and triplet eighths (4)
MIN_GROUP = 3  # a bar needs at least two similar bars to be corrected

Key = tuple[int, int, int]  # (beat within the bar, position in DIVISIONS, pitch)


def _slot(position: tuple[int, int]) -> int:
    slot, per_beat = position
    return slot * DIVISIONS // per_beat


def _position(slot: int) -> tuple[int, int]:
    if slot % 3 == 0:
        return slot // 3, 4
    if slot % 4 == 0:
        return slot // 4, 3
    return slot, DIVISIONS


def _bars(downbeats: Sequence[int], last_beat: int) -> list[tuple[int, int]]:
    """(first beat, number of beats) per bar; the last bar as long as the one before."""
    starts = sorted(set(downbeats))
    bars = [(a, b - a) for a, b in zip(starts, starts[1:], strict=False)]
    if starts and starts[-1] <= last_beat:
        bars.append((starts[-1], bars[-1][1] if bars else last_beat - starts[-1] + 1))
    return bars


def _similarity(a: set[Key], b: set[Key]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def consensus(
    notes: Sequence[QNote],
    downbeats: Sequence[int],
    *,
    similarity: float,
    add: float,
    remove: float,
    n_beats: int | None = None,
) -> list[QNote]:
    """`downbeats`: beat indices where bars start. A hit is added to a bar if at least `add` of
    its group of similar bars (similarity = Jaccard index of the hit sets, bars of equal length)
    have it, and removed if at most `remove` of them have it. `n_beats`: number of beat
    intervals; nothing is added at or beyond it (the last bar's length is only estimated)."""
    if not notes:
        return []
    bars = _bars(downbeats, max(n.beat for n in notes))
    content: list[set[Key]] = []
    members: list[list[QNote]] = []
    for start, length in bars:
        inside = [n for n in notes if start <= n.beat < start + length]
        members.append(inside)
        content.append({(n.beat - start, _slot(n.position), n.pitch) for n in inside})
    in_bars = {id(n) for m in members for n in m}
    out = [n for n in notes if id(n) not in in_bars]  # before the first downbeat
    for i, (start, length) in enumerate(bars):
        group = [
            j
            for j, (_, other) in enumerate(bars)
            if other == length and _similarity(content[i], content[j]) >= similarity
        ]
        if len(group) < MIN_GROUP:
            out += members[i]
            continue
        union = set().union(*(content[j] for j in group))
        share = {k: sum(k in content[j] for j in group) / len(group) for k in union}
        drop = {k for k in content[i] if share[k] <= remove}
        out += [n for n in members[i] if (n.beat - start, _slot(n.position), n.pitch) not in drop]
        out += [
            QNote(start + beat, _position(slot), pitch, VELOCITY)
            for beat, slot, pitch in sorted(union - content[i])
            if share[(beat, slot, pitch)] >= add and (n_beats is None or start + beat < n_beats)
        ]
    return sorted(out)
