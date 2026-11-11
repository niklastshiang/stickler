"""Tests für die öffentliche API."""

import pytest

from stickler import api
from stickler.datasets import mdb


def test_fetch_dataset_mdb_uses_data_subfolder(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(mdb, "fetch", lambda target: seen.append(target) or 23)
    assert api.fetch_dataset("mdb", tmp_path) == 23
    assert seen == [tmp_path / "mdb"]


def test_fetch_unknown_dataset_raises(tmp_path):
    with pytest.raises(ValueError, match="unbekannt"):
        api.fetch_dataset("foo", tmp_path)


def test_setup_adapters_selects_one_or_all(monkeypatch, tmp_path):
    from stickler import adapters

    for name in ("a", "b"):
        d = tmp_path / "transcribers" / name
        d.mkdir(parents=True)
        (d / "run.py").write_text("", encoding="utf-8")
    done = []
    monkeypatch.setattr(
        adapters, "setup_adapter", lambda spec, device="cpu": done.append((spec.id, device))
    )
    assert api.setup_adapters("a", adapters_root=tmp_path) == ["a"]
    assert api.setup_adapters(None, adapters_root=tmp_path) == ["a", "b"]
    assert done == [("a", "cpu"), ("a", "cpu"), ("b", "cpu")]
    # rocm ohne Angabe: nur Adapter mit [tool.stickler.rocm]
    (tmp_path / "transcribers" / "b" / "pyproject.toml").write_text(
        '[tool.stickler.rocm]\nindex = "i"\nreplace = []\npackages = []\n', encoding="utf-8"
    )
    (tmp_path / "transcribers" / "a" / "pyproject.toml").write_text("", encoding="utf-8")
    assert api.setup_adapters(None, device="rocm", adapters_root=tmp_path) == ["b"]
    with pytest.raises(ValueError, match="zzz"):
        api.setup_adapters("zzz", adapters_root=tmp_path)


def _bench(tmp_path, transcribers="[dummy]"):
    cfg = tmp_path / "bench.yaml"
    cfg.write_text(
        f"datasets: [mdb]\nseparators: [none]\ntranscribers: {transcribers}\n"
        'device: cpu\nschemes: ["5"]\n',
        encoding="utf-8",
    )
    return cfg


def _fake_mdb(monkeypatch, tmp_path):
    from pathlib import Path

    from stickler.datasets import mdb as mdb_mod

    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"x")
    ann = tmp_path / "t_subclass.txt"
    ann.write_text("0.5 \t KD \n1.0 \t SD \n", encoding="utf-8")
    track = mdb_mod.Track(id="t", mix=mix, drums=None, annotation=ann)
    monkeypatch.setattr(mdb_mod, "tracks", lambda target: [track])
    return Path(__file__).parent / "fixtures" / "adapters"


def test_load_config_validates(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("datasets: [mdb]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="separators"):
        api.load_benchmark_config(cfg)


def test_run_and_evaluate_benchmark(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    seen = []
    records = api.run_benchmark(cfg, progress=lambda d, t, label: seen.append(label), **kw)
    assert [r.ok for r in records] == [True]
    assert seen == ["mdb/t: none → dummy"]
    summary = api.evaluate_benchmark(cfg, results_dir=tmp_path / "results", **kw)
    assert summary[0]["micro_f1"] == 1.0
    assert (tmp_path / "results" / "metrics.csv").exists()
    assert (tmp_path / "results" / "summary.csv").exists()


def test_run_benchmark_device_override(monkeypatch, tmp_path):
    from stickler import runner

    fixtures = _fake_mdb(monkeypatch, tmp_path)
    captured = {}

    def fake_matrix(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(runner, "run_matrix", fake_matrix)
    api.run_benchmark(
        _bench(tmp_path),
        data_dir=tmp_path,
        cache_dir=tmp_path,
        adapters_root=fixtures,
        device="gpu",
    )
    assert captured["device"] == "gpu"


def test_missing_dataset_raises(monkeypatch, tmp_path):
    from stickler.datasets import mdb as mdb_mod

    monkeypatch.setattr(mdb_mod, "tracks", lambda target: [])
    with pytest.raises(ValueError, match="stickler fetch mdb"):
        api.run_benchmark(_bench(tmp_path), data_dir=tmp_path, cache_dir=tmp_path)


def test_run_doctor_returns_checks(tmp_path):
    names = [c.name for c in api.run_doctor(adapters_root=tmp_path, data_dir=tmp_path)]
    assert names[0] == "gpu" and "datensatz mdb" in names
