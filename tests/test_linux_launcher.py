"""The launcher of the `.deb` and `.rpm` (SPEC.md, module `linux-packages`, assumptions 4 and 6):
the app's own packages and the wheels for the running Python's minor version on the path, the
bundled uv first on PATH, and the app told that the system installed it."""

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "packaging" / "linux" / "stickler-gtk"


def _launcher():
    loader = importlib.machinery.SourceFileLoader("stickler_launcher", str(LAUNCHER))
    spec = importlib.util.spec_from_loader("stickler_launcher", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_the_wheels_of_the_running_python_go_on_the_path(tmp_path):
    for version in ("3.14", "3.15"):
        (tmp_path / f"python{version}").mkdir()
    path, env = _launcher().prepare(tmp_path, (3, 15), {"PATH": "/usr/bin:/bin"})
    assert path == [str(tmp_path), str(tmp_path / "python3.15")]
    assert env == {"STICKLER_PACKAGED": "system", "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin"}


def test_without_a_path_the_systems_default_still_finds_ffmpeg(tmp_path):
    import os

    (tmp_path / "python3.14").mkdir()
    _, env = _launcher().prepare(tmp_path, (3, 14), {})
    assert env["PATH"] == f"{tmp_path / 'bin'}:{os.defpath}"
    _, env = _launcher().prepare(tmp_path, (3, 14), {"PATH": ""})
    assert env["PATH"] == f"{tmp_path / 'bin'}:{os.defpath}"  # never the current folder


def test_a_python_without_wheels_names_the_supported_ones(tmp_path):
    for version in ("3.14", "3.15"):
        (tmp_path / f"python{version}").mkdir()
    with pytest.raises(SystemExit) as stopped:
        _launcher().prepare(tmp_path, (3, 16), {})
    assert str(stopped.value) == (
        "Stickler needs Python 3.14 or 3.15; this system's Python is 3.16. "
        "The Flatpak or the AppImage runs on any system."
    )
