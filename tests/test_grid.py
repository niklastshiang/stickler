"""Tests for scoring the end product: notes snapped to the beat grid like the sheet music."""

from pathlib import Path

import pytest

from stickler import grid
from stickler.notation import QNote
from stickler.runner import Record

BEATS = [0.0, 0.5, 1.0, 1.5, 2.0]  # 120 BPM


def test_grid_positions_map_back_to_times():
    q = [QNote(0, (0, 4), 36, 100), QNote(1, (2, 4), 38, 100), QNote(2, (1, 3), 42, 100)]
    assert grid.to_times(q, BEATS) == [(0.0, 36), (0.75, 38), (1.0 + 0.5 / 3, 42)]


def test_snap_moves_notes_onto_the_grid():
    notes = [(0.02, 36), (0.76, 38), (1.13, 42)]  # 1.13 → nearest sixteenth 1.125
    assert grid.snap(notes, BEATS) == [(0.0, 36), (0.75, 38), (1.125, 42)]


def test_snap_drops_notes_outside_the_beats():
    assert grid.snap([(3.0, 36)], BEATS) == []


def _record(track, trans="adtof", sep="none", error=None):
    return Record(
        "own",
        track,
        sep,
        trans,
        None,
        Path(f"{track}.mid"),
        {"seconds": 1.0},
        {"seconds": 2.0},
        error,
    )


def test_grid_records_for_the_configured_pipelines():
    records = [_record("a"), _record("b"), _record("a", trans="adt_str", sep="demucs")]
    beats = {("own", "a"): grid.BeatGrid(BEATS, [0.0, 2.0]), ("own", "b"): None}
    out = grid.grid_records(records, [("none", "adtof")], beats, read_notes=lambda p: [(0.02, 36)])
    assert [(r.track, r.transcriber, r.ok) for r in out] == [
        ("a", "adtof@grid", True),
        ("b", "adtof@grid", False),
    ]
    assert list(out[0].notes) == [(0.0, 36)] and "beats" in out[1].error
    assert out[0].transcriber_meta["seconds"] == 2.0


def test_parse_grid_pipelines():
    assert grid.parse_pipelines(["none+adtof", "combo+quality"]) == [
        ("none", "adtof"),
        ("combo", "quality"),
    ]
    with pytest.raises(ValueError, match="separator\\+transcriber"):
        grid.parse_pipelines(["adtof"])


def _groove_bar(bar: int, *, skip_hh_on=None, extra=None):
    """4/4 bar of 4 beats: kick on 1 and 3, snare on 2 and 4, hi-hat eighths."""
    b0 = bar * 4
    notes = []
    for beat in range(4):
        notes.append(QNote(b0 + beat, (0, 4), 36 if beat % 2 == 0 else 38, 100))
        for slot in (0, 2):
            if (beat, slot) != skip_hh_on:
                notes.append(QNote(b0 + beat, (slot, 4), 42, 100))
    if extra:
        notes.append(QNote(b0 + extra[0], extra[1], extra[2], 100))
    return notes


def test_consensus_adds_a_hit_missing_in_one_of_many_equal_bars():
    notes = [
        n for bar in range(6) for n in _groove_bar(bar, skip_hh_on=(1, 2) if bar == 3 else None)
    ]
    downbeats = list(range(0, 24, 4))
    out = grid.consensus(notes, downbeats, similarity=0.7, add=0.6, remove=0.0)
    assert QNote(13, (2, 4), 42, 100) in out and len(out) == len(notes) + 1


def test_consensus_removes_a_lone_extra_hit_only_when_asked():
    notes = [
        n for bar in range(6) for n in _groove_bar(bar, extra=(1, (1, 4), 45) if bar == 2 else None)
    ]
    downbeats = list(range(0, 24, 4))
    kept = grid.consensus(notes, downbeats, similarity=0.7, add=1.1, remove=0.0)
    assert QNote(9, (1, 4), 45, 100) in kept
    removed = grid.consensus(notes, downbeats, similarity=0.7, add=1.1, remove=0.3)
    assert QNote(9, (1, 4), 45, 100) not in removed and len(removed) == len(notes) - 1


def test_consensus_leaves_dissimilar_bars_alone():
    fill = [QNote(20 + b, (s, 4), 45, 100) for b in range(4) for s in range(4)]
    notes = [n for bar in range(5) for n in _groove_bar(bar)] + fill
    out = grid.consensus(notes, list(range(0, 24, 4)), similarity=0.7, add=0.6, remove=0.3)
    assert sorted(out) == sorted(notes)


def test_triplet_and_sixteenth_positions_are_compared_on_one_grid():
    assert grid._slot((2, 4)) == grid._slot((6, 12)) and grid._slot((1, 3)) == 4


def test_grid_records_add_a_consensus_variant():
    beats = [i * 0.5 for i in range(25)]  # 24 beats, 6 bars of 4/4
    notes = [(b * 0.5, 36) for b in range(24) if b != 13]  # kick on every beat, one missed
    params = grid.Consensus(similarity=0.7, add=0.6, remove=0.0)
    out = grid.grid_records(
        [_record("a")],
        [("none", "adtof")],
        {("own", "a"): grid.BeatGrid(beats, [i * 2.0 for i in range(6)])},
        read_notes=lambda p: notes,
        consensus_params=params,
    )
    assert [r.transcriber for r in out] == ["adtof@grid", "adtof@rep"]
    assert len(out[0].notes) == 23 and len(out[1].notes) == 24


def test_downbeat_times_become_beat_indices():
    assert grid.downbeat_indices([0.0, 0.5, 1.0, 1.5, 2.0], [0.02, 0.98]) == [0, 2]


def test_consensus_never_adds_beyond_the_last_beat():
    # 5 full bars plus a last bar with only 2 of its 4 beats tracked
    notes = [n for bar in range(5) for n in _groove_bar(bar)] + _groove_bar(5)[:6]
    out = grid.consensus(
        notes, list(range(0, 24, 4)), similarity=0.0, add=0.5, remove=0.0, n_beats=22
    )
    assert max(n.beat for n in out) < 22


def test_grid_records_add_a_simplified_variant():
    beats = [i * 0.5 for i in range(25)]  # 24 beats, 6 bars of 4/4
    hats = [(e * 0.25, 42) for e in range(48)]  # hi-hat eighths
    notes = [(b * 0.5, 36) for b in range(24) if b != 13] + hats  # kick per beat, one missed
    out = grid.grid_records(
        [_record("a")],
        [("none", "adtof")],
        {("own", "a"): grid.BeatGrid(beats, [i * 2.0 for i in range(6)])},
        read_notes=lambda p: notes,
        simplify_bars=True,
    )
    assert [r.transcriber for r in out] == ["adtof@grid", "adtof@simple"]
    assert len(out[0].notes) == 71 and len(out[1].notes) == 72


def test_simplified_variant_of_a_failed_record_keeps_the_error():
    out = grid.grid_records(
        [_record("a", error="boom")], [("none", "adtof")], {}, lambda p: [], simplify_bars=True
    )
    assert [(r.transcriber, r.error) for r in out] == [
        ("adtof@grid", "boom"),
        ("adtof@simple", "boom"),
    ]
