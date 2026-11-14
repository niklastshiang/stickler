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


def test_count_rows_split_confusions_by_the_drum_written_instead():
    b = errors.categorise(onsets(HH=[1.0, 2.0, 3.0]), onsets(CY=[1.0, 2.0], SD=[3.0]))
    (hh,) = [r for r in errors.count_rows(b, ["KD", "SD", "HH", "CY"]) if r["class"] == "HH"]
    assert hh["confused_ref"] == 3 and hh["ref_as_CY"] == 2 and hh["ref_as_SD"] == 1
    assert hh["ref_as_KD"] == 0 and hh["ref_as_HH"] == 0


def test_every_error_becomes_a_spot_with_the_side_that_claims_the_hit():
    b = errors.categorise(onsets(SD=[1.0, 5.0], HH=[3.0]), onsets(SD=[5.07, 7.0], CY=[3.0]))
    spots = errors.spots({("own", "song", "none+adtof"): b})
    got = sorted((s.time, s.cls, s.side) for s in spots)
    assert got == [
        (1.0, "SD", "ref"),  # missed
        (3.0, "CY", "est"),  # confused: the model wrote a cymbal ...
        (3.0, "HH", "ref"),  # ... where the reference has a hi-hat
        (5.0, "SD", "ref"),  # off time: both sides
        (5.07, "SD", "est"),
        (7.0, "SD", "est"),  # invented
    ]
    assert all(s.song == "song" and s.pipelines == frozenset({"none+adtof"}) for s in spots)


def test_spots_of_several_pipelines_are_merged():
    ref = onsets(KD=[1.0])
    fast = errors.categorise(ref, onsets(KD=[], HH=[2.0]))
    quality = errors.categorise(ref, onsets(KD=[], HH=[2.0], TT=[4.0]))
    spots = errors.spots({("own", "s", "fast"): fast, ("own", "s", "quality"): quality})
    by = {(s.time, s.cls): s.pipelines for s in spots}
    assert by[(1.0, "KD")] == by[(2.0, "HH")] == frozenset({"fast", "quality"})
    assert by[(4.0, "TT")] == frozenset({"quality"})


def _many_spots():
    return [
        errors.Spot(f"song{k % 3}", float(k), cls, side, frozenset({"p"}))
        for cls in ("KD", "SD", "TT", "HH", "CY")
        for side in ("ref", "est")
        for k in range(30)
    ] + [errors.Spot("song0", 99.0, "TT", "est", frozenset({"p"}))]


def test_the_sample_has_the_same_number_of_spots_per_class_and_side():
    sample = errors.draw_sample(_many_spots(), per_class_side=10, seed=1)
    assert len(sample) == 100 and len(set(sample)) == 100
    for cls in ("KD", "SD", "TT", "HH", "CY"):
        for side in ("ref", "est"):
            assert sum(s.cls == cls and s.side == side for s in sample) == 10


def test_the_sample_is_reproducible_and_shuffled():
    spots = _many_spots()
    first = errors.draw_sample(spots, per_class_side=10, seed=1)
    assert errors.draw_sample(list(reversed(spots)), per_class_side=10, seed=1) == first
    assert errors.draw_sample(spots, per_class_side=10, seed=2) != first
    assert [s.cls for s in first[:10]] != ["KD"] * 10  # classes are mixed, not in blocks


def test_a_small_group_is_taken_whole():
    spots = [errors.Spot("s", 1.0, "TT", "ref", frozenset({"p"}))]
    assert errors.draw_sample(spots, per_class_side=10, seed=1) == spots
