"""Tests für den Adapter-Vertrag (Subprozess, meta.json, Fehlerprotokoll, Erweiterbarkeit)."""

import json
from pathlib import Path

import pytest

from stickler import adapters
from stickler.midi import read_drum_notes

FIXTURES = Path(__file__).parent / "fixtures" / "adapters"


@pytest.fixture(scope="module")
def registry():
    return adapters.discover(FIXTURES)


def test_discover_finds_adapters_by_folder(registry):
    assert set(registry) == {"dummy", "broken"}
    assert registry["dummy"].stage == "transcribers"
    assert registry["dummy"].expected_output == "drums.mid"


def test_discover_ignores_folders_without_run_py(tmp_path):
    (tmp_path / "transcribers" / "halb").mkdir(parents=True)
    assert adapters.discover(tmp_path) == {}


def test_discover_rejects_unknown_stage(tmp_path):
    d = tmp_path / "mixers" / "x"
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="mixers"):
        adapters.discover(tmp_path)


def test_dummy_adapter_runs_and_writes_meta(registry, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"")
    result = adapters.run_adapter(registry["dummy"], audio, tmp_path / "out", device="cpu")
    assert result.ok, result.error
    assert result.output == tmp_path / "out" / "drums.mid"
    assert read_drum_notes(result.output) == [(0.5, 36), (1.0, 38)]
    meta = json.loads((tmp_path / "out" / "meta.json").read_text())
    assert meta["adapter"] == "dummy"
    assert meta["version"] == "1.0"
    assert meta["device"] == "cpu"
    assert meta["seconds"] >= 0
    assert meta["peak_rss_mb"] > 0
    assert result.meta == meta


def test_broken_adapter_is_logged_not_raised(registry, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"")
    result = adapters.run_adapter(registry["broken"], audio, tmp_path / "out", device="cpu")
    assert not result.ok
    assert "Modell explodiert" in result.error
    assert "Modell explodiert" in (tmp_path / "out" / "error.log").read_text()


def test_missing_output_counts_as_error(tmp_path):
    spec = adapters.AdapterSpec(id="leer", stage="transcribers", path=tmp_path)
    (tmp_path / "run.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "leer"\nversion = "0"\nrequires-python = ">=3.12,<3.13"\n',
        encoding="utf-8",
    )
    result = adapters.run_adapter(spec, tmp_path / "in.wav", tmp_path / "out", device="cpu")
    assert not result.ok
    assert "drums.mid" in result.error


def test_invalid_device_is_rejected(registry, tmp_path):
    with pytest.raises(ValueError, match="device"):
        adapters.run_adapter(registry["dummy"], tmp_path / "x.wav", tmp_path / "o", device="tpu")


def test_discover_skips_underscore_folders(tmp_path):
    d = tmp_path / "_common" / "helfer"
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    assert adapters.discover(tmp_path) == {}


def test_timeout_is_logged(registry, tmp_path):
    result = adapters.run_adapter(
        registry["dummy"], tmp_path / "in.wav", tmp_path / "out", device="cpu", timeout=0.001
    )
    assert not result.ok
    assert "Zeitlimit" in result.error


def test_setup_adapter_syncs_and_runs_setup_py(registry):
    marker = registry["dummy"].path / ".setup-done"
    marker.unlink(missing_ok=True)
    adapters.setup_adapter(registry["dummy"])
    assert marker.read_text() == "ok"


def test_setup_without_setup_py_only_syncs(registry):
    adapters.setup_adapter(registry["broken"])  # darf nicht werfen


def test_setup_failure_raises(tmp_path):
    (tmp_path / "pyproject.toml").write_text("kaputt = [", encoding="utf-8")
    spec = adapters.AdapterSpec(id="kaputt", stage="transcribers", path=tmp_path)
    with pytest.raises(RuntimeError, match="kaputt"):
        adapters.setup_adapter(spec)
