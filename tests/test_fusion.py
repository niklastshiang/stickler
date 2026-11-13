"""Tests for fusing frame activations of several inputs and tuning thresholds per class."""

import numpy as np
import pytest

from stickler import fusion

LABELS = [35, 38]  # KD, SD


def spikes(n, frames, value):
    a = np.zeros(n, dtype=np.float32)
    a[list(frames)] = value
    return a


def test_fuse_is_a_weighted_mean_over_the_common_length():
    a = np.ones((10, 2), dtype=np.float32)
    b = np.zeros((8, 2), dtype=np.float32)
    fused = fusion.fuse([a, b], [0.75, 0.25])
    assert fused.shape == (8, 2) and np.allclose(fused, 0.75)
    with pytest.raises(ValueError, match="weights"):
        fusion.fuse([a, b], [1.0])


def test_weight_grid_covers_the_simplex():
    assert fusion.weight_grid(2, step=0.5) == [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)]
    assert all(abs(sum(w) - 1) < 1e-9 for w in fusion.weight_grid(3, step=0.25))


def _sample():
    # Mix: kick clear, snare weak (0.3); stem: snare clear, a false kick at frame 70
    mix = np.stack([spikes(100, [10, 50], 0.9), spikes(100, [30], 0.3)], axis=1)
    stem = np.stack([spikes(100, [10, 50, 70], 0.9), spikes(100, [30], 0.9)], axis=1)
    ref = {"KD": np.array([0.10, 0.50]), "SD": np.array([0.30])}
    return fusion.Sample([mix, stem], ref, ())


def test_tune_picks_weights_and_threshold_per_class():
    best = fusion.tune(
        [_sample()],
        LABELS,
        {35: "KD", 38: "SD"},
        weights=fusion.weight_grid(2, 0.5),
        thresholds=[0.2, 0.5, 0.8],
    )
    assert best["KD"].f1 == 1.0 and best["KD"].weights[0] >= 0.5  # the stem adds a false kick
    assert best["SD"].f1 == 1.0
    assert best["SD"].counts == (1, 0, 0)


def test_excluded_regions_do_not_count():
    s = _sample()
    excluded = fusion.Sample(s.activations, {"KD": np.array([0.10])}, ((0.45, 0.75),))
    best = fusion.tune(
        [excluded], LABELS, {35: "KD", 38: "SD"}, weights=[(0.0, 1.0)], thresholds=[0.5]
    )
    assert best["KD"].counts == (1, 0, 0)  # kicks at 0.50 and 0.70 are excluded


def test_notes_apply_weights_and_thresholds_per_class():
    s = _sample()
    params = {
        "KD": fusion.ClassParams((1.0, 0.0), 0.5),
        "SD": fusion.ClassParams((0.0, 1.0), 0.5),
    }
    notes = fusion.notes(s.activations, params, LABELS, {35: "KD", 38: "SD"})
    assert notes == [(0.10, 35), (0.30, 38), (0.50, 35)]


def _records(tmp_path, track="t1", ok=True):
    from stickler.runner import Record

    s = _sample()
    out = []
    for sep, act in zip(["none", "demucs"], s.activations, strict=True):
        d = tmp_path / f"{sep}-{track}"
        d.mkdir()
        np.savez(d / "activations.npz", activations=act, fps=100, labels=np.asarray(LABELS))
        out.append(
            Record(
                "mdb",
                track,
                sep,
                "adtof",
                None,
                d / "drums.mid",
                {"seconds": 0.0 if sep == "none" else 3.0},
                {"seconds": 1.0, "device": "cpu"},
                None if ok else "boom",
            )
        )
    return out


def test_fusion_config_is_parsed_and_validated():
    raw = {
        "adtof_fused": {
            "inputs": ["none", "demucs"],
            "classes": {
                "KD": {"weights": [1, 0], "threshold": 0.5},
                "SD": {"weights": [0, 1], "threshold": 0.5},
            },
        }
    }
    (f,) = fusion.parse_fusions(raw, ["KD", "SD"])
    assert f.name == "adtof_fused" and f.inputs == ("none", "demucs")
    assert f.params["SD"] == fusion.ClassParams((0.0, 1.0), 0.5)
    raw["adtof_fused"]["classes"]["KD"]["weights"] = [1]
    with pytest.raises(ValueError, match="weights"):
        fusion.parse_fusions(raw, ["KD", "SD"])
    del raw["adtof_fused"]["classes"]["KD"]
    with pytest.raises(ValueError, match="KD"):
        fusion.parse_fusions(raw, ["KD", "SD"])


def test_fused_records_are_built_from_cached_activations(tmp_path):
    params = {"KD": fusion.ClassParams((1.0, 0.0), 0.5), "SD": fusion.ClassParams((0.0, 1.0), 0.5)}
    f = fusion.Fusion("adtof_fused", ("none", "demucs"), params)
    (rec,) = fusion.fused_records(_records(tmp_path), [f], {35: "KD", 38: "SD"})
    assert (rec.separator, rec.transcriber, rec.ok) == ("fusion", "adtof_fused", True)
    assert list(rec.notes) == [(0.10, 35), (0.30, 38), (0.50, 35)]
    assert rec.separator_meta["seconds"] == 3.0 and rec.transcriber_meta["seconds"] == 2.0


def test_fused_record_fails_if_an_input_failed(tmp_path):
    params = {"KD": fusion.ClassParams((1.0, 0.0), 0.5), "SD": fusion.ClassParams((0.0, 1.0), 0.5)}
    f = fusion.Fusion("adtof_fused", ("none", "demucs"), params)
    (rec,) = fusion.fused_records(_records(tmp_path, ok=False), [f], {35: "KD", 38: "SD"})
    assert not rec.ok and "none" in rec.error


def test_samples_from_records(tmp_path):
    class T:
        id, excluded = "t1", ((0.45, 0.75),)

        def reference_notes(self):
            return [(0.1, 36), (0.3, 38), (0.6, 36)]

    from stickler.classes import Scheme

    scheme = Scheme("5", {"KD": frozenset({35, 36}), "SD": frozenset({38})})
    (s,) = fusion.samples_from_records(
        _records(tmp_path), {"mdb": [T()]}, ("none", "demucs"), scheme
    )
    assert s.reference["KD"].tolist() == [0.1] and s.excluded == ((0.45, 0.75),)
    assert len(s.activations) == 2


def test_score_params_counts_fixed_settings():
    params = {"KD": fusion.ClassParams((0.0, 1.0), 0.5), "SD": fusion.ClassParams((1.0, 0.0), 0.5)}
    scored = fusion.score_params([_sample()], LABELS, {35: "KD", 38: "SD"}, params)
    assert scored["KD"].counts == (2, 1, 0)  # false kick from the stem
    assert scored["SD"].counts == (0, 0, 1)  # weak snare on the mix is missed
