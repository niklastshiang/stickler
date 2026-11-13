"""Tests for onset peak picking on frame activations (madmom's NotePeakPicking semantics)."""

import numpy as np
import pytest

from stickler import peaks


def act(n=100, **spikes):
    a = np.zeros(n, dtype=np.float32)
    for frame, value in spikes.items():
        a[int(frame.removeprefix("f"))] = value
    return a


def test_single_peak_above_threshold():
    assert peaks.pick(act(f30=0.9), 0.3, fps=100).tolist() == [0.30]


def test_peak_below_threshold_is_dropped():
    # moving average (10 frames before, 1 after) is subtracted first: 0.33 - 0.33/12 < 0.32
    assert peaks.pick(act(f30=0.33), 0.32).size == 0


def test_close_peaks_are_combined_to_the_stronger():
    a = act(f30=0.6, f32=0.9)  # 2 frames apart = within `combine` (20 ms)
    assert peaks.pick(a, 0.2).tolist() == [0.32]
    a = act(f30=0.6, f40=0.9)
    assert peaks.pick(a, 0.2).tolist() == [0.30, 0.40]


def test_plateau_without_onset_has_no_peak():
    a = np.full(100, 0.8, dtype=np.float32)
    assert peaks.pick(a, 0.2).size == 0


def test_pick_all_maps_columns_to_pitches():
    a = np.stack([act(f10=0.9), act(f50=0.9)], axis=1)
    notes = peaks.pick_all(a, [0.3, 0.3], pitches=[35, 38], fps=100)
    assert notes == [(0.10, 35), (0.50, 38)]
    with pytest.raises(ValueError, match="thresholds"):
        peaks.pick_all(a, [0.3], pitches=[35, 38])
