"""Playback decisions without GStreamer (SPEC.md, module `playback`)."""

from pathlib import Path

import pytest

from stickler import api
from stickler_app import paths, playback

# 6 song bars of 2 s; written bars 1 2 1 2 (a repeated phrase), then 3, then 4
BARS = [
    api.BarTime(0.0, 2.0, 1),
    api.BarTime(2.0, 4.0, 2),
    api.BarTime(4.0, 6.0, 1),
    api.BarTime(6.0, 8.0, 2),
    api.BarTime(8.0, 10.0, 3),
    api.BarTime(10.0, 12.0, 4),
]


@pytest.mark.parametrize(
    ("hear", "expected"),
    [("song", (0.8, 0.0)), ("hits", (0.0, 0.5)), ("both", (0.8, 0.5))],
)
def test_what_to_hear_mutes_one_source_or_none(hear, expected):
    assert playback.volumes(hear, song=0.8, hits=0.5) == expected


def test_a_bar_click_jumps_to_its_next_pass_then_back_to_the_first():
    assert playback.jump_target(BARS, 1, now=0.5) == 4.0  # the next pass of bar 1
    assert playback.jump_target(BARS, 1, now=5.0) == 0.0  # after its last pass: the first
    assert playback.jump_target(BARS, 3, now=0.0) == 8.0
    assert playback.jump_target(BARS, 3, now=9.0) == 8.0  # inside its only pass: its start
    assert playback.jump_target(BARS, 7, now=0.0) is None  # not in the song


def test_the_arrow_keys_go_one_song_bar_back_or_on():
    assert playback.step(BARS, now=5.0, by=1) == 6.0
    assert playback.step(BARS, now=5.0, by=-1) == 2.0
    assert playback.step(BARS, now=0.5, by=-1) == 0.0  # no bar before the first
    assert playback.step(BARS, now=11.0, by=1) == 10.0  # none after the last
    assert playback.step([], now=3.0, by=1) == 3.0


def test_the_bar_shows_the_time_and_the_song_bar():
    assert playback.clock(6.4) == "0:06"
    assert playback.clock(246.0) == "4:06"
    assert playback.clock(3725.0) == "1:02:05"
    assert playback.bar_label(BARS, 5.0) == "Bar 3 of 6"
    assert playback.bar_label(BARS, 99.0) == "Bar 6 of 6"
    assert playback.bar_label([], 1.0) == ""


def test_the_clicks_of_a_song_go_to_the_apps_cache(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    wav = paths.hits_path(Path("/music/a/Song.flac"), env)
    assert wav.parent == tmp_path / "stickler" / "hits" and wav.suffix == ".wav"
    assert wav.stem == paths.score_path(Path("/music/a/Song.flac"), env).stem
