"""From song time (and from a click) to the marked bar (SPEC.md, module `sheet-view`)."""

from stickler import notation
from stickler_gtk.logic import engraving, marker

KICK = 36
BEATS = [k * 0.5 for k in range(33)]  # 8 bars of 2 s
DOWNBEATS = BEATS[:-1:4]


def _song(notes, repeats=True):
    e = notation.engrave(notes, BEATS, DOWNBEATS, repeats=repeats)
    return e.bars, engraving.engrave(e.musicxml, width=800)


def _kick_in(bars_with_hits):
    return [(b * 2.0 + k * 0.5, KICK + (b % 2) * 2, 100) for b in bars_with_hits for k in range(4)]


def test_a_time_marks_the_written_bar_of_the_song_bar_sounding_then():
    bar_map, pages = _song(_kick_in(range(8)), repeats=False)
    assert marker.written_at(bar_map, 0.0) == 1
    assert marker.written_at(bar_map, 3.99) == 2
    assert marker.written_at(bar_map, 4.0) == 3
    assert marker.written_at(bar_map, 15.9) == 8


def test_no_bar_sounds_before_the_first_or_after_the_last():
    bar_map, _ = _song(_kick_in(range(8)))
    assert marker.written_at(bar_map, -0.1) is None
    assert marker.written_at(bar_map, 16.0) is None
    assert marker.written_at([], 1.0) is None


def test_inside_repeat_signs_every_pass_marks_the_same_written_bar():
    same = [(b * 2.0 + k * 0.5, KICK, 100) for b in range(8) for k in range(4)]
    bar_map, pages = _song(same)
    assert {marker.written_at(bar_map, b * 2.0 + 1) for b in range(8)} == {1}
    page, box = marker.locate(pages, 1)
    assert page == 0 and box == pages[0].bars[1]


def test_a_bar_inside_a_multi_measure_rest_marks_the_rest():
    bar_map, pages = _song(_kick_in(range(2, 8)))  # bars 1 and 2 empty
    assert marker.written_at(bar_map, 2.5) == 1
    assert marker.locate(pages, 2) == marker.locate(pages, 1)  # 2 has no rectangle of its own


def test_a_bar_number_the_engraving_does_not_know_marks_nothing():
    _, pages = _song(_kick_in(range(8)))
    assert marker.locate(pages, -5) is None
    assert marker.locate([], 1) is None


def test_a_click_finds_the_bar_under_it():
    _, pages = _song(_kick_in(range(8)), repeats=False)
    box = pages[0].bars[3]
    assert marker.bar_at_point(pages[0], box.x + box.width / 2, box.y + box.height / 2) == 3
    assert marker.bar_at_point(pages[0], -10, -10) is None
