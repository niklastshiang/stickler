"""The app's boundaries: GTK stays out of the library and the app's logic; one app ID."""

import ast
import configparser
import tomllib
from pathlib import Path

import stickler_gtk

ROOT = Path(__file__).resolve().parents[2]
NO_GTK = [ROOT / "src" / "stickler", ROOT / "src" / "stickler_gtk" / "logic"]


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


def test_one_app_id_for_the_app_and_its_desktop_file():
    assert stickler_gtk.APP_ID == "ng.tshia.Stickler"
    desktop = configparser.ConfigParser(interpolation=None)
    desktop.optionxform = str
    desktop.read(ROOT / "packaging" / f"{stickler_gtk.APP_ID}.desktop", encoding="utf-8")
    entry = desktop["Desktop Entry"]
    assert entry["Type"] == "Application"
    assert entry["Exec"].split()[0] == "stickler-gtk"
    assert entry["Icon"] == stickler_gtk.APP_ID


def test_stickler_gtk_is_an_installed_command():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"]["stickler-gtk"] == "stickler_gtk.main:main"
