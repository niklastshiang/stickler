"""The Mac app's icon (SPEC.md, module `mac-package`, scope 4; `mac-design`: the GTK icon's
layers on the macOS shape; an Icon Composer bundle with a dark appearance since 2026-11-22) and
its version, which is the project's."""

import importlib.util
import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mac_icon", ROOT / "scripts" / "mac_icon.py")
assert _spec and _spec.loader
mac_icon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mac_icon)

BUNDLE = ROOT / "mac" / "Stickler" / "AppIcon.icon"
GTK_ICON = ROOT / "packaging" / "icons" / "ng.tshia.Stickler.svg"


def _gtk_icon() -> str:
    return GTK_ICON.read_text(encoding="utf-8")


def test_the_master_is_the_gtk_icons_layers_on_the_macos_shape():
    master = mac_icon.master_svg(_gtk_icon())
    assert 'viewBox="0 0 1024 1024"' in master
    # the design board's numbers (docs/design/mac/Icon.dc.html)
    assert '<rect x="100" y="100" width="824" height="824" rx="185" fill="#e8894a"/>' in master
    assert '<svg x="98" y="127" width="720" height="720" viewBox="0 0 128 128">' in master
    for layer in ("paper", "staff", "notes", "sticks"):
        assert f'<g id="{layer}">' in master
    assert master.count("<?xml") == 1 and "<!--" not in master


def test_the_stored_master_and_bundle_follow_the_gtk_icon():
    """Changing the GTK icon or the script without running scripts/mac_icon.py fails here."""
    assert mac_icon.MASTER.read_text(encoding="utf-8") == mac_icon.master_svg(_gtk_icon())
    files = mac_icon.bundle_files(_gtk_icon())
    stored = {
        path.relative_to(BUNDLE).as_posix(): path.read_text(encoding="utf-8")
        for path in BUNDLE.rglob("*")
        if path.is_file()
    }
    assert stored == files


def test_an_icon_without_its_four_layers_is_refused():
    try:
        mac_icon.drawing('<svg xmlns="http://www.w3.org/2000/svg"><g id="paper"/></svg>')
    except ValueError as error:
        assert "staff" in str(error)
    else:
        raise AssertionError("accepted")


def test_the_dark_drawing_has_dark_paper_and_white_notes_and_keeps_the_rest():
    light = mac_icon.drawing(_gtk_icon())
    dark = mac_icon.dark_drawing(light)

    def part(text: str, layer: str, following: str | None) -> str:
        start = text.index(f'<g id="{layer}">')
        return text[start : text.index(f'<g id="{following}">') if following else len(text)]

    paper, notes = part(dark, "paper", "staff"), part(dark, "notes", "sticks")
    assert {"#241f31", "#3d3846", "#5e5c64"} <= set(re.findall(r"#[0-9a-f]{6}", paper))
    assert not {"#ffffff", "#deddda", "#c0bfbc"} & set(re.findall(r"#[0-9a-f]{6}", paper))
    assert set(re.findall(r"#[0-9a-f]{6}", notes)) == {"#ffffff"}
    # the staff lines and the sticks are the light icon's
    assert part(dark, "staff", "notes") == part(light, "staff", "notes")
    assert part(dark, "sticks", None) == part(light, "sticks", None)


def test_a_missing_colour_is_refused_instead_of_a_half_dark_icon():
    light = mac_icon.drawing(_gtk_icon()).replace('"#deddda"', '"#dddddd"')
    try:
        mac_icon.dark_drawing(light)
    except ValueError as error:
        assert "#deddda" in str(error)
    else:
        raise AssertionError("accepted")


def test_the_layers_fill_icon_composers_canvas_as_the_drawing_fills_the_board():
    layer = mac_icon.layer_svg("<g/>")
    assert 'viewBox="0 0 1024 1024"' in layer
    # 98 and 127 on the 824 square from 100, scaled to 1024; 720 of 128 units, scaled too
    assert '<g transform="translate(-2.485 33.553) scale(6.99029)">' in layer


def test_the_descriptor_is_the_orange_with_a_light_and_a_dark_picture_for_macos():
    descriptor = json.loads(mac_icon.descriptor_text())
    # the orange in dark too (owner): a plain "fill" counts for light only, and macOS put its
    # own black behind the dark picture (seen on the owner's Mac, 2026-11-22)
    orange = {"solid": "srgb:0.90980,0.53725,0.29020,1.00000"}
    assert "fill" not in descriptor
    assert descriptor["fill-specializations"] == [
        {"value": orange},
        {"appearance": "dark", "value": orange},
    ]
    assert descriptor["supported-platforms"] == {"squares": ["macOS"]}
    (group,) = descriptor["groups"]
    (layer,) = group["layers"]
    assert layer["glass"] is False
    assert layer["image-name-specializations"] == [
        {"value": "drawing.svg"},
        {"appearance": "dark", "value": "drawing-dark.svg"},
    ]
    assert mac_icon.descriptor_text().startswith('{\n  "fill-specializations" : [')


def test_colours_are_written_as_icon_composer_writes_them():
    assert mac_icon.colour("#ffffff") == "srgb:1.00000,1.00000,1.00000,1.00000"
    assert mac_icon.colour("#000000") == "srgb:0.00000,0.00000,0.00000,1.00000"


def test_the_app_uses_the_bundle_and_no_icon_set():
    project = yaml.safe_load((ROOT / "mac" / "project.yml").read_text(encoding="utf-8"))
    settings = project["targets"]["Stickler"]["settings"]["base"]
    assert settings["ASSETCATALOG_COMPILER_APPICON_NAME"] == BUNDLE.stem
    assert {"path": "Stickler"} in project["targets"]["Stickler"]["sources"]
    assert not (ROOT / "mac" / "Stickler" / "Assets.xcassets").exists()


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
