"""The app's boundaries: GTK stays out of the library and the app's logic; the logic is
shared and depends on no app; one app ID."""

import ast
import configparser
import tomllib
from pathlib import Path

import stickler_app

ROOT = Path(__file__).resolve().parents[2]
NO_GTK = [ROOT / "src" / "stickler", ROOT / "src" / "stickler_app"]


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_library_and_app_logic_never_import_gtk():
    for folder in NO_GTK:
        files = sorted(folder.rglob("*.py"))
        assert files, f"{folder} has no Python files"
        offenders = [str(f.relative_to(ROOT)) for f in files if "gi" in _imports(f)]
        assert offenders == [], f"GTK imported where it must not be: {offenders}"


def test_the_shared_logic_depends_on_no_app_and_the_library_on_neither():
    """`stickler_app` serves the GTK app and the Mac app (SPEC.md, module `shared-core`)."""
    for package, forbidden in (
        ("stickler_app", {"stickler_gtk"}),
        ("stickler", {"stickler_app", "stickler_gtk"}),
    ):
        files = sorted((ROOT / "src" / package).rglob("*.py"))
        offenders = [str(f.relative_to(ROOT)) for f in files if _imports(f) & forbidden]
        assert offenders == [], f"{package} imports {forbidden}: {offenders}"


def test_verovio_is_the_apps_alone():
    """Verovio (LGPL) engraves for the app; the library and its CLI never import it."""
    files = sorted((ROOT / "src" / "stickler").rglob("*.py"))
    offenders = [str(f.relative_to(ROOT)) for f in files if "verovio" in _imports(f)]
    assert offenders == []


def test_the_app_engraves_with_the_pinned_verovio():
    import verovio

    assert verovio.toolkit().getVersion().startswith("6.4.1")


def test_the_leipzig_font_ships_with_its_licence():
    fonts = ROOT / "packaging" / "fonts"
    assert (fonts / "Leipzig.ttf").read_bytes()[:4] == b"\x00\x01\x00\x00"  # TrueType
    assert "SIL OPEN FONT LICENSE" in (fonts / "OFL.txt").read_text(encoding="utf-8").upper()


def test_one_app_id_for_the_app_and_its_desktop_file():
    assert stickler_app.APP_ID == "ng.tshia.Stickler"
    desktop = configparser.ConfigParser(interpolation=None)
    desktop.optionxform = str
    desktop.read(ROOT / "packaging" / f"{stickler_app.APP_ID}.desktop", encoding="utf-8")
    entry = desktop["Desktop Entry"]
    assert entry["Type"] == "Application"
    assert entry["Exec"].split()[0] == "stickler-gtk"
    assert entry["Icon"] == stickler_app.APP_ID


def test_stickler_gtk_is_an_installed_command():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"]["stickler-gtk"] == "stickler_gtk.main:main"


def test_the_app_icon_and_its_symbolic_variant_ship_in_packaging():
    """GNOME HIG: a 128 x 128 icon and a 16 x 16 symbolic one, named after the app ID."""
    import xml.etree.ElementTree as ET

    icons = ROOT / "packaging" / "icons"
    for name, size in ((stickler_app.APP_ID, "128"), (f"{stickler_app.APP_ID}-symbolic", "16")):
        root = ET.parse(icons / f"{name}.svg").getroot()
        assert (root.get("width"), root.get("height")) == (size, size)
