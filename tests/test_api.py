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
