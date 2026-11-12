"""Tests for the time alignment of own notes onto the recording (synthetic data)."""

import mido
import numpy as np
import pytest

from stickler import align

KICK, SNARE, HAT, CRASH = 36, 38, 42, 49


def groove(bars, beat=0.5, fill_every=4):
    """4/4 groove (kick 1+3, snare 2+4, eighth-note hi-hat), every 4th bar with a snare fill."""
    notes = []
    for bar in range(bars):
        t0 = bar * 4 * beat
        if bar % fill_every == fill_every - 1:
            notes += [(t0 + k * beat / 4, SNARE) for k in range(16)]
            continue
        if bar % fill_every == 0:
            notes.append((t0, CRASH))
        notes += [(t0, KICK), (t0 + 2 * beat, KICK), (t0 + beat, SNARE), (t0 + 3 * beat, SNARE)]
        notes += [(t0 + k * beat / 2, HAT) for k in range(8)]
    return sorted(notes)


def warp(t):
    """Recording: 3 s intro, slightly fluctuating tempo (±2 %)."""
    return 3.0 + t * 1.0 + 0.15 * np.sin(t / 6.0)


def flux_for(times_pitches, duration, noise=0.0, seed=0):
    """Synthetic band flux: impulses per class in the matching band."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, duration, align.onsets.HOP)
    flux = rng.random((len(t), 3)) * noise
    band = {KICK: 0, SNARE: 1, HAT: 2, CRASH: 2}
    for time, pitch in times_pitches:
        flux[int(round(time / align.onsets.HOP)), band[pitch]] += 1.0
    return t, flux


def beats_for(score_beats, f, jitter=0.01, seed=1):
    rng = np.random.default_rng(seed)
    return np.array([f(b) for b in score_beats]) + rng.uniform(-jitter, jitter, len(score_beats))


def make_score(notes, beat=0.5, n_beats=None):
    n = n_beats or int(max(t for t, _ in notes) / beat) + 2
    return align.Score(beats=np.arange(n) * beat, notes=notes)


def test_read_score_beats_follow_tempo_changes(tmp_path):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))  # 120 BPM
    track.append(mido.Message("note_on", channel=9, note=KICK, velocity=100, time=0))
    track.append(mido.Message("note_off", channel=9, note=KICK, velocity=0, time=480))
    track.append(mido.MetaMessage("set_tempo", tempo=1000000, time=480))  # from beat 2: 60 BPM
    track.append(mido.Message("note_on", channel=9, note=SNARE, velocity=100, time=0))
    track.append(mido.Message("note_off", channel=9, note=SNARE, velocity=0, time=480))
    path = tmp_path / "s.mid"
    mid.save(path)
    score = align.read_score(path)
    assert score.notes == [(0.0, KICK), (1.0, SNARE)]
    assert np.allclose(score.beats[:4], [0.0, 0.5, 1.0, 2.0])


def test_aligns_offset_and_rubato():
    notes = groove(64)  # 128 s: above the 120 s minimum of evaluated music
    score = make_score(notes)
    true = [(warp(t), p) for t, p in notes]
    ft, flux = flux_for(true, warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    got = dict(((round(t, 3), p), a) for (t, p), a in zip(notes, result.mapped_times, strict=True))
    errors = [abs(got[(round(t, 3), p)] - warp(t)) for t, p in notes]
    assert max(errors) < 0.02  # flux grid 10 ms + beat jitter
    assert result.quality.passed, result.quality.reasons


def test_audio_section_missing_in_score_is_excluded():
    """The recording plays 2 bars (8 beats) more than the notes contain: eighth-note kicks with
    crash, a pattern that does not occur in the notes (otherwise the position is ambiguous)."""
    notes = groove(24)
    score = make_score(notes)
    insert_at, extra = 6.0, 4.0  # 2 bars of 2 s after score second 6

    def f(t):
        return warp(t) + (extra if t >= insert_at else 0.0)

    audio_notes = [(f(t), p) for t, p in notes]
    audio_notes += [(warp(insert_at) + k * 0.25, KICK) for k in range(16)]
    audio_notes += [(warp(insert_at) + k * 1.0, CRASH) for k in range(4)]
    ft, flux = flux_for(audio_notes, f(score.beats[-1]) + 2, noise=0.05)
    beats = np.sort(
        np.concatenate([beats_for(score.beats, f), warp(insert_at) + np.arange(8) * 0.5])
    )
    result = align.align(score, beats, ft, flux)
    lo, hi = warp(insert_at), warp(insert_at) + extra
    assert any(a <= lo + 0.3 and b >= hi - 0.3 for a, b in result.excluded)
    after = [(a, f(t)) for (t, _), a in zip(notes, result.mapped_times, strict=True) if t > 8]
    assert max(abs(a - b) for a, b in after) < 0.02


def test_score_gap_with_drums_in_audio_is_excluded():
    """The notes rest for 2 bars ("drum loop"), the recording plays."""
    full = groove(16)
    gap = (8.0, 12.0)
    notes = [(t, p) for t, p in full if not gap[0] <= t < gap[1]]
    score = make_score(notes, n_beats=66)
    ft, flux = flux_for([(warp(t), p) for t, p in full], warp(33) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    lo, hi = warp(gap[0]), warp(gap[1])
    assert any(a <= lo + 0.1 and b >= hi - 0.6 for a, b in result.excluded)
    assert result.quality.excluded_strong == pytest.approx(0.125, abs=0.05)


def test_half_time_beats_are_handled():
    """Beat This! hears half tempo: only every second beat is reported."""
    notes = groove(32)
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in notes], warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats[::2], warp), ft, flux)
    errors = [abs(a - warp(t)) for (t, _), a in zip(notes, result.mapped_times, strict=True)]
    assert max(errors) < 0.02


def test_wrong_reference_fails_quality():
    """Notes do not match the recording (different pattern): the check fails."""
    notes = groove(32)
    other = [(t + 0.25, SNARE) for t, p in notes if p == KICK]  # syncopation instead of groove
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in other], warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    assert not result.quality.passed
    assert result.quality.reasons


def test_beat_level_switching_between_sections():
    """Beat This! hears eighths instead of quarters in some sections (as with Bat Country)."""
    notes = groove(32)
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in notes], warp(score.beats[-1]) + 2, noise=0.05)
    quarters = score.beats
    eighths = np.sort(np.concatenate([quarters, (quarters[:-1] + quarters[1:]) / 2]))
    mixed = np.concatenate(
        [
            quarters[quarters < 16],
            eighths[(eighths >= 16) & (eighths < 40)],
            quarters[quarters >= 40],
        ]
    )
    result = align.align(score, beats_for(mixed, warp), ft, flux)
    errors = [abs(a - warp(t)) for (t, _), a in zip(notes, result.mapped_times, strict=True)]
    assert max(errors) < 0.02
    assert result.quality.beat_fit > 0.95


def test_half_time_section_gets_midpoints():
    notes = groove(32)
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in notes], warp(score.beats[-1]) + 2, noise=0.05)
    q = score.beats
    mixed = np.concatenate([q[q < 20], q[(q >= 20) & (q < 44)][::2], q[q >= 44]])
    result = align.align(score, beats_for(mixed, warp), ft, flux)
    errors = [abs(a - warp(t)) for (t, _), a in zip(notes, result.mapped_times, strict=True)]
    assert max(errors) < 0.02


def test_normalize_beats_fills_gaps_without_duplicates():
    """Gap of 1.45 quarters: gets split, no beat duplicated."""
    beats = np.array([0.0, 0.5, 1.0, 1.725, 2.225, 2.725])
    flux = np.zeros((300, 3))
    out = align._normalize_beats(beats, 0.5, np.arange(300) * 0.01, flux)
    assert np.all(np.diff(out) > 0.3)


def test_pause_in_recording_does_not_bend_neighbours():
    """The recording pauses briefly after bar 12 (0.25 s break), the notes run on."""
    notes = groove(24)
    score = make_score(notes)
    pause_at = 24.0

    def f(t):
        return warp(t) + (0.25 if t >= pause_at else 0.0)

    ft, flux = flux_for([(f(t), p) for t, p in notes], f(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, f), ft, flux)
    errors = [
        abs(a - f(t))
        for (t, _), a in zip(notes, result.mapped_times, strict=True)
        if not pause_at - 0.5 < t < pause_at  # in the beat with the pause the position is open
    ]
    assert max(errors) < 0.02


def test_score_passage_missing_in_recording_does_not_fail():
    """The score repeats 2 bars that the recording does not have (owner's rule: extra score
    passages are reported, but are no reason to fail)."""
    notes = groove(72)  # 144 s, so 140 s remain after the cut (minimum: 120 s)
    cut, extra = 16.0, 4.0  # score bars 8-9 (16-20 s) are not in the recording

    def f(t):
        return warp(t) if t < cut else warp(t - extra)

    audio_notes = [(f(t), p) for t, p in notes if not cut <= t < cut + extra]
    score = make_score(notes)
    ft, flux = flux_for(audio_notes, f(score.beats[-1]) + 2, noise=0.05)
    kept = score.beats[(score.beats < cut) | (score.beats >= cut + extra)]
    result = align.align(score, beats_for(kept, f), ft, flux)
    assert result.quality.passed, result.quality.reasons
    assert result.quality.score_unmatched == pytest.approx(8 / 288, abs=0.02)
    after = [(a, f(t)) for (t, _), a in zip(notes, result.mapped_times, strict=True) if t > 22]
    assert max(abs(a - b) for a, b in after) < 0.02


def test_too_little_evaluated_music_fails():
    """Owner's rule: at least 2 minutes of evaluated music."""
    notes = groove(16)  # 32 s
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in notes], warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    assert not result.quality.passed
    assert any("evaluated_seconds" in r for r in result.quality.reasons)


def test_evaluated_seconds_excludes_gaps():
    full = groove(16)
    gap = (8.0, 12.0)
    notes = [(t, p) for t, p in full if not gap[0] <= t < gap[1]]
    score = make_score(notes, n_beats=66)
    ft, flux = flux_for([(warp(t), p) for t, p in full], warp(33) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    span = warp(full[-1][0]) - warp(0.0)
    assert result.quality.evaluated_seconds == pytest.approx(span - 4.0, abs=0.6)
