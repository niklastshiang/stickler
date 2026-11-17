"""Onsets from separated drum stems: per-stem onset-strength envelopes → GM drum notes.

For transcribers that first split a drum stem into one stem per drum (drumsep_onset,
Separate-and-Detect) and then detect onsets per stem, so they share one detector and differ
only in the separation. Needs numpy (unlike the rest of stickler_adapter); imported only by
adapters that have it. The harness tests it directly (tests/test_adapter_onsets.py).

All stems of a song share one scale, the largest envelope value of any stem: librosa's
onset_detect normalises each envelope on its own, so a stem holding only bleed (a song without
toms) would be scaled up until its noise looks like hits. Peaks are then picked exactly as the
harness picks ADTOF's activations (`pick` is a copy of stickler.peaks.pick, which an adapter may
not import; a test keeps the two identical), so a threshold tuned with `stickler tune` on the
saved activations reproduces the adapter's MIDI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

LABELS = [36, 38, 47, 42, 49]  # activation columns: KD, SD, TT, HH, CY (ADTOF's order)

# Default until it is chosen on MDB and ENST (SPEC.md, Release 8, method 2); on the song's
# common scale, after the moving average is subtracted.
THRESHOLD = 0.1

# stickler.peaks: madmom's NotePeakPickingProcessor as ADTOF uses it
PRE_AVG, POST_AVG = 0.1, 0.01
PRE_MAX, POST_MAX = 0.02, 0.01
COMBINE = 0.02


def _frames(seconds: float, fps: int) -> int:
    return int(round(seconds * fps))


def pick(activation: np.ndarray, threshold: float, fps: int) -> np.ndarray:
    """Onset times in seconds for one class (copy of stickler.peaks.pick)."""
    a = np.asarray(activation, dtype=np.float32).reshape(-1)
    if a.size == 0:
        return np.zeros(0)
    left, right = _frames(PRE_AVG, fps), _frames(POST_AVG, fps)
    kernel = np.full(left + 1 + right, 1.0 / (left + 1 + right), dtype=np.float32)
    avg = np.convolve(np.pad(a, (left, right), mode="edge"), kernel, mode="valid")
    proc = np.maximum(np.float32(0.0), a - avg.astype(np.float32))
    left, right = _frames(PRE_MAX, fps), _frames(POST_MAX, fps)
    window_max = sliding_window_view(np.pad(proc, (left, right), mode="edge"), left + 1 + right)
    candidates = np.flatnonzero((proc >= window_max.max(axis=1)) & (proc >= threshold))
    if candidates.size == 0:
        return np.zeros(0)
    combine = max(1, _frames(COMBINE, fps))
    kept, group = [], [int(candidates[0])]
    for idx in candidates[1:]:
        if idx - group[-1] <= combine:
            group.append(int(idx))
        else:
            kept.append(max(group, key=lambda i: proc[i]))  # first of equal maxima
            group = [int(idx)]
    kept.append(max(group, key=lambda i: proc[i]))
    return np.asarray(kept) / float(fps)


def _scaled(envelopes: Mapping[str, np.ndarray], stems: Sequence[str]) -> dict[str, np.ndarray]:
    missing = [s for s in stems if s not in envelopes]
    if missing:
        raise ValueError(f"stems missing: {', '.join(missing)}")
    top = max(float(np.max(envelopes[s], initial=0.0)) for s in stems)
    scale = np.float32(1.0 / top if top > 0 else 0.0)
    return {s: np.asarray(envelopes[s], dtype=np.float32) * scale for s in stems}


def transcribe(
    envelopes: Mapping[str, np.ndarray],
    stem_pitches: Mapping[str, int],
    fps: int,
    threshold: float = THRESHOLD,
) -> list[tuple[float, int, int]]:
    """(time s, GM pitch, velocity) for every peak of every stem, sorted by time; the velocity
    follows the envelope's height at the peak."""
    scaled = _scaled(envelopes, list(stem_pitches))
    notes = []
    for stem, pitch in stem_pitches.items():
        env = scaled[stem]
        for t in pick(env, threshold, fps):
            height = float(env[min(len(env) - 1, round(t * fps))])
            notes.append((float(t), pitch, int(round(1 + 126 * min(1.0, height)))))
    return sorted(notes)


def activations(
    envelopes: Mapping[str, np.ndarray], columns: Sequence[Sequence[str]]
) -> tuple[np.ndarray, list[int]]:
    """[frames, 5] float32 on the song's common scale, one column per class in LABELS order,
    each the maximum of its stems (e.g. ride and crash for CY); for tuning the threshold in the
    harness without running the model again."""
    if len(columns) != len(LABELS):
        raise ValueError(f"{len(LABELS)} columns needed, got {len(columns)}")
    s = _scaled(envelopes, [stem for column in columns for stem in column])
    act = np.stack([np.max([s[stem] for stem in column], axis=0) for column in columns], axis=1)
    return act.astype(np.float32), list(LABELS)
