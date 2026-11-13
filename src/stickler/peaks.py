"""Onset peak picking on frame activations, with the semantics of madmom's
NotePeakPickingProcessor as ADTOF uses it (pre_avg 0.1 s, post_avg 0.01 s, pre_max 0.02 s,
post_max 0.01 s, combine 0.02 s):

1. subtract a moving average (edge-padded window from pre_avg before to post_avg after) and
   clip at 0,
2. keep frames that are the maximum of their window (pre_max/post_max) and reach the threshold,
3. merge peaks that follow each other within `combine` (chained) into the strongest one.

With ADTOF's default thresholds this reproduces the adapter's drums.mid (checked on MDB, see
tasks/todo.md), so thresholds can be tuned and inputs fused without running the model again.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

FPS = 100
PRE_AVG, POST_AVG = 0.1, 0.01
PRE_MAX, POST_MAX = 0.02, 0.01
COMBINE = 0.02


def _frames(seconds: float, fps: int) -> int:
    return int(round(seconds * fps))


def pick(activation: np.ndarray, threshold: float, fps: int = FPS) -> np.ndarray:
    """Onset times in seconds for one class."""
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


def pick_all(
    activations: np.ndarray, thresholds: Sequence[float], pitches: Sequence[int], fps: int = FPS
) -> list[tuple[float, int]]:
    """[frames, classes] activations → (time, pitch) notes sorted by time, one threshold and
    one GM pitch per class column."""
    if len(thresholds) != activations.shape[1] or len(pitches) != activations.shape[1]:
        raise ValueError(
            f"{activations.shape[1]} classes need as many thresholds and pitches "
            f"(got {len(thresholds)} and {len(pitches)})"
        )
    notes = [
        (float(t), int(pitch))
        for col, (thr, pitch) in enumerate(zip(thresholds, pitches, strict=True))
        for t in pick(activations[:, col], thr, fps)
    ]
    return sorted(notes)
