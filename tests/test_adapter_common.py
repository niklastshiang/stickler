"""Tests für das gemeinsame Adapter-Paket (adapters/_common), direkt importiert."""

import importlib.util
import sys
from pathlib import Path

import pytest

from stickler.midi import read_drum_notes

_SRC = Path(__file__).resolve().parents[1] / "adapters" / "_common" / "src" / "stickler_adapter"
_spec = importlib.util.spec_from_file_location("stickler_adapter", _SRC / "__init__.py")
assert _spec and _spec.loader
sa = importlib.util.module_from_spec(_spec)
sys.modules["stickler_adapter"] = sa
_spec.loader.exec_module(sa)


def test_cpu_requested_is_cpu():
    assert sa.choose_device("cpu") == "cpu"


def test_auto_without_torch_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(sa, "_gpu_available", lambda: False)
    assert sa.choose_device("auto") == "cpu"


def test_auto_with_gpu_picks_gpu(monkeypatch):
    monkeypatch.setattr(sa, "_gpu_available", lambda: True)
    assert sa.choose_device("auto") == "gpu"


def test_gpu_requested_but_missing_fails(monkeypatch):
    monkeypatch.setattr(sa, "_gpu_available", lambda: False)
    with pytest.raises(RuntimeError, match="GPU"):
        sa.choose_device("gpu")


def test_write_drum_midi_roundtrip(tmp_path):
    path = tmp_path / "x.mid"
    sa.write_drum_midi(path, [(1.25, 42, 80), (0.0, 36, 127), (3.0, 49, 1)])
    assert read_drum_notes(path) == [(0.0, 36), (1.25, 42), (3.0, 49)]


def test_write_drum_midi_empty(tmp_path):
    path = tmp_path / "leer.mid"
    sa.write_drum_midi(path, [])
    assert read_drum_notes(path) == []
