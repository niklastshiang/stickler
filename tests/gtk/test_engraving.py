"""Engraving with Verovio (SPEC.md, module `sheet-view`): pages for a width and zoom, and for
each written bar its page and rectangle, taken from the staff lines."""

import re

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


def test_print_pages_are_a4_with_the_title_on_the_first():
    xml = notation.engrave(
        groove(), BEATS, DOWNBEATS, title="Groove Song", artist="The Band"
    ).musicxml
    pages = engraving.a4_pages(xml)
    assert len(pages) >= 1
    for page in pages:
        assert page.height / page.width == pytest.approx(297 / 210, rel=0.01)
    assert "Groove Song" in pages[0].svg and "The Band" in pages[0].svg
    assert sum(len(p.bars) for p in pages) == 8


def test_the_tempo_mark_keeps_its_spaces_around_the_equals_sign():
    """Verovio writes " = " with no-break spaces; librsvg drops a leading one (even with
    xml:space="preserve") and a trailing one unless preserved, so "♩ = 109" read "♩=109"
    (owner, 2026-11-15). The leading space becomes an explicit shift (dx) of about one space,
    the trailing one is preserved."""

    svg = engraving.engrave(_xml(), width=800)[0].svg
    tempo = re.search(r'class="tempo".*?</g>', svg, re.S).group(0)
    equals = re.search(
        '<tspan font-size="(\\d+)px" dx="([\\d.]+)" xml:space="preserve">=\u00a0</tspan>', tempo
    )
    assert equals, tempo
    assert float(equals.group(2)) == pytest.approx(
        engraving.SPACE_EM * int(equals.group(1)), rel=0.01
    )


# --- The legend on page 1 (module `legend`) ---------------------------------------------------


def _long(bars=120, **kw):
    beats = [k * 0.5 for k in range(bars * 4 + 1)]
    return notation.engrave(groove(bars), beats, beats[:-1:4], **kw).musicxml


def _legend(xml):
    from stickler_gtk.logic import legend

    return legend.score(xml)


def _staff_top(page):
    return min(b.y for b in page.bars.values()) + engraving.PAD * engraving.STAFF_UNITS * page.scale


@pytest.mark.parametrize("artist", ["The Band", ""])
def test_the_legend_sits_under_the_band_and_above_the_music(artist):
    xml = _long(title="Groove Song", artist=artist)
    plain = engraving.a4_pages(xml)
    pages = engraving.a4_pages(xml, legend=_legend(xml))
    box = engraving.legend_box(pages[0])
    assert box is not None
    assert box.y >= engraving.header_bottom(pages[0])
    above = _staff_top(plain[0]) - engraving.header_bottom(plain[0])  # tempo, cymbals
    assert box.y + box.height <= _staff_top(pages[0]) - above + 1
    assert "Bass Drum" in pages[0].svg and "Hi-Hat" in pages[0].svg


def test_only_page_one_gets_the_legend_and_later_pages_keep_their_top_margin():
    xml = _long(title="Groove Song", artist="The Band")
    plain = engraving.a4_pages(xml)
    pages = engraving.a4_pages(xml, legend=_legend(xml))
    assert len(plain) >= 2 and len(pages) in (len(plain), len(plain) + 1)
    assert all(engraving.legend_box(p) is None for p in pages[1:])
    assert _staff_top(pages[1]) == pytest.approx(_staff_top(plain[1]), abs=1)
    assert sum(len(p.bars) for p in pages) == sum(len(p.bars) for p in plain)


def test_the_room_never_reaches_the_musicxml_it_was_given():
    xml = _long(bars=8, title="Groove Song", artist="The Band")
    before = str(xml)
    engraving.a4_pages(xml, legend=_legend(xml))
    assert xml == before and " </credit-words>" not in xml


def test_without_a_legend_the_pages_are_as_before():
    xml = _long(bars=8, title="Groove Song", artist="The Band")

    def plain(pages):  # Verovio draws new ids on every render
        ids = {i.rsplit("-", 1)[-1] for p in pages for i in re.findall(r' id="([^"]+)"', p.svg)}
        found = re.compile(rf"\b({'|'.join(ids)})\b")
        return [found.sub("ID", p.svg) for p in pages]

    assert plain(engraving.a4_pages(xml, legend=None)) == plain(engraving.a4_pages(xml))


def test_every_position_with_the_longest_names_stays_one_line_on_the_page():
    """The longest name of each position across the app's languages (po/*.po): one staff,
    drawn smaller rather than squeezed when it is wider than the page."""
    from pathlib import Path

    from stickler_gtk.logic import legend

    po = Path(__file__).resolve().parents[2] / "po"
    longest = {name: name for name in legend.NAMES.values()}
    for catalogue in po.glob("*.po"):
        pairs = re.findall(r'^msgid "(.+)"\nmsgstr "(.+)"$', catalogue.read_text(), re.M)
        for msgid, msgstr in pairs:
            if msgid in longest and len(msgstr) > len(longest[msgid]):
                longest[msgid] = msgstr
    positions = list(legend.NAMES)
    xml = notation.legend_musicxml(positions, [longest[legend.NAMES[s]] for s in positions])
    sheet = _long(bars=8, title="Groove Song", artist="The Band")
    page = engraving.a4_pages(sheet, legend=xml)[0]
    box = engraving.legend_box(page)
    assert page.svg.count('class="system"') > 1  # the legend's one and the music's
    legend_svg = page.svg[page.svg.index('class="legend"') :]
    assert legend_svg.count('class="system"') == 1
    assert box.x + box.width <= page.width
    assert box.width == pytest.approx(page.width, abs=1)  # 15 long names fill the page


def test_a_short_legend_keeps_the_size_of_the_music():
    xml = _long(bars=8, title="Groove Song", artist="The Band")
    page = engraving.a4_pages(xml, legend=_legend(xml))[0]
    box = engraving.legend_box(page)
    settings = engraving.options(engraving.A4[0], engraving.PAGE_HEIGHT, engraving.BASE_SCALE)
    alone = engraving.render(_legend(xml), settings)[0]
    assert box.width < page.width / 2
    assert box.height == pytest.approx(alone.height, abs=0.1)
