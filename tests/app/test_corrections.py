"""A song's corrections without GTK (SPEC.md, module `corrections`)."""

import json
from pathlib import Path

from stickler import api
from stickler_app import corrections

DETECTED = api.Corrections()


def test_nothing_is_corrected_until_a_control_changes_something():
    assert not corrections.corrected(DETECTED)
    assert corrections.corrected(corrections.with_tempo(DETECTED, "half"))
    assert not corrections.corrected(corrections.with_tempo(DETECTED, "normal"))
    assert corrections.corrected(corrections.with_simplify(DETECTED, False))
    assert corrections.corrected(corrections.with_repeats(DETECTED, False))


def test_beats_per_bar_stay_from_1_to_12_and_keep_the_first_one_in_the_bar():
    assert corrections.with_beats(DETECTED, 3).beats_per_bar == 3
    assert corrections.with_beats(DETECTED, 0).beats_per_bar == 1
    assert corrections.with_beats(DETECTED, 13).beats_per_bar == 12
    late = api.Corrections(first_downbeat=4)
    assert corrections.with_beats(late, 3).first_downbeat == 1  # beat 4 of 3 is beat 1


def test_the_first_one_stays_within_the_bar():
    assert corrections.with_first_one(DETECTED, 2, beats_per_bar=4).first_downbeat == 2
    assert corrections.with_first_one(DETECTED, 0, beats_per_bar=4).first_downbeat == 1
    assert corrections.with_first_one(DETECTED, 9, beats_per_bar=4).first_downbeat == 4


def test_a_new_tempo_counts_the_first_one_anew():
    """The first one is counted on the corrected beats; after half or double they differ."""
    moved = api.Corrections(first_downbeat=3, beats_per_bar=3)
    halved = corrections.with_tempo(moved, "half")
    assert (halved.tempo, halved.first_downbeat, halved.beats_per_bar) == ("half", None, 3)


def test_the_first_one_reads_as_a_beat():
    assert corrections.beat_label(2) == "Beat 2"


def test_the_store_keeps_each_songs_corrections(tmp_path):
    store = tmp_path / "corrections.json"
    eye, other = Path("/music/eye.flac"), Path("/music/other.flac")
    assert corrections.load(store) == {}
    fixed = api.Corrections(tempo="half", beats_per_bar=3, first_downbeat=2, repeats=False)
    corrections.remember(store, eye, fixed)
    corrections.remember(store, other, api.Corrections(simplify=False))
    assert corrections.load(store)[eye] == fixed
    corrections.remember(store, eye, DETECTED)  # Back to Detected removes the entry
    assert set(corrections.load(store)) == {other}
    assert not store.with_suffix(".json.part").exists()


def test_a_broken_entry_is_dropped_alone(tmp_path):
    store = tmp_path / "corrections.json"
    store.write_text(
        json.dumps(
            {
                "/music/good.flac": {"tempo": "double"},
                "/music/bad.flac": {"tempo": "triple"},
                "/music/worse.flac": "half",
                "/music/zero.flac": {"beats_per_bar": 0},
            }
        ),
        encoding="utf-8",
    )
    assert corrections.load(store) == {Path("/music/good.flac"): api.Corrections(tempo="double")}
    store.write_text("not json", encoding="utf-8")
    assert corrections.load(store) == {}


def test_the_store_lives_next_to_the_recent_songs(tmp_path):
    assert corrections.store_path({"XDG_DATA_HOME": str(tmp_path)}) == (
        tmp_path / "stickler" / "corrections.json"
    )


# Release 10 (SPEC.md "keep and remove", scope A3): songs found again by their content


def test_a_moved_song_keeps_its_corrections(tmp_path):
    store = tmp_path / "corrections.json"
    fix = api.Corrections(tempo="half")
    corrections.remember(store, Path("/old/song.mp3"), fix, digest="abc")
    assert corrections.lookup(store, Path("/new/song.mp3"), "abc") == fix
    # the entry moved with the song: the new path is remembered, the old one is gone
    assert set(json.loads(store.read_text(encoding="utf-8"))) == {"/new/song.mp3"}
    assert corrections.lookup(store, Path("/new/song.mp3"), "abc") == fix


def test_an_entry_without_a_digest_gets_one_when_its_song_is_opened(tmp_path):
    store = tmp_path / "corrections.json"
    store.write_text(
        json.dumps({"/a/song.mp3": {"tempo": "double"}}), encoding="utf-8"
    )  # before Release 10
    assert corrections.lookup(store, Path("/a/song.mp3"), "abc") == api.Corrections(tempo="double")
    assert json.loads(store.read_text(encoding="utf-8"))["/a/song.mp3"]["digest"] == "abc"


def test_an_unknown_song_has_the_detected_values_and_changes_nothing(tmp_path):
    store = tmp_path / "corrections.json"
    corrections.remember(store, Path("/a/song.mp3"), api.Corrections(tempo="half"), digest="abc")
    before = store.read_text(encoding="utf-8")
    assert corrections.lookup(store, Path("/b/other.mp3"), "xyz") == DETECTED
    assert store.read_text(encoding="utf-8") == before


def test_the_digest_is_not_a_correction():
    assert corrections._parse({"tempo": "half", "digest": "abc"}) == api.Corrections(tempo="half")
