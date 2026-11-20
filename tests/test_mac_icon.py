"""The Mac app's icon (SPEC.md, module `mac-package`, scope 4; `mac-design`: the GTK icon's
layers on the macOS shape) and its version, which is the project's."""

import importlib.util
import json
import re
import struct
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mac_icon", ROOT / "scripts" / "mac_icon.py")
assert _spec and _spec.loader
mac_icon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mac_icon)

ICONSET = ROOT / "mac" / "Stickler" / "Assets.xcassets" / "AppIcon.appiconset"
GTK_ICON = ROOT / "packaging" / "icons" / "ng.tshia.Stickler.svg"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR", path
    return struct.unpack(">II", data[16:24])


def test_the_master_is_the_gtk_icons_layers_on_the_macos_shape():
    master = mac_icon.master_svg(GTK_ICON.read_text(encoding="utf-8"))
    assert 'viewBox="0 0 1024 1024"' in master
    # the design board's numbers (docs/design/mac/Icon.dc.html)
    assert '<rect x="100" y="100" width="824" height="824" rx="185" fill="#e8894a"/>' in master
    assert '<svg x="98" y="127" width="720" height="720" viewBox="0 0 128 128">' in master
    for layer in ("paper", "staff", "notes", "sticks"):
        assert f'<g id="{layer}">' in master
    assert master.count("<?xml") == 1 and "<!--" not in master.split("<svg", 1)[1]


def test_the_stored_master_follows_the_gtk_icon():
    """Changing the GTK icon without running scripts/mac_icon.py fails here."""
    assert mac_icon.MASTER.read_text(encoding="utf-8") == mac_icon.master_svg(
        GTK_ICON.read_text(encoding="utf-8")
    )


def test_an_icon_without_its_four_layers_is_refused():
    try:
        mac_icon.master_svg('<svg xmlns="http://www.w3.org/2000/svg"><g id="paper"/></svg>')
    except ValueError as error:
        assert "staff" in str(error)
    else:
        raise AssertionError("accepted")


def test_the_icon_set_names_a_picture_of_the_right_size_for_every_slot():
    contents = json.loads((ICONSET / "Contents.json").read_text(encoding="utf-8"))
    assert contents == mac_icon.contents()
    slots = {(image["size"], image["scale"]) for image in contents["images"]}
    assert slots == {(f"{n}x{n}", s) for n in (16, 32, 128, 256, 512) for s in ("1x", "2x")}
    for image in contents["images"]:
        assert image["idiom"] == "mac"
        points = int(image["size"].split("x")[0]) * int(image["scale"][0])
        assert _png_size(ICONSET / image["filename"]) == (points, points), image
    stored = {p.name for p in ICONSET.iterdir()}
    assert stored == {"Contents.json"} | {image["filename"] for image in contents["images"]}


def test_the_app_uses_the_icon_set():
    project = yaml.safe_load((ROOT / "mac" / "project.yml").read_text(encoding="utf-8"))
    settings = project["targets"]["Stickler"]["settings"]["base"]
    assert settings["ASSETCATALOG_COMPILER_APPICON_NAME"] == "AppIcon"
    catalog = json.loads((ICONSET.parent / "Contents.json").read_text(encoding="utf-8"))
    assert catalog["info"]["author"] == "xcode"


def test_the_mac_app_has_the_projects_version():
    """About shows the release's number (ADR 0006); both move together at a release."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert re.fullmatch(r"[1-9][0-9]*", version)
    base = yaml.safe_load((ROOT / "mac" / "project.yml").read_text(encoding="utf-8"))["settings"][
        "base"
    ]
    assert base["MARKETING_VERSION"] == version
    assert base["CURRENT_PROJECT_VERSION"] == version
