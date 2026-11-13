"""Tests for voting across pipelines: a hit counts if at least k of n pipelines detect it."""

from pathlib import Path

import pytest

from stickler import vote
from stickler.classes import Scheme
from stickler.runner import Record

SCHEME = Scheme("5", {"KD": frozenset({35, 36}), "SD": frozenset({38}), "HH": frozenset({42})})


def test_two_of_three_agree():
    a = [(1.000, 36), (2.000, 38)]
    b = [(1.010, 35), (3.000, 42)]
    c = [(0.990, 36), (2.020, 38)]
    out = vote.vote([a, b, c], min_agree=2, scheme=SCHEME)
    assert [round(t, 3) for t, _ in out] == [1.0, 2.01]
    assert [p for _, p in out] == [36, 38]  # most common pitch of the cluster


def test_far_apart_hits_do_not_agree():
    out = vote.vote([[(1.0, 36)], [(1.06, 36)]], min_agree=2, scheme=SCHEME)
    assert out == []


def test_one_pipeline_cannot_vote_twice():
    out = vote.vote([[(1.0, 36), (1.01, 36)], [(5.0, 36)]], min_agree=2, scheme=SCHEME)
    assert out == []


def test_classes_vote_separately():
    out = vote.vote([[(1.0, 36)], [(1.0, 38)]], min_agree=2, scheme=SCHEME)
    assert out == []


def test_parse_votes():
    (v,) = vote.parse_votes({"v": {"pipelines": ["none+adtof", "demucs+adt_str"], "min_agree": 2}})
    assert v == vote.Vote("v", (("none", "adtof"), ("demucs", "adt_str")), 2)
    with pytest.raises(ValueError, match="min_agree"):
        vote.parse_votes({"v": {"pipelines": ["none+adtof"], "min_agree": 2}})


def _rec(sep, trans, notes, error=None):
    return Record(
        "own",
        "t",
        sep,
        trans,
        None,
        Path("x.mid"),
        {"seconds": 1.0},
        {"seconds": 2.0},
        error,
        tuple(notes),
    )


def test_vote_records():
    records = [_rec("none", "adtof", [(1.0, 36)]), _rec("demucs", "adt_str", [(1.01, 36)])]
    v = vote.Vote("v", (("none", "adtof"), ("demucs", "adt_str")), 2)
    (out,) = vote.vote_records(records, [v], SCHEME, read_notes=lambda p: [])
    assert (out.separator, out.transcriber, out.ok) == ("vote", "v", True)
    assert len(out.notes) == 1 and out.transcriber_meta["seconds"] == 4.0
    records[1] = _rec("demucs", "adt_str", [], error="boom")
    (out,) = vote.vote_records(records, [v], SCHEME, read_notes=lambda p: [])
    assert not out.ok
