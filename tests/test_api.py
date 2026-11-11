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
    monkeypatch.setattr(adapters, "setup_adapter", lambda spec: done.append(spec.id))
    assert api.setup_adapters("a", adapters_root=tmp_path) == ["a"]
    assert api.setup_adapters(None, adapters_root=tmp_path) == ["a", "b"]
    assert done == ["a", "a", "b"]
    with pytest.raises(ValueError, match="zzz"):
        api.setup_adapters("zzz", adapters_root=tmp_path)
