"""The legend's names (SPEC.md, module `legend`): what each staff position of a sheet is called,
in the app's language, and the legend's score for a sheet. No GTK; `stickler.notation` knows the
positions and writes the score, this module only names them."""

from __future__ import annotations

from stickler import notation
from stickler.notation import OTHER, STAFF, Staff
from stickler_app.i18n import N_, _

# One name per staff position. A5 is where ADTOF writes every cymbal, so it is "Cymbal", not
# "Crash" (owner, 2026-11-17).
NAMES: dict[Staff, str] = {
    STAFF[52]: N_("China"),
    STAFF[49]: N_("Cymbal"),
    STAFF[42]: N_("Hi-Hat"),
    STAFF[46]: N_("Open Hi-Hat"),
    STAFF[51]: N_("Ride"),
    STAFF[53]: N_("Ride Bell"),
    STAFF[55]: N_("Splash"),
    STAFF[48]: N_("High Tom"),
    STAFF[45]: N_("Mid Tom"),
    STAFF[38]: N_("Snare"),
    STAFF[37]: N_("Side Stick"),
    OTHER: N_("Other Percussion"),
    STAFF[41]: N_("Floor Tom"),
    STAFF[36]: N_("Bass Drum"),
    STAFF[44]: N_("Pedal Hi-Hat"),
}


def entries(musicxml: str) -> list[tuple[Staff, str]]:
    """The sheet's positions from the top of the staff down, each with its name."""
    return [(staff, _(NAMES[staff])) for staff in notation.legend_positions(musicxml)]


def score(musicxml: str) -> str | None:
    """The legend's MusicXML for a sheet, or None when the sheet has no hits."""
    found = entries(musicxml)
    if not found:
        return None
    return notation.legend_musicxml([s for s, _name in found], [name for _s, name in found])
