"""The Mac app's bundled core (SPEC.md, module `mac-package`, scope 2; task 132): the parts of
its build that do not need a Mac. `scripts/mac_bundle.sh` runs them on the runner."""

import gettext
import importlib.util
import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))  # the tools import the po reader next to them
_spec = importlib.util.spec_from_file_location("tools", ROOT / "scripts" / "mac_bundle_tools.py")
assert _spec and _spec.loader
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

PO = """msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

msgid "Open a Song…"
msgstr "Song öffnen …"

msgid "{count} page"
msgid_plural "{count} pages"
msgstr[0] "{count} Seite"
msgstr[1] "{count} Seiten"

#, fuzzy
msgid "Zoom In"
msgstr "Geraten"

msgid "Not translated"
msgstr ""
"""


def _catalogue(po: str) -> gettext.GNUTranslations:
    return gettext.GNUTranslations(io.BytesIO(tools.compile_mo(po)))


def test_a_catalogue_translates_plurals_too_and_keeps_guesses_out():
    de = _catalogue(PO)
    assert de.gettext("Open a Song…") == "Song öffnen …"
    assert de.ngettext("{count} page", "{count} pages", 1) == "{count} Seite"
    assert de.ngettext("{count} page", "{count} pages", 3) == "{count} Seiten"
    assert de.gettext("Zoom In") == "Zoom In"  # a fuzzy entry is a guess (as msgfmt)
    assert de.gettext("Not translated") == "Not translated"


@pytest.mark.parametrize("language", (ROOT / "po" / "LINGUAS").read_text().split())
def test_every_translation_of_the_app_survives(language):
    import xcstrings

    text = (ROOT / "po" / f"{language}.po").read_text(encoding="utf-8")
    catalogue = _catalogue(text)
    _header, entries = xcstrings.read_po(text)
    checked = 0
    for entry in entries:
        if "fuzzy" in entry.flags or not all(entry.msgstr):
            continue
        if entry.msgid_plural is None:
            assert catalogue.gettext(entry.msgid) == entry.msgstr[0]
        else:
            assert catalogue.ngettext(entry.msgid, entry.msgid_plural, 1) == entry.msgstr[0]
            assert catalogue.ngettext(entry.msgid, entry.msgid_plural, 5) == entry.msgstr[1]
        checked += 1
    assert checked > 150


