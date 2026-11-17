"""The legend's names (module `legend`), without GTK."""

from stickler import notation
from stickler_app import legend


def _sheet(pitches):
    beats = [k * 0.5 for k in range(9)]
    notes = [(i * 0.5, p, 100) for i, p in enumerate(pitches)]
    return notation.engrave(notes, beats, beats[:-1:4]).musicxml


def test_every_position_of_the_staff_has_a_name():
    for staff in [*notation.STAFF.values(), notation.OTHER]:
        assert legend.NAMES[staff]


def test_the_cymbal_position_is_named_cymbal_not_crash():
    """ADTOF writes every cymbal there (owner, 2026-11-17)."""
    assert legend.NAMES[notation.STAFF[49]] == "Cymbal"


def test_a_sheet_gets_its_positions_with_their_names_from_the_top_down():
    assert legend.entries(_sheet([36, 38, 42])) == [
        (notation.STAFF[42], "Hi-Hat"),
        (notation.STAFF[38], "Snare"),
        (notation.STAFF[36], "Bass Drum"),
    ]


def test_the_legend_score_names_the_sheet_s_positions():
    xml = legend.score(_sheet([36, 49]))
    assert xml is not None and "<text>Cymbal</text>" in xml and "<text>Bass Drum</text>" in xml


def test_a_sheet_without_hits_has_no_legend_score():
    assert legend.score(_sheet([])) is None


def test_the_names_follow_the_app_s_language(monkeypatch):
    from stickler_app import i18n

    monkeypatch.setattr(i18n, "_", lambda text: {"Cymbal": "Becken"}.get(text, text))
    monkeypatch.setattr(legend, "_", i18n._)
    assert legend.entries(_sheet([49]))[0][1] == "Becken"
