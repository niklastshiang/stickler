"""Recent songs (design screen 4): newest first, ten at most, kept across restarts."""

from datetime import date
from pathlib import Path

from stickler_app import recent


def _song(name, opened=date(2026, 11, 14)):
    return recent.Recent(Path(f"/music/{name}.flac"), name.title(), "Band", opened)


def test_a_song_opened_again_moves_to_the_top_once():
    songs = [_song("a"), _song("b")]
    again = recent.add(songs, _song("b", date(2026, 11, 15)))
    assert [s.path.stem for s in again] == ["b", "a"]
    assert again[0].opened == date(2026, 11, 15)


def test_only_the_newest_ten_are_kept():
    songs = []
    for k in range(12):
        songs = recent.add(songs, _song(f"s{k}"))
    assert len(songs) == recent.LIMIT == 10
    assert songs[0].path.stem == "s11" and songs[-1].path.stem == "s2"


def test_a_song_can_be_removed():
    songs = [_song("a"), _song("b")]
    assert [s.path.stem for s in recent.remove(songs, Path("/music/a.flac"))] == ["b"]


def test_the_list_survives_a_restart(tmp_path):
    store = tmp_path / "stickler" / "recent.json"
    songs = [_song("a"), _song("b", date(2026, 11, 12))]
    recent.save(store, songs)
    assert recent.load(store) == songs


def test_a_missing_or_damaged_store_starts_an_empty_list(tmp_path):
    assert recent.load(tmp_path / "none.json") == []
    damaged = tmp_path / "recent.json"
    damaged.write_text('[{"path": "/a.flac", "title"', encoding="utf-8")
    assert recent.load(damaged) == []
    damaged.write_text('{"not": "a list"}', encoding="utf-8")
    assert recent.load(damaged) == []
    damaged.write_text('[{"path": "/a.flac"}, 3]', encoding="utf-8")
    assert recent.load(damaged) == []


def test_the_store_lives_in_the_xdg_data_folder(tmp_path):
    assert (
        recent.store_path({"XDG_DATA_HOME": str(tmp_path)}) == tmp_path / "stickler" / "recent.json"
    )
    assert recent.store_path({"HOME": str(tmp_path)}) == (
        tmp_path / ".local" / "share" / "stickler" / "recent.json"
    )


def test_rows_say_who_played_it_and_when_and_mark_missing_files():
    today = date(2026, 11, 15)
    songs = [
        _song("a", today),
        _song("b", date(2026, 11, 14)),
        _song("c", date(2026, 11, 12)),
        recent.Recent(Path("/music/d.flac"), "D", "", today),
    ]
    rows = recent.rows(songs, today=today, exists=lambda p: p.stem != "c")
    assert [r.title for r in rows] == ["A", "B", "C", "D"]
    assert rows[0].detail == "Band · opened today"
    assert rows[1].detail == "Band · opened yesterday"
    assert rows[2].missing and rows[2].detail == "Band · file not found"
    assert rows[3].detail == "opened today" and not rows[3].missing
    assert "12" in recent.rows([songs[2]], today=today, exists=lambda p: True)[0].detail


def test_a_finished_song_is_noted_with_todays_date():
    song = recent.opened_now(Path("/music/eye.flac"), "Eye of the Tiger", "Survivor")
    assert song == recent.Recent(
        Path("/music/eye.flac"), "Eye of the Tiger", "Survivor", date.today()
    )


# Release 10 (SPEC.md "keep and remove", scope A3): songs found again by their content


def test_a_moved_song_replaces_its_old_entry(tmp_path):
    old = recent.Recent(Path("/old/song.mp3"), "Song", "Band", date(2026, 11, 1), "abc")
    other = recent.Recent(Path("/x/other.mp3"), "Other", "Band", date(2026, 11, 2), "def")
    moved = recent.Recent(Path("/new/song.mp3"), "Song", "Band", date(2026, 11, 22), "abc")
    assert recent.add([other, old], moved) == [moved, other]


def test_the_digest_is_kept_and_old_lists_load_without_one(tmp_path):
    store = tmp_path / "recent.json"
    song = recent.Recent(Path("/a/song.mp3"), "Song", "Band", date(2026, 11, 22), "abc")
    recent.save(store, [song])
    assert recent.load(store) == [song]
    store.write_text(
        '[{"path": "/b.mp3", "title": "B", "artist": "", "opened": "2026-11-01"}]', encoding="utf-8"
    )
    (loaded,) = recent.load(store)
    assert loaded.path == Path("/b.mp3") and loaded.digest == ""
