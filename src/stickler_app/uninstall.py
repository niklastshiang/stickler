"""What "Uninstall Stickler…" removes, per package, without GTK (SPEC.md "Release 10 (proposed):
keep and remove", scope B). The apps remove the program itself in their own way (the GTK app:
the AppImage to the Bin, PackageKit for the `.deb`/`.rpm`, the Software app for the Flatpak;
the Mac app: its bundle to the Bin); this module says which folders and files go with it.

Stickler's own folders go as for "Remove Downloaded Models…"; with `keep_settings` (the
dialog's box not ticked, the default) the settings, recent songs and corrections stay, so a
new install picks up where the user left off. An AppImage also loses the menu entries and icons
an integration tool made for this very file (Gear Lever, AppImageLauncher, appimaged), never
another app's or another copy's."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from stickler_app import APP_ID, paths, removal

PACKAGE = "stickler"  # the `.deb`'s and the `.rpm`'s name (packaging/nfpm.yaml)


@dataclass(frozen=True)
class Plan:
    kind: str | None  # paths.packaged(): None from the checkout, where nothing is removed
    folders: list[Path]
    files: list[Path]  # an AppImage integration's menu entries and icons
    program: str  # the AppImage's path, the package's name or the Flatpak's id ("" else)
    size: int  # bytes the folders and files hold


def plan(env: Mapping[str, str] = os.environ, *, keep_settings: bool = True) -> Plan:
    kind = paths.packaged(env)
    if kind is None:
        return Plan(None, [], [], "", 0)
    folders = removal.targets(env, everything=not keep_settings)
    files = _integration(env) if kind == "appimage" else []
    program = {"appimage": env.get("APPIMAGE", ""), "system": PACKAGE, "flatpak": APP_ID}
    size = removal.size(folders) + sum(f.stat().st_size for f in files if f.is_file())
    return Plan(kind, folders, files, program.get(kind, ""), size)


def flatpak_command() -> str:
    """For a system whose Software app does not open `appstream:` links (Ubuntu's App Center)."""
    return f"flatpak uninstall --user {APP_ID}"


def _entries(desktop: Path) -> dict[str, str]:
    values = {}
    try:
        lines = desktop.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() not in values:
            values[key.strip()] = value.strip()
    return values


def _integration(env: Mapping[str, str]) -> list[Path]:
    """The menu entries an integration tool made for this AppImage and their icons: an entry
    is this file's when its Exec or TryExec starts with the file's path (Gear Lever) or its
    X-AppImage-Identifier is the MD5 of the file's URI (libappimage: AppImageLauncher and
    appimaged, which also name their icons `appimagekit_<md5>_…`)."""
    image = env.get("APPIMAGE", "")
    if not image:
        return []
    md5 = hashlib.md5(f"file://{image}".encode()).hexdigest()
    data = Path(env.get("XDG_DATA_HOME") or Path(env.get("HOME") or Path.home()) / ".local/share")
    found: list[Path] = []
    for desktop in sorted((data / "applications").glob("*.desktop")):
        values = _entries(desktop)
        commands = [values.get("Exec", ""), values.get("TryExec", "")]
        ours = any(c == image or c.startswith(f"{image} ") for c in commands)
        if not (ours or values.get("X-AppImage-Identifier") == md5):
            continue
        found.append(desktop)
        icon = values.get("Icon", "")
        if icon.startswith("/"):
            if Path(icon).is_file():
                found.append(Path(icon))
        elif icon.startswith(f"appimagekit_{md5}"):
            found.extend(sorted((data / "icons").glob(f"*/*/apps/{icon}.*")))
    return found


def remove(chosen: Plan) -> None:
    """Deletes the plan's folders and files; what is already gone is fine."""
    for folder in chosen.folders:
        if folder.exists():
            shutil.rmtree(folder)
    for file in chosen.files:
        file.unlink(missing_ok=True)
