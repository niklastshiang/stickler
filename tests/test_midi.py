"""Tests for reading drum MIDI files."""

import mido

from stickler import midi


def test_read_drum_hits_keeps_velocity(tmp_path):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
    track.append(mido.Message("note_on", channel=9, note=38, velocity=35, time=480))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=0))  # not drums
    track.append(mido.Message("note_on", channel=9, note=38, velocity=0, time=10))  # note off
    path = tmp_path / "d.mid"
    mid.save(path)
    assert midi.read_drum_hits(path) == [(0.0, 36, 100), (0.5, 38, 35)]
    assert midi.read_drum_notes(path) == [(0.0, 36), (0.5, 38)]
