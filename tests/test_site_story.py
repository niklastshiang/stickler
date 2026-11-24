"""The pictures of the website's "How it works" story (SPEC.md "Website", "Change 2026-11-22"):
made from the stored analysis of the example song by scripts/site_story.py."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("site_story", ROOT / "scripts" / "site_story.py")
assert _spec and _spec.loader
site_story = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site_story)


def test_the_loudness_is_one_value_per_column_with_the_loudest_at_one():
    rate = 10
    samples = [0.0] * 50 + [0.5] * 50 + [-1.0] * 50 + [0.25] * 50  # 20 s at 10 per second
    loudness = site_story.envelope(samples, rate, seconds=20, columns=4)
    assert loudness == [0.0, 0.5, 1.0, 0.25]


def test_only_the_first_seconds_hits_are_kept_in_the_clicks_groups():
    hits = [(0.5, 36, 100), (1.0, 38, 90), (2.0, 42, 80), (2.5, 45, 70), (21.0, 36, 100)]
    assert site_story.first_hits(hits, seconds=20) == [
        [0.5, "kick"],
        [1.0, "snare"],
        [2.0, "cymbals"],
        [2.5, "snare"],  # a tom goes with the snare, as its click does
    ]


def test_the_sheet_music_is_cut_below_its_second_system():
    svg = '<svg width="900px" height="2000px"><g/></svg>'
    boxes = {
        1: (50, 100, 200, 40),
        2: (250, 100, 200, 40),
        3: (50, 300, 400, 40),
        4: (50, 500, 400, 40),
    }
    cut, bars = site_story.first_systems(svg, boxes, systems=2)
    assert 'height="364px"' in cut and 'viewBox="0 0 900 364"' in cut
    assert list(bars) == ["1", "2", "3"]
    assert bars["3"] == [
        round(50 / 900, 4),
        round(300 / 364, 4),
        round(400 / 900, 4),
        round(40 / 364, 4),
    ]


def test_the_cut_keeps_verovios_scale():
    """Verovio draws in its own units inside a second <svg>; cut it by the same share."""
    svg = (
        '<svg width="900px" height="2000px" xmlns="http://www.w3.org/2000/svg">'
        '<svg class="definition-scale" viewBox="0 0 18000 40000"><g/></svg></svg>'
    )
    cut, _bars = site_story.first_systems(svg, {1: (50, 100, 200, 40)}, systems=1)
    assert 'viewBox="0 0 18000 3280"' in cut  # 164 of 2000 pixels


def test_the_cut_sheet_music_keeps_only_its_first_systems():
    svg = (
        '<svg width="900px" height="2000px" xmlns="http://www.w3.org/2000/svg">'
        '<g class="page-margin"><g class="system" id="s1"/><g class="system" id="s2"/>'
        '<g class="system" id="s3"/></g></svg>'
    )
    boxes = {1: (50, 100, 200, 40), 2: (50, 300, 200, 40), 3: (50, 500, 200, 40)}
    cut, _bars = site_story.first_systems(svg, boxes, systems=2)
    assert 'id="s1"' in cut and 'id="s2"' in cut and 'id="s3"' not in cut


def test_the_cut_has_no_tempo_mark_whose_note_needs_a_font_the_site_lacks():
    svg = (
        '<svg width="900px" height="2000px" xmlns="http://www.w3.org/2000/svg">'
        '<g class="system"><g class="tempo" id="t"><text>= 122</text></g></g></svg>'
    )
    cut, _bars = site_story.first_systems(svg, {1: (50, 100, 200, 40)}, systems=1)
    assert 'class="system"' in cut and 'class="tempo"' not in cut


def test_each_hit_is_a_dot_in_its_lane():
    data = {"seconds": 20, "loudness": [0.5, 1.0], "hits": [[0.0, "kick"], [10.0, "cymbals"]]}
    wave = site_story.waveform(data)
    dots = re.findall(r'<circle class="story-hit (\w+)" cx="([\d.]+)" cy="([\d.]+)"', wave)
    (kick, cymbals) = dots
    assert kick[0] == "kick" and float(kick[1]) == site_story.DOT  # whole, at the edge
    assert cymbals[0] == "cymbals" and float(cymbals[1]) == site_story.WIDTH / 2
    assert float(cymbals[2]) > float(kick[2])  # the cymbals' lane is below the kick's
    assert 'aria-hidden="true"' in wave


def test_no_picture_carries_a_style_attribute_the_sites_policy_would_block():
    """The site's Content-Security-Policy allows styles from its own files only."""
    data = {
        "seconds": 20,
        "loudness": [0.5, 1.0],
        "hits": [[0.0, "kick"]],
        "bars": {"1": [0.1, 0.1, 0.2, 0.2]},
    }
    assert all("style=" not in picture for picture in site_story.pictures(data).values())


def test_each_hit_appears_in_its_own_part_of_the_scroll_from_left_to_right():
    data = {"seconds": 20, "hits": [[0.0, "kick"], [10.0, "cymbals"]], "bars": {}}
    css = site_story.ranges(data)
    assert ".story-hit:nth-of-type(1) { animation-range: cover 20% cover 24%; }" in css
    assert ".story-hit:nth-of-type(2) { animation-range: cover 45% cover 49%; }" in css


