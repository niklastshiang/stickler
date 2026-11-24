"""Tests for scripts/lock_platforms.py: what a uv.lock resolves for Linux, compared before and
after a lock change (SPEC.md, module `mac-core`, scope 1)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "lock_platforms", ROOT / "scripts" / "lock_platforms.py"
)
assert _spec and _spec.loader
lp = importlib.util.module_from_spec(_spec)
sys.modules["lock_platforms"] = lp
_spec.loader.exec_module(lp)

HEAD = 'version = 1\nrequires-python = "==3.14.*"\n'
LINUX = "torch-2.15.0-cp314-cp314-manylinux_2_28_x86_64.whl"
MAC = "torch-2.15.0-cp314-cp314-macosx_14_0_arm64.whl"
ANY = "tqdm-4.67.1-py3-none-any.whl"


def _root(*deps: str) -> str:
    rows = ", ".join(deps)
    head = '\n[[package]]\nname = "adapter"\nversion = "0.1.0"\nsource = { virtual = "." }\n'
    return head + f"dependencies = [{rows}]\n"


def _package(name, version, wheels=(), markers=None, sdist="sha256:s"):
    text = f'\n[[package]]\nname = "{name}"\nversion = "{version}"\n'
    text += 'source = { registry = "https://pypi.org/simple" }\n'
    if markers:
        text += "resolution-markers = [" + ", ".join(f'"{m}"' for m in markers) + "]\n"
    text += f'sdist = {{ url = "https://x/{name}.tar.gz", hash = "{sdist}" }}\n'
    if wheels:
        rows = ", ".join(f'{{ url = "https://x/{w}", hash = "sha256:{w}" }}' for w in wheels)
        text += f"wheels = [{rows}]\n"
    return text


def test_adding_a_platforms_wheels_leaves_linux_unchanged():
    root = _root('{ name = "torch" }', '{ name = "tqdm" }')
    before = HEAD + root + _package("torch", "2.15.0", [LINUX]) + _package("tqdm", "4.67.1", [ANY])
    after = (
        HEAD + root + _package("torch", "2.15.0", [LINUX, MAC]) + _package("tqdm", "4.67.1", [ANY])
    )
    assert lp.compare(before, after) == []


def test_a_new_package_only_for_macos_is_not_a_linux_change():
    before = HEAD + _root('{ name = "torch" }') + _package("torch", "2.15.0", [LINUX])
    after = (
        HEAD
        + _root('{ name = "torch" }', '{ name = "appnope", marker = "sys_platform == \'darwin\'" }')
        + _package("torch", "2.15.0", [LINUX])
        + _package("appnope", "0.1.4", ["appnope-0.1.4-py2.py3-none-any.whl"])
    )
    assert lp.compare(before, after) == []


def test_another_version_on_linux_is_reported():
    root = _root('{ name = "torch" }')
    before = HEAD + root + _package("torch", "2.15.0", [LINUX])
    after = HEAD + root + _package("torch", "2.15.1", [LINUX.replace("2.15.0", "2.15.1")])
    assert any("torch" in line for line in lp.compare(before, after))


def test_a_changed_hash_is_reported():
    root = _root('{ name = "tqdm" }')
    before = HEAD + root + _package("tqdm", "4.67.1", [ANY])
    after = HEAD + root + _package("tqdm", "4.67.1", [ANY], sdist="sha256:other")
    assert lp.compare(before, after) != []


def test_a_new_dependency_for_every_platform_counts_for_linux():
    before = HEAD + _root('{ name = "torch" }') + _package("torch", "2.15.0", [LINUX])
    after = (
        HEAD
        + _root('{ name = "torch" }', '{ name = "tqdm" }')
        + _package("torch", "2.15.0", [LINUX])
        + _package("tqdm", "4.67.1", [ANY])
    )
    assert any("tqdm" in line for line in lp.compare(before, after))


def test_an_unclear_marker_counts_for_linux():
    """Only a plain "this other platform" marker is left out; anything else is reported."""
    before = HEAD + _root('{ name = "torch" }') + _package("torch", "2.15.0", [LINUX])
    after = (
        HEAD
        + _root('{ name = "torch" }', '{ name = "x", marker = "python_full_version >= \'3.14\'" }')
        + _package("torch", "2.15.0", [LINUX])
        + _package("x", "1.0", ["x-1.0-py3-none-any.whl"])
    )
    assert any("x" in line for line in lp.compare(before, after))


def test_a_fork_keeps_the_linux_version_apart_from_the_mac_one():
    linux_numpy = "numpy-2.3.0-cp314-cp314-manylinux_2_28_x86_64.whl"
    before = HEAD + _root('{ name = "numpy" }') + _package("numpy", "2.3.0", [linux_numpy])
    mac = "sys_platform == 'darwin' and platform_machine == 'arm64'"
    after = (
        HEAD
        + _root(
            '{ name = "numpy", version = "2.3.0", marker = "sys_platform == \'linux\'" }',
            f'{{ name = "numpy", version = "2.4.0", marker = "{mac}" }}',
        )
        + _package("numpy", "2.3.0", [linux_numpy], ["sys_platform == 'linux'"])
        + _package("numpy", "2.4.0", ["numpy-2.4.0-cp314-cp314-macosx_14_0_arm64.whl"], [mac])
    )
    assert lp.compare(before, after) == []


def test_main_exits_non_zero_on_a_difference(tmp_path):
    root = _root('{ name = "torch" }')
    a, b = tmp_path / "a.lock", tmp_path / "b.lock"
    a.write_text(HEAD + root + _package("torch", "2.15.0", [LINUX]), encoding="utf-8")
    b.write_text(HEAD + root + _package("torch", "2.15.1", [LINUX]), encoding="utf-8")
    assert lp.main([str(a), str(a)]) == 0
    assert lp.main([str(a), str(b)]) == 1
