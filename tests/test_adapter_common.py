"""Tests for the shared adapter package (adapters/_common), imported directly."""

import ctypes
import importlib.util
import sys
import types
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


class _Usage:
    def __init__(self, maxrss: int):
        self.ru_maxrss = maxrss


@pytest.mark.parametrize(
    ("platform", "maxrss"),
    [("linux", 2048 * 1024), ("darwin", 2048 * 1024 * 1024)],  # KiB on Linux, bytes on macOS
)
def test_peak_ram_is_in_megabytes_on_linux_and_macos(monkeypatch, platform, maxrss):
    # a stand-in for the whole module: Windows, where these tests run too, has no `resource`
    posix = types.SimpleNamespace(
        getrusage=lambda who: _Usage(maxrss), RUSAGE_SELF=0, RUSAGE_CHILDREN=-1
    )
    monkeypatch.setattr(sa, "resource", posix)
    assert sa._peak_rss_mb(platform) == 2048.0


def test_peak_ram_on_windows_is_the_peak_working_set_in_megabytes():
    """Windows has no `resource`; the process's own PeakWorkingSetSize (bytes) is read instead.
    The models run inside the adapter's process, so there is no child to add."""
    assert sa._peak_rss_mb("win32", windows_peak=lambda: 2048 * 1024 * 1024) == 2048.0


def test_the_windows_memory_counters_have_the_size_windows_expects():
    """PROCESS_MEMORY_COUNTERS on 64-bit Windows: two DWORDs and eight SIZE_Ts. The call
    itself only exists on Windows (first run by the Windows smoke tests)."""
    assert ctypes.sizeof(sa._MemoryCounters) == 72
    assert sa._MemoryCounters.PeakWorkingSetSize.offset == 8


def test_the_package_imports_where_there_is_no_resource_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", None)  # import resource: ImportError
    spec = importlib.util.spec_from_file_location("stickler_adapter_win", _SRC / "__init__.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._peak_rss_mb("win32", windows_peak=lambda: 1024 * 1024) == 1.0
