"""Tests für das GM-Pitch → Klassen-Mapping."""

from pathlib import Path

import numpy as np
import pytest

from stickler.classes import Onsets, load_schemes, onsets_from_notes

CONFIG = Path(__file__).resolve().parents[1] / "config" / "classes.yaml"


@pytest.fixture(scope="module")
def schemes():
    return load_schemes(CONFIG)


def test_both_schemes_are_loaded(schemes):
    assert set(schemes) == {"5", "3"}
    assert list(schemes["5"].classes) == ["KD", "SD", "TT", "HH", "CY"]
    assert list(schemes["3"].classes) == ["KD", "SD", "HH"]


@pytest.mark.parametrize(
    ("pitch", "five", "three"),
    [(36, "KD", "KD"), (38, "SD", "SD"), (45, "TT", None), (42, "HH", "HH"), (51, "CY", None)],
)
def test_pitch_mapping(schemes, pitch, five, three):
    assert schemes["5"].class_of(pitch) == five
    assert schemes["3"].class_of(pitch) == three


def test_unknown_pitch_is_ignored(schemes):
    assert schemes["5"].class_of(56) is None


def test_duplicate_pitch_in_scheme_is_rejected(tmp_path):
    bad = tmp_path / "classes.yaml"
    bad.write_text('schemes:\n  "x":\n    KD: [36]\n    SD: [36]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="36"):
        load_schemes(bad)


def test_onsets_from_notes_sorts_and_groups(schemes):
    notes = [(2.0, 36), (1.0, 36), (1.5, 42), (1.5, 56)]
    onsets = onsets_from_notes(notes, schemes["5"])
    np.testing.assert_allclose(onsets.by_class["KD"], [1.0, 2.0])
    np.testing.assert_allclose(onsets.by_class["HH"], [1.5])
    assert onsets.by_class["SD"].size == 0
    assert set(onsets.by_class) == {"KD", "SD", "TT", "HH", "CY"}


def test_simultaneous_hits_of_one_class_count_once(schemes):
    # Crash + Ride gleichzeitig ist ein CY-Ereignis, kein Doppeltreffer.
    notes = [(1.000, 49), (1.004, 51), (1.5, 49)]
    onsets = onsets_from_notes(notes, schemes["5"])
    np.testing.assert_allclose(onsets.by_class["CY"], [1.0, 1.5])


def test_onsets_count():
    onsets = Onsets({"KD": np.array([1.0, 2.0]), "SD": np.array([3.0])})
    assert onsets.count() == 3
