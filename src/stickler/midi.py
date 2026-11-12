"""Read MIDI: drum notes (channel 10) as (time s, GM pitch)."""

from __future__ import annotations

from pathlib import Path

import mido

DRUM_CHANNEL = 9  # channel 10, zero-based


def read_drum_hits(path: Path) -> list[tuple[float, int, int]]:
    """All note-ons on channel 10 as (time s, GM pitch, velocity), sorted by time."""
    hits: list[tuple[float, int, int]] = []
    now = 0.0
    for msg in mido.MidiFile(path):
        now += msg.time
        if msg.type == "note_on" and msg.velocity > 0 and msg.channel == DRUM_CHANNEL:
            hits.append((round(now, 6), msg.note, msg.velocity))
    return sorted(hits)


def read_drum_notes(path: Path) -> list[tuple[float, int]]:
    """All note-ons on channel 10, sorted by time; tempo changes are taken into account."""
    notes: list[tuple[float, int]] = []
    now = 0.0
    for msg in mido.MidiFile(path):
        now += msg.time
        if msg.type == "note_on" and msg.velocity > 0 and msg.channel == DRUM_CHANNEL:
            notes.append((round(now, 6), msg.note))
    return sorted(notes)
