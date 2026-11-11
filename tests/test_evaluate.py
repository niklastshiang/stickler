"""Tests für die Onset-Bewertung (Success Criterion 1)."""

import numpy as np
import pytest

from stickler.classes import Onsets
from stickler.evaluate import score


def onsets(**by_class: list[float]) -> Onsets:
    return Onsets({k: np.array(v, dtype=float) for k, v in by_class.items()})


REF = onsets(KD=[1.0, 2.0, 3.0], SD=[1.5, 2.5], HH=[1.0, 1.25, 1.5])


def test_reference_against_itself_is_perfect():
    result = score(REF, REF)
    assert all(prf.f1 == 1.0 for prf in result.per_class.values())
    assert result.micro.f1 == 1.0
    assert result.macro_f1 == 1.0


def test_shift_of_60ms_is_a_miss():
    shifted = onsets(KD=[1.06], SD=[], HH=[])
    result = score(onsets(KD=[1.0], SD=[], HH=[]), shifted)
    assert result.per_class["KD"].f1 == 0.0


def test_shift_of_40ms_is_a_hit():
    shifted = onsets(KD=[1.04], SD=[], HH=[])
    result = score(onsets(KD=[1.0], SD=[], HH=[]), shifted)
    assert result.per_class["KD"].f1 == 1.0


def test_micro_counts_events_over_all_classes():
    ref = onsets(KD=[1.0, 2.0], SD=[1.0])
    est = onsets(KD=[1.0], SD=[1.0, 3.0])  # TP=2, FP=1, FN=1
    result = score(ref, est)
    assert result.micro.precision == pytest.approx(2 / 3)
    assert result.micro.recall == pytest.approx(2 / 3)
    assert result.micro.f1 == pytest.approx(2 / 3)
    assert (result.micro.tp, result.micro.fp, result.micro.fn) == (2, 1, 1)


def test_macro_averages_classes_present_in_reference():
    ref = onsets(KD=[1.0], SD=[1.0], TT=[])
    est = onsets(KD=[1.0], SD=[5.0], TT=[7.0])
    result = score(ref, est)
    assert result.per_class["KD"].f1 == 1.0
    assert result.per_class["SD"].f1 == 0.0
    # TT hat keine Referenz → nicht im Makro-Mittel, aber als Fehlalarm im Mikro-Wert
    assert result.macro_f1 == pytest.approx(0.5)
    assert result.micro.fp == 2


def test_class_missing_in_estimate_counts_as_all_misses():
    result = score(onsets(KD=[1.0], HH=[2.0]), onsets(KD=[1.0]))
    assert result.per_class["HH"].recall == 0.0
    assert result.per_class["HH"].fn == 1


def test_empty_reference_and_estimate():
    result = score(onsets(KD=[]), onsets(KD=[]))
    assert result.macro_f1 is None
    assert result.micro.f1 == 0.0


def test_one_estimate_matches_at_most_one_reference():
    result = score(onsets(KD=[1.0, 1.03]), onsets(KD=[1.01]))
    assert (result.per_class["KD"].tp, result.per_class["KD"].fn) == (1, 1)
