"""Tests für den Zeitabgleich eigener Noten auf die Aufnahme (synthetische Daten)."""

import mido
import numpy as np
import pytest

from stickler import align

KICK, SNARE, HAT, CRASH = 36, 38, 42, 49


def groove(bars, beat=0.5, fill_every=4):
    """4/4-Groove (Kick 1+3, Snare 2+4, Achtel-Hi-Hat), jeder 4. Takt mit Snare-Fill."""
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
    """Aufnahme: 3 s Intro, leicht schwankendes Tempo (±2 %)."""
    return 3.0 + t * 1.0 + 0.15 * np.sin(t / 6.0)


def flux_for(times_pitches, duration, noise=0.0, seed=0):
    """Synthetischer Bandfluss: Impulse je Klasse im passenden Band."""
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
    track.append(mido.MetaMessage("set_tempo", tempo=1000000, time=480))  # ab Beat 2: 60 BPM
    track.append(mido.Message("note_on", channel=9, note=SNARE, velocity=100, time=0))
    track.append(mido.Message("note_off", channel=9, note=SNARE, velocity=0, time=480))
    path = tmp_path / "s.mid"
    mid.save(path)
    score = align.read_score(path)
    assert score.notes == [(0.0, KICK), (1.0, SNARE)]
    assert np.allclose(score.beats[:4], [0.0, 0.5, 1.0, 2.0])


def test_aligns_offset_and_rubato():
    notes = groove(32)
    score = make_score(notes)
    true = [(warp(t), p) for t, p in notes]
    ft, flux = flux_for(true, warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    got = dict(((round(t, 3), p), a) for (t, p), a in zip(notes, result.mapped_times, strict=True))
    errors = [abs(got[(round(t, 3), p)] - warp(t)) for t, p in notes]
    assert max(errors) < 0.02  # Flux-Raster 10 ms + Beat-Jitter
    assert result.quality.passed, result.quality.reasons


def test_audio_section_missing_in_score_is_excluded():
    """Die Aufnahme spielt 2 Takte (8 Beats) mehr, als in den Noten stehen: Kick-Achtel mit
    Crash, ein Muster, das in den Noten nicht vorkommt (sonst wäre die Lage mehrdeutig)."""
    notes = groove(24)
    score = make_score(notes)
    insert_at, extra = 6.0, 4.0  # 2 Takte à 2 s nach Score-Sekunde 6

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
    """Noten pausieren 2 Takte ("Drum Loop"), in der Aufnahme wird gespielt."""
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
    """Beat This! hört halbes Tempo: nur jeder zweite Beat wird gemeldet."""
    notes = groove(32)
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in notes], warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats[::2], warp), ft, flux)
    errors = [abs(a - warp(t)) for (t, _), a in zip(notes, result.mapped_times, strict=True)]
    assert max(errors) < 0.02


def test_wrong_reference_fails_quality():
    """Noten passen nicht zur Aufnahme (anderes Muster): Prüfung schlägt fehl."""
    notes = groove(32)
    other = [(t + 0.25, SNARE) for t, p in notes if p == KICK]  # Synkopen statt Groove
    score = make_score(notes)
    ft, flux = flux_for([(warp(t), p) for t, p in other], warp(score.beats[-1]) + 2, noise=0.05)
    result = align.align(score, beats_for(score.beats, warp), ft, flux)
    assert not result.quality.passed
    assert result.quality.reasons
