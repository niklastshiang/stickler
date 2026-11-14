"""Tests for the error breakdown: missed, invented, confused and off-time hits."""

import numpy as np
import pytest

from stickler import errors, evaluate
from stickler.classes import Onsets


def onsets(**by_class):
    return Onsets({c: np.asarray(t, dtype=float) for c, t in by_class.items()})


def test_matched_hits_are_no_errors():
    b = errors.categorise(onsets(KD=[1.0, 2.0]), onsets(KD=[1.01, 2.02]))
    assert b.per_class["KD"].tp == 2
    assert b.counts("KD") == {
        "tp": 2,
        "missed": 0,
        "invented": 0,
        "off_time": 0,
        "confused_ref": 0,
        "confused_est": 0,
    }


def test_unmatched_hits_are_missed_and_invented():
    b = errors.categorise(onsets(SD=[1.0]), onsets(SD=[3.0]))
    assert b.per_class["SD"].missed == (1.0,) and b.per_class["SD"].invented == (3.0,)


def test_another_drum_at_the_same_moment_is_a_confusion():
    b = errors.categorise(onsets(HH=[1.0]), onsets(CY=[1.01]))
    assert b.confused == (errors.Confusion("HH", "CY", 1.0, 1.01),)
    assert b.counts("HH")["missed"] == 0 and b.counts("CY")["invented"] == 0
    assert b.counts("HH")["confused_ref"] == 1 and b.counts("CY")["confused_est"] == 1


def test_same_drum_50_to_100_ms_away_is_off_time():
    b = errors.categorise(onsets(SD=[1.0, 5.0]), onsets(SD=[1.07, 5.12]))
    assert b.per_class["SD"].off_time == ((1.0, 1.07),)
    assert b.per_class["SD"].missed == (5.0,) and b.per_class["SD"].invented == (5.12,)


def test_each_hit_is_confused_at_most_once():
    b = errors.categorise(onsets(HH=[1.0]), onsets(CY=[1.0], TT=[1.02]))
    assert len(b.confused) == 1
    assert b.counts("CY")["invented"] + b.counts("TT")["invented"] == 1


def test_confusion_comes_before_off_time():
    b = errors.categorise(onsets(SD=[1.0]), onsets(HH=[1.0], SD=[1.08]))
    assert b.confused == (errors.Confusion("SD", "HH", 1.0, 1.0),)
    assert b.per_class["SD"].off_time == () and b.per_class["SD"].invented == (1.08,)


def test_confusions_are_paired_as_many_as_possible_not_greedily():
    # nearest first would pair the kick at 1.00 with the hi-hat at 1.04 (40 ms, nearer than
    # 45 ms) and leave the kick at 1.08 without its only partner
    b = errors.categorise(onsets(KD=[1.0, 1.08]), onsets(HH=[0.955, 1.04]))
    assert sorted((c.ref_time, c.est_time) for c in b.confused) == [(1.0, 0.955), (1.08, 1.04)]


def test_a_class_only_the_model_has():
    b = errors.categorise(onsets(KD=[1.0]), onsets(KD=[1.0], TT=[2.0]))
    assert b.counts("TT")["invented"] == 1 and b.counts("TT")["tp"] == 0


@pytest.mark.parametrize("seed", range(20))
def test_categories_add_up_to_the_scores_errors(seed):
    rng = np.random.default_rng(seed)
    classes = ["KD", "SD", "TT", "HH", "CY"]
    ref = onsets(**{c: np.sort(rng.uniform(0, 10, rng.integers(0, 30))) for c in classes})
    est = onsets(**{c: np.sort(rng.uniform(0, 10, rng.integers(0, 30))) for c in classes})
    b = errors.categorise(ref, est)
    scores = evaluate.score(ref, est)
    for c in classes:
        k, prf = b.counts(c), scores.per_class[c]
        assert k["tp"] == prf.tp
        assert k["missed"] + k["off_time"] + k["confused_ref"] == prf.fn
        assert k["invented"] + k["off_time"] + k["confused_est"] == prf.fp
