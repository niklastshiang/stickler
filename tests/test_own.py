"""Tests for the own-songs dataset (references/own/*.yaml + data/own/<song>/)."""

import json

import pytest

from stickler.datasets import own


@pytest.fixture
def layout(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    refs, data = tmp_path / "references", tmp_path / "data"
    refs.mkdir()
    (tmp_path / "home" / "Musik").mkdir(parents=True)
    (tmp_path / "home" / "Musik" / "a.mp3").write_bytes(b"x")
    (refs / "song_a.yaml").write_text(
        'title: "A"\naudio: "~/Musik/a.mp3"\nexclude: [[10, 20]]\n', encoding="utf-8"
    )
    (refs / "song_b.yaml").write_text('title: "B"\naudio: "/fehlt.mp3"\n', encoding="utf-8")
    return refs, data, tmp_path / "home"


def test_songs_are_read_with_expanded_paths(layout):
    refs, data, home = layout
    songs = {s.id: s for s in own.songs(refs, data)}
    assert songs["song_a"].audio == home / "Musik" / "a.mp3"
    assert songs["song_a"].score == data / "own" / "song_a" / "score.mid"
    assert songs["song_a"].exclude == ((10.0, 20.0),)
    assert songs["song_b"].exclude == ()


def test_only_passed_alignments_become_tracks(layout):
    refs, data, home = layout
    a, b = sorted(own.songs(refs, data), key=lambda s: s.id)
    own.save_alignment(
        a,
        notes=[(1.0, 36), (2.0, 38)],
        excluded=[(10.0, 20.0)],
        quality={"coverage": 0.99},
        reasons=[],
        shift=0.01,
    )
    own.save_alignment(
        b, notes=[(1.0, 36)], excluded=[], quality={}, reasons=["too poor"], shift=0.0
    )
    tracks = own.tracks(refs, data)
    assert [t.id for t in tracks] == ["song_a"]
    t = tracks[0]
    assert t.reference_notes() == [(1.0, 36), (2.0, 38)]
    assert t.excluded == ((10.0, 20.0),)
    assert t.mix == home / "Musik" / "a.mp3" and t.drums is None


def test_alignment_file_is_readable_json(layout):
    refs, data, _ = layout
    song = own.songs(refs, data)[0]
    path = own.save_alignment(
        song, notes=[], excluded=[(5.0, float("inf"))], quality={}, reasons=[], shift=0.0
    )
    saved = json.loads(path.read_text())
    assert saved["excluded"] == [[5.0, None]] and saved["passed"] is True
    assert own.load_alignment(song)["excluded"] == [(5.0, float("inf"))]


def test_approval_by_ear_overrides_failed_checks(layout):
    refs, data, _ = layout
    (refs / "song_c.yaml").write_text(
        'title: "C"\naudio: "/c.mp3"\napproved_by_ear: "bass bleed fools the check"\n',
        encoding="utf-8",
    )
    song = next(s for s in own.songs(refs, data) if s.id == "song_c")
    assert song.approved_by_ear == "bass bleed fools the check"
    own.save_alignment(
        song,
        notes=[(1.0, 36)],
        excluded=[],
        quality={},
        reasons=["explained"],
        shift=0.0,
        approved_by_ear=song.approved_by_ear,
    )
    saved = own.load_alignment(song)
    assert saved["passed"] is True and saved["reasons"] == ["explained"]
    assert saved["approved_by_ear"] == "bass bleed fools the check"
    assert "song_c" in [t.id for t in own.tracks(refs, data)]
