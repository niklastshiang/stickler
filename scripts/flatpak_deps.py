"""Writes the Flatpak module with the app's Python packages from uv.lock (SPEC.md, module
`packaging`): the versions the tests use, one wheel each for Python 3.14 on x86_64 (or a pure
Python one), with its SHA-256, so the build needs no network and no compiler.

    uv run python scripts/flatpak_deps.py      # after a change to uv.lock
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("packaging/flatpak/python-deps.json")
# what the installed app imports (no benchmark, no CLI); Stickler itself is pure Python and
# copied in by the manifest, so no build backend is needed
PACKAGES = ["numpy", "pyyaml", "mido", "packaging", "verovio"]
PYTHON_TAG, PLATFORM = "cp314", "x86_64"


def pick(wheels: list[dict], python_tag: str = PYTHON_TAG) -> dict:
    """A wheel CPython `python_tag` (the runtime's 3.14) on x86_64 can install, preferring the
    specific one. The `.deb` and `.rpm` use it for 3.15 too (scripts/linux_packages.py)."""
    names = [(w, w["url"].rsplit("/", 1)[-1]) for w in wheels]
    for wheel, name in names:
        if f"-{python_tag}-{python_tag}-" in name and "manylinux" in name and PLATFORM in name:
            return wheel
    for wheel, name in names:
        if "-abi3-" in name and "manylinux" in name and PLATFORM in name:
            return wheel
    for wheel, name in names:
        if name.endswith("-none-any.whl"):
            return wheel
    raise LookupError(f"no wheel for {python_tag} on {PLATFORM}: {[n for _, n in names]}")


def module(lock: Path, packages: list[str]) -> dict:
    locked = {p["name"]: p for p in tomllib.loads(lock.read_text(encoding="utf-8"))["package"]}
    sources = []
    for name in packages:
        if name not in locked:
            raise KeyError(f"{name} is not in {lock.name}")
        wheel = pick(locked[name].get("wheels", []))
        sources.append(
            {
                "type": "file",
                "url": wheel["url"],
                "sha256": wheel["hash"].removeprefix("sha256:"),
                "dest-filename": wheel["url"].rsplit("/", 1)[-1],
            }
        )
    return {
        "name": "python-deps",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --no-index --no-deps --no-build-isolation --find-links=. "
            "--prefix=/app *.whl"
        ],
        "sources": sources,
    }


def main() -> int:
    data = module(ROOT / "uv.lock", PACKAGES)
    (ROOT / OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / OUTPUT).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"{OUTPUT}: {len(data['sources'])} wheels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
