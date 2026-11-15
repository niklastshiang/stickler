"""Engraving with Verovio (SPEC.md, module `sheet-view`): pages for a width and zoom, and for
each written bar its page and rectangle, taken from the staff lines."""

import pytest

from stickler import notation
from stickler_gtk.logic import engraving

KICK, SNARE, HAT = 36, 38, 42
BEATS = [k * 0.5 for k in range(33)]  # 8 bars of 4/4 plus the closing beat
DOWNBEATS = BEATS[:-1:4]


def groove(bars=8):
    notes = []
    for bar in range(bars):
        t0 = bar * 2.0
        notes += [(t0 + k * 0.25, HAT, 90) for k in range(8)]
        notes += [(t0, KICK, 100), (t0 + 1.0, KICK, 100), (t0 + 0.5, SNARE, 100)]
        notes.append((t0 + 1.5, SNARE + (bar % 2), 100))  # alternating, so nothing repeats
    return notes


def _xml(notes=None, beats=BEATS, downbeats=DOWNBEATS, **kw):
    return notation.engrave(groove() if notes is None else notes, beats, downbeats, **kw).musicxml


def _written(musicxml: str) -> list[int]:
    import re

    return [int(n) for n in re.findall(r'<measure number="(\d+)"', musicxml)]


def test_every_written_bar_gets_one_rectangle_on_a_page_as_wide_as_asked():
    xml = _xml()
    pages = engraving.engrave(xml, width=800)
    assert pages and all(p.width == pytest.approx(800, abs=1) for p in pages)
    bars = {n: (k, box) for k, p in enumerate(pages) for n, box in p.bars.items()}
    assert sorted(bars) == _written(xml) == list(range(1, 9))
    for k, box in bars.values():
        page = pages[k]
        assert box.x >= 0 and box.x + box.width <= page.width + 1
        assert box.y >= 0 and box.y + box.height <= page.height + 1
        assert box.width > 0 and box.height > 0


def test_bars_of_a_system_follow_left_to_right():
    pages = engraving.engrave(_xml(), width=800)
    boxes = [pages[0].bars[n] for n in sorted(pages[0].bars)]
    systems = {}
    for box in boxes:
        systems.setdefault(round(box.y), []).append(box)
    assert len(systems) >= 2  # 8 bars do not fit one line at 800 px
    for line in systems.values():
        assert all(a.x + a.width <= b.x + 1 for a, b in zip(line, line[1:], strict=False))


def test_zoom_makes_the_staff_taller_at_the_same_width():
    xml = _xml()
    normal = engraving.engrave(xml, width=800)[0].bars[1]
    double = engraving.engrave(xml, width=800, zoom=2.0)[0].bars[1]
    assert double.height == pytest.approx(2 * normal.height, rel=0.05)


def test_the_rectangle_spans_the_staff_and_some_room_around_it():
    page = engraving.engrave(_xml(), width=800)[0]
    box = page.bars[1]
    staff = engraving.STAFF_UNITS * page.scale  # five lines, four spaces
    assert box.height == pytest.approx(staff * (1 + 2 * engraving.PAD), rel=0.01)


def test_a_pickup_is_bar_zero():
    beats = [k * 0.5 for k in range(19)]
    notes = [(0.0, SNARE, 100)] + [(t, KICK, 100) for t in (1.0, 3.0, 5.0, 7.0)]
    xml = _xml(notes, beats, beats[2:-1:4])
    bars = engraving.engrave(xml, width=800)[0].bars
    assert sorted(bars) == [0, 1, 2, 3, 4]


def test_a_multi_measure_rest_is_one_rectangle_at_its_first_bar():
    notes = [n for n in groove() if n[0] >= 4.0]  # bars 1 and 2 empty
    bars = engraving.engrave(_xml(notes), width=800)[0].bars
    assert 1 in bars and 2 not in bars and 3 in bars


def test_repeated_bars_are_engraved_once():
    notes = [n for n in groove() if n[1] != SNARE + 1] + [
        (b * 2.0 + 1.5, SNARE, 100) for b in range(8)
    ]
    xml = _xml(notes, repeats=True)
    bars = engraving.engrave(xml, width=800)[0].bars
    assert sorted(bars) == _written(xml) == [1]


def test_a_tiny_width_still_engraves():
    pages = engraving.engrave(_xml(), width=120)
    assert sum(len(p.bars) for p in pages) == 8


def test_verovio_writes_numbers_with_a_point_whatever_the_users_locale():
    """GTK sets the user's locale; under German Verovio wrote "scale(0,72, 0,72)", which
    librsvg rejects, so every notehead was lost. Engraving runs Verovio in the C locale."""
    import locale

    before = locale.setlocale(locale.LC_NUMERIC)
    with engraving.c_numbers():
        assert locale.setlocale(locale.LC_NUMERIC) == "C"
    assert locale.setlocale(locale.LC_NUMERIC) == before
    for comma in ("de_DE.UTF-8", "de_DE.utf8", "fr_FR.UTF-8", "fr_FR.utf8"):
        try:
            locale.setlocale(locale.LC_NUMERIC, comma)
        except locale.Error:
            continue  # not installed here (CI has few locales); the guard above still holds
        try:
            svg = engraving.engrave(_xml(), width=800)[0].svg
        finally:
            locale.setlocale(locale.LC_NUMERIC, before)
        assert "scale(0.72, 0.72)" in svg and "scale(0,72" not in svg
        break