def test_the_bar_marks_light_one_after_the_other_and_the_last_stays():
    data = {
        "hits": [],
        "bars": {"1": [0.1, 0.1, 0.2, 0.2], "2": [0.3, 0.1, 0.2, 0.2], "3": [0.1, 0.6, 0.4, 0.2]},
    }
    marks = re.findall(
        r"\.story-bar:nth-of-type\((\d)\) \{ animation-range: cover (\d+)% cover (\d+)%; \}",
        site_story.ranges(data),
    )
    assert marks == [("1", "20", "40"), ("2", "40", "60"), ("3", "60", "100")]


def test_a_page_without_a_place_for_a_picture_is_refused():
    with pytest.raises(ValueError, match="wave"):
        site_story.fill("<p>no story here</p>", {"wave": "<svg/>"})


def test_filling_twice_gives_the_same_page():
    page = "<div><!-- story:wave -->old<!-- /story:wave --></div>"
    once = site_story.fill(page, {"wave": "<svg>new</svg>"})
    assert once == "<div><!-- story:wave --><svg>new</svg><!-- /story:wave --></div>"
    assert site_story.fill(once, {"wave": "<svg>new</svg>"}) == once


def test_the_stored_data_is_the_example_songs_first_seconds():
    data = json.loads(site_story.DATA.read_text(encoding="utf-8"))
    assert data["song"] == "Fluffing a Duck.mp3" and data["seconds"] == 20
    assert len(data["loudness"]) == site_story.COLUMNS and max(data["loudness"]) == 1.0
    times = [t for t, _group in data["hits"]]
    assert times == sorted(times) and times[0] >= 0 and times[-1] < 20
    assert {group for _t, group in data["hits"]} == set(site_story.GROUPS)
    assert list(data["bars"]) == [str(n) for n in range(1, len(data["bars"]) + 1)]
    assert site_story.NOTES.read_text(encoding="utf-8").lstrip().startswith("<svg")


@pytest.mark.parametrize("page", site_story.PAGES, ids=["en", "de"])
def test_the_pages_hold_what_the_stored_data_draws(page):
    """Changing the data or the script without `site_story.py draw` fails here."""
    html = page.read_text(encoding="utf-8")
    drawn = site_story.pictures(json.loads(site_story.DATA.read_text(encoding="utf-8")))
    assert site_story.fill(html, drawn) == html


def test_the_stored_ranges_are_what_the_stored_data_gives():
    """Changing the data or the script without `site_story.py draw` fails here."""
    data = json.loads(site_story.DATA.read_text(encoding="utf-8"))
    assert site_story.RANGES.read_text(encoding="utf-8") == site_story.ranges(data)


def test_the_last_hit_keeps_its_whole_dot_inside_the_picture():
    data = {"seconds": 20, "loudness": [1.0], "hits": [[19.99, "kick"]]}
    (cx,) = re.findall(
        r'<circle[^>]*cx="([\d.]+)" cy="[\d.]+" r="(\d+)"', site_story.waveform(data)
    )
    assert float(cx[0]) + int(cx[1]) <= site_story.WIDTH


def test_the_cut_drops_the_embedded_music_font_the_kept_systems_do_not_use():
    svg = (
        '<svg width="900px" height="2000px" xmlns="http://www.w3.org/2000/svg">'
        "<style>@font-face { font-family: Leipzig; src: url(data:font/woff2;base64,AAAA); }</style>"
        '<g class="system"/></svg>'
    )
    cut, _bars = site_story.first_systems(svg, {1: (50, 100, 200, 40)}, systems=1)
    assert "@font-face" not in cut and "<style" not in cut


def test_sheet_music_without_bars_is_refused_with_a_reason():
    with pytest.raises(ValueError, match="no bars"):
        site_story.first_systems('<svg width="900px" height="2000px"/>', {}, systems=2)


def test_a_failing_page_leaves_every_file_as_it_was(tmp_path, monkeypatch):
    good, bad = tmp_path / "good.html", tmp_path / "bad.html"
    good.write_text(
        "<!-- story:wave --><!-- /story:wave --><!-- story:marks --><!-- /story:marks -->",
        encoding="utf-8",
    )
    bad.write_text("<p>no places</p>", encoding="utf-8")
    ranges = tmp_path / "story.css"
    monkeypatch.setattr(site_story, "PAGES", (good, bad))
    monkeypatch.setattr(site_story, "RANGES", ranges)
    with pytest.raises(ValueError):
        site_story.draw()
    assert not ranges.exists() and "<svg" not in good.read_text(encoding="utf-8")


@pytest.mark.parametrize("page", site_story.PAGES, ids=["en", "de"])
def test_the_sheet_musics_reserved_size_is_the_svgs(page):
    """The <img> keeps its space before it loads only if its width and height are the file's."""
    svg = site_story.NOTES.read_text(encoding="utf-8")
    width, height = re.search(r'<svg[^>]*width="(\d+)px" height="(\d+)px"', svg).groups()
    html = page.read_text(encoding="utf-8")
    assert f'story/notes.svg" alt="" width="{width}" height="{height}"' in html