def _file(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _core(root: Path) -> Path:
    """A made-up bundle that holds everything the real one must."""
    core = root / "core"
    site = core / "python" / "lib" / "python3.14" / "site-packages"
    for program in ("bin/uv", "bin/ffmpeg", "bin/ffprobe", "python/bin/python3"):
        _file(core / program)
        (core / program).chmod(0o755)
    for package in ("stickler", "stickler_app", "numpy", "verovio"):
        _file(site / package / "__init__.py")
    _file(site / "stickler-7.dist-info" / "METADATA", "Name: stickler\nVersion: 7\n")
    _file(site / "numpy-2.5.4.dist-info" / "METADATA", "Name: numpy\nVersion: 2.5.4\n")
    _file(site / "numpy-2.5.4.dist-info" / "LICENSE.txt", "BSD")
    _file(site / "verovio-6.4.1.dist-info" / "METADATA", "Name: verovio\nVersion: 6.4.1\n")
    _file(site / "verovio-6.4.1.dist-info" / "licenses" / "COPYING.LESSER", "LGPL")
    _file(core / "python" / "lib" / "python3.14" / "LICENSE.txt", "PSF")
    share = core / "python" / "share"
    for adapter in tools.APP_ADAPTERS:
        _file(share / "stickler" / "adapters" / adapter / "pyproject.toml")
        _file(share / "stickler" / "adapters" / adapter / "uv.lock")
    _file(share / "stickler" / "adapters" / "_common" / "stickler_adapter.py")
    for language in ("de", "es"):
        _file(share / "locale" / language / "LC_MESSAGES" / "stickler.mo")
    return core


def _licensed(core: Path, tmp_path: Path) -> None:
    extra = {}
    for name in ("uv", "ffmpeg", "stickler"):
        _file(tmp_path / f"{name}-LICENSE", name)
        extra[name] = [tmp_path / f"{name}-LICENSE"]
    tools.collect_licenses(core, extra)


def test_the_licences_of_everything_shipped_are_collected(tmp_path):
    core = _core(tmp_path)
    _licensed(core, tmp_path)
    licences = core / "licenses"
    assert (licences / "numpy" / "LICENSE.txt").read_text() == "BSD"
    assert (licences / "verovio" / "COPYING.LESSER").read_text() == "LGPL"
    assert (licences / "python" / "LICENSE.txt").read_text() == "PSF"
    assert (licences / "uv" / "uv-LICENSE").read_text() == "uv"
    assert not (licences / "stickler" / "METADATA").exists()  # only what was handed over
    index = (licences / "README.txt").read_text(encoding="utf-8")
    for name in ("ffmpeg", "numpy 2.5.4", "python", "stickler", "uv", "verovio 6.4.1"):
        assert name in index


def test_a_package_without_a_licence_file_stops_the_build(tmp_path):
    core = _core(tmp_path)
    site = core / "python" / "lib" / "python3.14" / "site-packages"
    _file(site / "mido-1.3.3.dist-info" / "METADATA", "Name: mido\nVersion: 1.3.3\n")
    with pytest.raises(ValueError, match="mido"):
        _licensed(core, tmp_path)


def test_a_complete_bundle_passes(tmp_path):
    core = _core(tmp_path)
    _licensed(core, tmp_path)
    assert tools.problems(core, languages=["de", "es"]) == []


@pytest.mark.parametrize(
    "extra",
    [
        "python/share/stickler/adapters/transcribers/adtof/.venv/bin/python",
        "python/share/stickler/adapters/transcribers/adtof/weights/model.ckpt",
        "python/lib/python3.14/site-packages/stickler/__pycache__/api.cpython-314.pyc",
        "python/share/stickler/adapters/beats/beat_this/.setup-done",
        "python/lib/python3.14/site-packages/pip/__init__.py",
    ],
)
def test_environments_weights_caches_and_pip_are_found(tmp_path, extra):
    core = _core(tmp_path)
    _licensed(core, tmp_path)
    _file(core / extra)
    found = tools.problems(core, languages=["de", "es"])
    assert len(found) == 1 and found[0].startswith("must not ship: "), found
    assert found[0].removeprefix("must not ship: ") in extra


@pytest.mark.parametrize(
    "missing",
    [
        "bin/uv",
        "bin/ffprobe",
        "python/share/locale/es/LC_MESSAGES/stickler.mo",
        "python/share/stickler/adapters/separators/demucs/pyproject.toml",
        "python/share/stickler/adapters/_common/stickler_adapter.py",
        "licenses/ffmpeg/ffmpeg-LICENSE",
        "python/lib/python3.14/site-packages/stickler_app/__init__.py",
    ],
)
def test_a_missing_part_is_named(tmp_path, missing):
    core = _core(tmp_path)
    _licensed(core, tmp_path)
    (core / missing).unlink()
    found = tools.problems(core, languages=["de", "es"])
    assert found and any(missing in line or str(Path(missing).parent) in line for line in found)


def test_a_program_that_cannot_run_is_named(tmp_path):
    core = _core(tmp_path)
    _licensed(core, tmp_path)
    (core / "bin" / "ffmpeg").chmod(0o644)
    assert any("ffmpeg" in line for line in tools.problems(core, languages=["de", "es"]))


def test_python_loses_what_the_core_never_runs(tmp_path):
    python = tmp_path / "python"
    lib = python / "lib" / "python3.14"
    kept = [
        lib / "json" / "__init__.py",
        lib / "site-packages" / "numpy" / "__init__.py",
        lib / "site-packages" / "numpy-2.5.4.dist-info" / "METADATA",
        lib / "lib-dynload" / "_struct.cpython-314-darwin.so",
        python / "bin" / "python3.14",
    ]
    gone = [
        lib / "test" / "test_os.py",
        lib / "idlelib" / "idle.py",
        lib / "tkinter" / "__init__.py",
        lib / "turtledemo" / "clock.py",
        lib / "ensurepip" / "__init__.py",
        lib / "lib-dynload" / "_tkinter.cpython-314-darwin.so",
        lib / "site-packages" / "pip" / "__init__.py",
        lib / "site-packages" / "pip-26.0.dist-info" / "METADATA",
        lib / "site-packages" / "numpy" / "_core" / "tests" / "test_multiarray.py",
        lib / "site-packages" / "numpy" / "__pycache__" / "x.pyc",
        python / "lib" / "tcl9.0" / "init.tcl",
        python / "lib" / "tk9.0" / "tk.tcl",
        python / "lib" / "libtcl9.0.dylib",
        python / "include" / "python3.14" / "Python.h",
        python / "share" / "man" / "man1" / "python3.1",
        python / "bin" / "pip3",
        python / "bin" / "idle3.14",
    ]
    for path in kept + gone:
        _file(path)
    tools.prune(python)
    assert all(path.exists() for path in kept)
    assert not any(path.exists() for path in gone)


def test_uv_is_one_version_in_every_package_and_every_download_is_pinned():
    mac = (ROOT / "scripts" / "mac_bundle.sh").read_text(encoding="utf-8")
    appimage = (ROOT / "scripts" / "appimage.sh").read_text(encoding="utf-8")
    flatpak = (ROOT / "packaging" / "flatpak" / "ng.tshia.Stickler.yml").read_text("utf-8")
    version = re.search(r"^UV_VERSION=(\S+)", mac, re.MULTILINE).group(1)
    assert re.search(r"^UV_VERSION=(\S+)", appimage, re.MULTILINE).group(1) == version
    assert set(re.findall(r"astral-sh/uv/(?:releases/download/)?([0-9.]+)/", flatpak)) == {version}
    for script in (mac, (ROOT / "scripts" / "mac_ffmpeg.sh").read_text(encoding="utf-8")):
        pins = re.findall(r"^[A-Z_]+_SHA256=(\S+)", script, re.MULTILINE)
        assert pins and all(re.fullmatch(r"[0-9a-f]{64}", pin) for pin in pins)
        # nothing is fetched without a checksum: every curl goes through fetch or a check
        assert script.count("curl ") == script.count("shasum -a 256 -c")
    assert "brew" not in mac  # the runner's Homebrew is not a pinned source
