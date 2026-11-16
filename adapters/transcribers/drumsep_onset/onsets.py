"""The onset step of drumsep_onset: per-stem onset-strength envelopes → GM drum notes.

numpy only, so the harness tests it directly (tests/test_drumsep_onsets.py). The envelopes
come from librosa (run.py); picking is done here instead of librosa.onset.onset_detect, because
onset_detect normalises each envelope on its own: a stem holding only bleed (no toms in the
song) would then be scaled up until its noise looks like hits. Here all six stems of a song
share one scale, the largest value of any stem.

Peaks are picked exactly as the harness picks ADTOF's activations (`pick` is a copy of
stickler.peaks.pick, which an adapter may not import; a test keeps the two identical), so a
threshold tuned with `stickler tune` on the saved activations reproduces this adapter's MIDI.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# DrumSep's stems (config_drumsep_mdx23c.yaml) → GM pitches; ride and crash both score as CY.
STEM_PITCHES = {"kick": 36, "snare": 38, "toms": 47, "hh": 42, "ride": 51, "crash": 49}
LABELS = [36, 38, 47, 42, 49]  # activation columns: KD, SD, TT, HH, CY (ADTOF's order)

# Default until it is chosen on MDB and ENST (SPEC.md, Release 7, method 2); on the song's
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


def _scaled(envelopes: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    missing = [s for s in STEM_PITCHES if s not in envelopes]
    if missing:
        raise ValueError(f"stems missing: {', '.join(missing)}")
    top = max(float(np.max(envelopes[s], initial=0.0)) for s in STEM_PITCHES)
    scale = 1.0 / top if top > 0 else 0.0
    return {s: np.asarray(envelopes[s], dtype=np.float32) * np.float32(scale) for s in STEM_PITCHES}


def transcribe(
    envelopes: Mapping[str, np.ndarray], fps: int, threshold: float = THRESHOLD
) -> list[tuple[float, int, int]]:
    """(time s, GM pitch, velocity) for every peak of every stem, sorted by time; the velocity
    follows the envelope's height at the peak."""
    scaled = _scaled(envelopes)
    notes = []
    for stem, pitch in STEM_PITCHES.items():
        env = scaled[stem]
        for t in pick(env, threshold, fps):
            height = float(env[min(len(env) - 1, round(t * fps))])
            notes.append((float(t), pitch, int(round(1 + 126 * min(1.0, height)))))
    return sorted(notes)


def activations(envelopes: Mapping[str, np.ndarray]) -> tuple[np.ndarray, list[int]]:
    """[frames, 5] float32 on the song's common scale (ride and crash merged by maximum), in
    LABELS order, for tuning the threshold in the harness without running the model again."""
    s = _scaled(envelopes)
    cymbals = np.maximum(s["ride"], s["crash"])
    act = np.stack([s["kick"], s["snare"], s["toms"], s["hh"], cymbals], axis=1)
    return act.astype(np.float32), list(LABELS)
