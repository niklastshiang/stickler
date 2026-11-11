"""MIDI lesen: Schlagzeug-Noten (Kanal 10) als (Zeit s, GM-Pitch)."""

from __future__ import annotations

from pathlib import Path

import mido

DRUM_CHANNEL = 9  # Kanal 10, nullbasiert


def read_drum_notes(path: Path) -> list[tuple[float, int]]:
    """Alle Note-ons auf Kanal 10, nach Zeit sortiert; Tempowechsel werden berücksichtigt."""
    notes: list[tuple[float, int]] = []
    now = 0.0
    for msg in mido.MidiFile(path):
        now += msg.time
        if msg.type == "note_on" and msg.velocity > 0 and msg.channel == DRUM_CHANNEL:
            notes.append((round(now, 6), msg.note))
    return sorted(notes)
