"""The onset step of drumsep_onset: per-stem onset-strength envelopes → GM drum notes.

numpy only, so the harness tests it directly (tests/test_drumsep_onsets.py). The envelopes
come from librosa (run.py); picking is done here instead of librosa.onset.onset_detect, because
onset_detect normalises each envelope on its own: a stem holding only bleed (no toms in the
song) would then be scaled up until its noise looks like hits. Here all six stems of a song
share one scale, the largest value of any stem.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

# DrumSep's stems (config_drumsep_mdx23c.yaml) → GM pitches; ride and crash both score as CY.
STEM_PITCHES = {"kick": 36, "snare": 38, "toms": 47, "hh": 42, "ride": 51, "crash": 49}
LABELS = [36, 38, 47, 42, 49]  # activation columns: KD, SD, TT, HH, CY (ADTOF's order)

# Defaults until they are chosen on MDB and ENST (SPEC.md, Release 7, method 2).
THRESHOLD = 0.1  # share of the song's largest envelope value
WAIT = 0.03  # seconds: of two peaks closer than this, the larger one stays


def _scaled(envelopes: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    missing = [s for s in STEM_PITCHES if s not in envelopes]
    if missing:
        raise ValueError(f"stems missing: {', '.join(missing)}")
    top = max(float(np.max(envelopes[s], initial=0.0)) for s in STEM_PITCHES)
    scale = 1.0 / top if top > 0 else 0.0
    return {s: np.asarray(envelopes[s], dtype=np.float64) * scale for s in STEM_PITCHES}


def _peaks(env: np.ndarray, threshold: float, wait: int) -> list[int]:
    """Frames that rise from the left, do not fall to the right, reach the threshold, and are
    the largest within `wait` frames of the previous kept peak."""
    left = np.concatenate(([-np.inf], env[:-1]))
    right = np.concatenate((env[1:], [-np.inf]))
    candidates = np.flatnonzero((env > left) & (env >= right) & (env >= threshold))
    kept: list[int] = []
    for i in candidates:
        if kept and i - kept[-1] < wait:
            if env[i] > env[kept[-1]]:
                kept[-1] = int(i)
            continue
        kept.append(int(i))
    return kept


def transcribe(
    envelopes: Mapping[str, np.ndarray],
    fps: int,
    threshold: float = THRESHOLD,
    wait: float = WAIT,
) -> list[tuple[float, int, int]]:
    """(time s, GM pitch, velocity) for every peak of every stem, sorted by time."""
    scaled = _scaled(envelopes)
    wait_frames = max(1, round(wait * fps))
    notes = [
        (i / fps, pitch, int(round(1 + 126 * min(1.0, env[i]))))
        for stem, pitch in STEM_PITCHES.items()
        for env in [scaled[stem]]
        for i in _peaks(env, threshold, wait_frames)
    ]
    return sorted(notes)


def activations(envelopes: Mapping[str, np.ndarray]) -> tuple[np.ndarray, list[int]]:
    """[frames, 5] float32 on the song's common scale (ride and crash merged by maximum), in
    LABELS order, for tuning the threshold in the harness without running the model again."""
    s = _scaled(envelopes)
    cymbals = np.maximum(s["ride"], s["crash"])
    act = np.stack([s["kick"], s["snare"], s["toms"], s["hh"], cymbals], axis=1)
    return act.astype(np.float32), list(LABELS)
