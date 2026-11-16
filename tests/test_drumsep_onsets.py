"""Tests for the onset step of the drumsep_onset adapter (numpy only), imported directly."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_SRC = Path(__file__).resolve().parents[1] / "adapters/transcribers/drumsep_onset/onsets.py"
_spec = importlib.util.spec_from_file_location("drumsep_onsets", _SRC)
assert _spec and _spec.loader
onsets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(onsets)

FPS = 100


def envelope(seconds: float, hits: list[float], height: float = 1.0) -> np.ndarray:
    """An onset-strength envelope with a sharp peak at each hit time."""
    env = np.zeros(int(seconds * FPS))
    for t in hits:
        i = round(t * FPS)
        env[i] = max(env[i], height)
        if i + 1 < len(env):
            env[i + 1] = max(env[i + 1], height / 3)
    return env


def silent(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * FPS))


def stems(**given: np.ndarray) -> dict[str, np.ndarray]:
    length = max(len(v) for v in given.values())
    return {s: given.get(s, np.zeros(length)) for s in onsets.STEM_PITCHES}


def times(notes, pitch: int) -> list[float]:
    return [round(t, 2) for t, p, _ in notes if p == pitch]


def test_each_stem_gives_its_gm_pitch_at_the_hit_times():
    notes = onsets.transcribe(
        stems(
            kick=envelope(4, [0.5, 1.5]),
            snare=envelope(4, [1.0]),
            toms=envelope(4, [2.0]),
            hh=envelope(4, [0.5, 0.75]),
            ride=envelope(4, [3.0]),
            crash=envelope(4, [3.5]),
        ),
        FPS,
    )
    assert times(notes, 36) == [0.5, 1.5]
    assert times(notes, 38) == [1.0]
    assert times(notes, 47) == [2.0]
    assert times(notes, 42) == [0.5, 0.75]
    assert times(notes, 51) == [3.0]
    assert times(notes, 49) == [3.5]
    assert [t for t, _, _ in notes] == sorted(t for t, _, _ in notes)


def test_a_quiet_stem_stays_quiet_because_all_stems_share_one_scale():
    """Bleed in a stem without its drum must not become hits (no per-stem normalisation)."""
    rng = np.random.default_rng(0)
    bleed = np.abs(rng.normal(0, 0.01, 4 * FPS))
    notes = onsets.transcribe(stems(kick=envelope(4, [0.5, 1.5]), toms=bleed), FPS)
    assert times(notes, 47) == []
    assert times(notes, 36) == [0.5, 1.5]


def test_hits_within_the_combine_window_become_one():
    notes = onsets.transcribe(stems(snare=envelope(2, [1.0, 1.01])), FPS)
    assert times(notes, 38) == [1.0]


def test_a_silent_song_gives_no_notes():
    assert onsets.transcribe(stems(kick=silent(3)), FPS) == []


def test_louder_hits_get_higher_velocity():
    env = envelope(3, [0.5]) + envelope(3, [2.0], height=0.4)
    notes = onsets.transcribe(stems(kick=env), FPS)
    (_, _, loud), (_, _, soft) = notes
    assert 1 <= soft < loud <= 127


def test_activations_are_five_classes_with_ride_and_crash_merged():
    act, labels = onsets.activations(
        stems(kick=envelope(2, [0.5]), ride=envelope(2, [1.0], 0.5), crash=envelope(2, [1.0]))
    )
    assert labels == [36, 38, 47, 42, 49]
    assert act.shape == (2 * FPS, 5) and act.dtype == np.float32
    assert act[:, 0].max() == pytest.approx(1.0)
    assert act[round(1.0 * FPS), 4] == pytest.approx(1.0)  # max of ride and crash
    assert act.max() <= 1.0


def test_missing_stem_is_an_error():
    with pytest.raises(ValueError, match="toms"):
        onsets.transcribe({"kick": silent(1)}, FPS)


def test_peak_picking_is_the_harness_s_so_tuned_thresholds_reproduce_the_adapter():
    """The adapter may not import the harness, so it keeps a copy of stickler.peaks.pick."""
    from stickler import peaks

    rng = np.random.default_rng(1)
    for _ in range(20):
        env = np.clip(rng.gamma(0.3, 0.3, 600), 0, None).astype(np.float32)
        for thr in (0.02, 0.1, 0.3):
            assert np.array_equal(onsets.pick(env, thr, FPS), peaks.pick(env, thr, FPS))
