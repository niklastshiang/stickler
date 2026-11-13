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
    beats = {("own", "a"): BEATS, ("own", "b"): None}
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
