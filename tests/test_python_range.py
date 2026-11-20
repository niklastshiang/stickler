"""The project's Python range and what CI tests (SPEC.md, module `linux-packages`): Fedora 45's
system Python is 3.15, and the `.rpm` runs the app on it."""

import re
import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet

ROOT = Path(__file__).resolve().parents[1]


def requires_python() -> SpecifierSet:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return SpecifierSet(project["requires-python"])


def test_the_range_covers_the_python_of_every_supported_system():
    # Ubuntu 26.04 and Fedora 44 have 3.14, Fedora 45 has 3.15
    allowed = requires_python()
    for version in ("3.12.0", "3.14.0", "3.15.0"):
        assert allowed.contains(version), version


def test_ci_tests_both_ends_of_the_range():
    allowed = requires_python()
    minors = [f"3.{minor}" for minor in range(10, 20) if allowed.contains(f"3.{minor}.0")]
    workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
    matrix = re.search(r"python: \[([^\]]*)\]", workflow)
    assert matrix, "check.yml has no python matrix"
    assert [v.strip().strip('"') for v in matrix.group(1).split(",")] == [minors[0], minors[-1]]
