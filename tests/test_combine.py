"""Tests for combined pipelines: each instrument class taken from a different pipeline."""

from pathlib import Path

import pytest

from stickler import combine
from stickler.classes import Scheme
from stickler.runner import Record

SCHEME = Scheme(
    "5",
    {
        "KD": frozenset({36}),
        "SD": frozenset({38}),
        "TT": frozenset({45}),
        "HH": frozenset({42}),
        "CY": frozenset({49}),
    },
)


def rec(sep, trans, track="t1", error=None, seconds=(1.0, 2.0)):
    return Record(
        "own",
        track,
        sep,
        trans,
        None,
        None if error else Path(f"{sep}-{trans}-{track}.mid"),
        {"seconds": seconds[0], "peak_rss_mb": 100.0},
        {"seconds": seconds[1], "peak_rss_mb": 300.0, "device": "gpu"},
        error,
    )


NOTES = {
    "demucs-muscriptor_m-t1.mid": [(0.0, 36), (0.5, 38), (1.0, 45), (1.0, 42), (2.0, 49)],
    "none-adtof-t1.mid": [(0.0, 36), (0.25, 42), (2.0, 49), (2.5, 38)],
}


def read(path):
    return NOTES.get(path.name, [])


def test_parse_combos_validates_classes():
    combos = combine.parse_combos(
        {"quality": {"demucs+muscriptor_m": ["KD", "SD", "TT"], "none+adtof": ["HH", "CY"]}},
        SCHEME,
    )
    assert combos == [
        combine.Combo(
            "quality",
            {
                ("demucs", "muscriptor_m"): frozenset({"KD", "SD", "TT"}),
                ("none", "adtof"): frozenset({"HH", "CY"}),
            },
        )
    ]
    with pytest.raises(ValueError, match="unknown class"):
        combine.parse_combos({"q": {"none+adtof": ["XX"]}}, SCHEME)
    with pytest.raises(ValueError, match="more than one"):
        combine.parse_combos({"q": {"none+adtof": ["KD"], "demucs+adtof": ["KD"]}}, SCHEME)
    with pytest.raises(ValueError, match="separator\\+transcriber"):
        combine.parse_combos({"q": {"adtof": ["KD"]}}, SCHEME)


def test_combined_record_takes_each_class_from_its_pipeline():
    (combo,) = combine.parse_combos(
        {"quality": {"demucs+muscriptor_m": ["KD", "SD", "TT"], "none+adtof": ["HH", "CY"]}},
        SCHEME,
    )
    records = [rec("demucs", "muscriptor_m"), rec("none", "adtof", seconds=(0.0, 0.5))]
    (out,) = combine.combine_records(records, [combo], SCHEME, read)
    assert (out.separator, out.transcriber, out.ok) == ("combo", "quality", True)
    assert sorted(out.notes) == [(0.0, 36), (0.25, 42), (0.5, 38), (1.0, 45), (2.0, 49)]
    assert out.separator_meta["seconds"] == 1.0  # one Demucs run; "none" costs nothing
    assert out.transcriber_meta["seconds"] == 2.5
    assert out.transcriber_meta["peak_rss_mb"] == 300.0


def test_combined_record_fails_if_a_part_failed_or_is_missing():
    (combo,) = combine.parse_combos(
        {"q": {"demucs+muscriptor_m": ["KD"], "none+adtof": ["HH"]}}, SCHEME
    )
    failed = [rec("demucs", "muscriptor_m", error="time limit"), rec("none", "adtof")]
    (out,) = combine.combine_records(failed, [combo], SCHEME, read)
    assert not out.ok and "demucs+muscriptor_m" in out.error
    (out,) = combine.combine_records([rec("none", "adtof")], [combo], SCHEME, read)
    assert not out.ok and "missing" in out.error


def test_one_combined_record_per_track():
    (combo,) = combine.parse_combos({"q": {"none+adtof": ["HH"]}}, SCHEME)
    out = combine.combine_records(
        [rec("none", "adtof", "a"), rec("none", "adtof", "b", error="x")], [combo], SCHEME, read
    )
    assert [(r.track, r.ok) for r in out] == [("a", True), ("b", False)]


def test_parts_with_notes_in_memory_are_used_directly():
    (combo,) = combine.parse_combos({"q": {"vote+v": ["KD"]}}, SCHEME)
    part = Record("own", "t1", "vote", "v", None, None, {}, {}, None, ((0.5, 36), (0.6, 38)))
    (out,) = combine.combine_records([part], [combo], SCHEME, read)
    assert list(out.notes) == [(0.5, 36)]
