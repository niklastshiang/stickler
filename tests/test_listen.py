"""Tests for the listening snippets that the owner judges by ear."""

import numpy as np
import pytest

from stickler import listen

SR = 1000  # low rate keeps the arrays small; the marker tone stays below Nyquist


def test_snippet_plays_the_passage_plain_then_with_the_marker_in_the_other_ear():
    mix = np.zeros(10 * SR)
    stem = np.zeros(10 * SR)
    stem[5 * SR] = 0.5  # the drum hit at the spot
    s = listen.render(mix, stem, time=5.0, sr=SR, marker_freq=200.0)
    passage = int((listen.BEFORE + listen.AFTER) * SR)
    gap = int(listen.GAP * SR)
    music, marker = s.signal[:, 0], s.signal[:, 1]
    assert s.signal.shape == (2 * passage + gap, 2)
    assert np.array_equal(music[:passage], music[passage + gap :])  # same music twice
    assert not marker[: passage + gap].any()  # no marker in the first pass
    assert s.marker == pytest.approx((passage + gap) / SR + listen.BEFORE)
    assert np.flatnonzero(marker)[0] / SR == pytest.approx(s.marker)
    assert np.abs(marker).max() >= listen.PEAK  # as loud as the music, but in its own ear


def test_drums_are_normalised_and_the_stem_is_louder_than_the_mix():
    mix = np.zeros(10 * SR)
    stem = np.zeros(10 * SR)
    mix[4 * SR] = 0.01  # a quiet mix sample and a quiet drum hit
    stem[5 * SR] = 0.02
    s = listen.render(mix, stem, time=5.0, sr=SR, marker_freq=200.0)
    first = s.signal[: int((listen.BEFORE + listen.AFTER) * SR), 0]
    assert np.abs(first).max() == pytest.approx(listen.PEAK)
    hit, other = first[int(listen.BEFORE * SR)], first[int((listen.BEFORE - 1.0) * SR)]
    assert hit > 2 * other


def test_a_spot_near_the_start_gets_a_shorter_passage():
    s = listen.render(np.zeros(10 * SR), np.zeros(10 * SR), time=1.0, sr=SR, marker_freq=200.0)
    passage = int((1.0 + listen.AFTER) * SR)
    assert len(s.signal) == 2 * passage + int(listen.GAP * SR)  # frames
    assert s.marker == pytest.approx((passage + int(listen.GAP * SR)) / SR + 1.0)


def test_snippet_is_written_as_wav(tmp_path):
    from stickler import audio

    s = listen.render(np.zeros(10 * SR), np.zeros(10 * SR), time=5.0, sr=SR, marker_freq=200.0)
    path = listen.write(tmp_path / "spot.wav", s)
    assert audio.duration(path) == pytest.approx(len(s.signal) / SR, abs=0.01)


def test_loop_is_a_short_window_around_the_spot_with_the_click():
    mix = np.zeros(10 * SR)
    stem = np.full(10 * SR, 0.3)  # constant music, to see the fades at the edges
    s = listen.render_loop(mix, stem, time=5.0, sr=SR, marker_freq=200.0)
    music, marker = s.signal[:, 0], s.signal[:, 1]
    assert len(music) == int((listen.LOOP_BEFORE + listen.LOOP_AFTER) * SR)
    assert s.marker == pytest.approx(listen.LOOP_BEFORE)
    assert np.flatnonzero(marker)[0] / SR == pytest.approx(listen.LOOP_BEFORE)
    assert abs(music[0]) < 0.01 and abs(music[-1]) < 0.01  # faded: no click at the seam
    assert music[len(music) // 2] == pytest.approx(listen.PEAK)
