"""Tests for onset detection per frequency band (synthetic signals)."""

import numpy as np
import pytest

from stickler import onsets

SR = 22050


def kick(t):
    env = np.exp(-t * 30)
    return 0.8 * env * np.sin(2 * np.pi * (50 + 60 * env) * t)


def hat(t, rng):
    """High-pass noise: difference of consecutive samples."""
    noise = rng.standard_normal(len(t) + 1)
    return 0.3 * np.exp(-t * 80) * np.diff(noise)


def render(events, seconds=4.0):
    rng = np.random.default_rng(0)
    out = np.zeros(int(seconds * SR), dtype=np.float32)
    t = np.arange(int(0.2 * SR)) / SR
    for time, kind in events:
        start = int(time * SR)
        sound = kick(t) if kind == "kick" else hat(t, rng)
        out[start : start + len(sound)] += sound[: len(out) - start]
    return out


def test_onset_times_found():
    times = [0.5, 1.0, 1.25, 2.0, 3.1]
    sig = render([(t, "kick" if i % 2 else "hat") for i, t in enumerate(times)])
    found = onsets.onset_times(sig, SR)
    assert len(found) == len(times)
    assert np.allclose(found, times, atol=0.02)


def test_bands_separate_kick_and_hat():
    sig = render([(0.5, "kick"), (1.5, "hat")])
    times, flux = onsets.band_flux(sig, SR)
    at_kick, at_hat = np.argmin(abs(times - 0.5)), np.argmin(abs(times - 1.5))
    kick_frames, hat_frames = flux[at_kick - 2 : at_kick + 3], flux[at_hat - 2 : at_hat + 3]
    assert kick_frames[:, 0].max() > kick_frames[:, 2].max()
    assert hat_frames[:, 2].max() > hat_frames[:, 0].max()
    assert flux.shape == (len(times), len(onsets.BANDS))


def test_silence_has_no_onsets():
    assert len(onsets.onset_times(np.zeros(SR * 2, dtype=np.float32), SR)) == 0


@pytest.mark.parametrize("gap", [0.03, 0.06])
def test_close_onsets(gap):
    sig = render([(1.0, "hat"), (1.0 + gap, "hat")])
    assert len(onsets.onset_times(sig, SR)) == (1 if gap < onsets.MIN_GAP else 2)
