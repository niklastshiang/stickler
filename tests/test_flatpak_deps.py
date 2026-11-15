"""The Flatpak's Python packages come from uv.lock: the tested versions, wheels with hashes
(SPEC.md, module `packaging`)."""

import importlib.util
import json
from pathlib import Path

_FILE = Path(__file__).parents[1] / "scripts" / "flatpak_deps.py"
_spec = importlib.util.spec_from_file_location("flatpak_deps", _FILE)
deps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deps)

LOCK = Path(__file__).parents[1] / "uv.lock"


def test_each_package_gets_a_wheel_for_python_314_on_x86_64_or_a_pure_one():
    module = deps.module(LOCK, ["numpy", "pyyaml", "verovio", "mido", "packaging"])
    names = [s["dest-filename"] for s in module["sources"]]
    assert len(names) == 5 and all(n.endswith(".whl") for n in names)
    numpy = next(n for n in names if n.startswith("numpy-"))
    assert "cp314-cp314-" in numpy and "x86_64" in numpy
    assert any(n.startswith("mido-") and n.endswith("-none-any.whl") for n in names)
    assert all(
        len(s["sha256"]) == 64 and s["url"].startswith("https://") for s in module["sources"]
    )
    assert (
        "--no-index" in module["build-commands"][0]
        and "--prefix=/app" in module["build-commands"][0]
    )


def test_an_unknown_package_is_an_error():
    try:
        deps.module(LOCK, ["no-such-package"])
    except KeyError as exc:
        assert "no-such-package" in str(exc)
    else:
        raise AssertionError("no error for a package missing from the lock")


def test_the_committed_list_matches_the_lock():
    """Regenerate with: uv run python scripts/flatpak_deps.py"""
    committed = json.loads((Path(__file__).parents[1] / deps.OUTPUT).read_text(encoding="utf-8"))
    assert committed == deps.module(LOCK, deps.PACKAGES)
