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

import contextlib
import hashlib
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from stickler_app import APP_ID, paths, removal, settings

PACKAGE = "stickler"  # the `.deb`'s and the `.rpm`'s name (packaging/nfpm.yaml)
# PackageKit's numbers (its D-Bus API): the filter for installed packages, a successful exit
INSTALLED = 1 << 2  # PK_FILTER_ENUM_INSTALLED as a bitfield
SUCCESS = 1  # PK_EXIT_ENUM_SUCCESS


@dataclass(frozen=True)
class Plan:
    kind: str | None  # paths.packaged(): None from the checkout, where nothing is removed
    folders: list[Path]
    files: list[Path]  # an AppImage integration's menu entries and icons
    program: str  # the AppImage's path, the package's name or the Flatpak's id ("" else)
    size: int  # bytes the folders and files hold
    keep_settings: bool = True


def plan(env: Mapping[str, str] = os.environ, *, keep_settings: bool = True) -> Plan:
    kind = paths.packaged(env)
    if kind is None:
        return Plan(None, [], [], "", 0)
    folders = removal.targets(env, everything=not keep_settings)
    files = _integration(env) if kind == "appimage" else []
    program = {"appimage": env.get("APPIMAGE", ""), "system": PACKAGE, "flatpak": APP_ID}
    size = removal.size(folders) + sum(f.stat().st_size for f in files if f.is_file())
    return Plan(kind, folders, files, program.get(kind, ""), size, keep_settings)


def terminal_command(fedora_marker: str = "/etc/fedora-release") -> str:
    """For a `.deb`/`.rpm` PackageKit could not remove (found 2026-11-22 in a Fedora 45
    container: after an install through dnf5daemon, PackageKit's dnf5 backend listed no
    installed package at all): the line to run instead; nothing of Stickler's is removed then."""
    tool = "dnf" if Path(fedora_marker).exists() else "apt"
    return f"sudo {tool} remove {PACKAGE}"


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
    # libappimage hashes the file's URI, escaped where the path needs it; both forms are this file
    md5s = {hashlib.md5(f"file://{form}".encode()).hexdigest() for form in (image, quote(image))}
    data = Path(env.get("XDG_DATA_HOME") or Path(env.get("HOME") or Path.home()) / ".local/share")
    # an icon is deleted only from where the tools put them: never a picture of the user's own
    icon_folders = (data / "icons", Path(image).parent / ".icons")
    found: list[Path] = []
    for desktop in sorted((data / "applications").glob("*.desktop")):
        values = _entries(desktop)
        commands = [values.get("Exec", ""), values.get("TryExec", "")]
        ours = any(_runs(c, image) for c in commands)
        if not (ours or values.get("X-AppImage-Identifier") in md5s):
            continue
        found.append(desktop)
        icon = values.get("Icon", "")
        if icon.startswith("/"):
            path = Path(icon)
            if path.is_file() and any(path.is_relative_to(f) for f in icon_folders):
                found.append(path)
        elif any(icon.startswith(f"appimagekit_{md5}") for md5 in md5s):
            found.extend(sorted((data / "icons").glob(f"*/*/apps/{icon}.*")))
    return found


def _runs(command: str, image: str) -> bool:
    """Whether a desktop entry's Exec or TryExec starts this file, quoted or not."""
    line = command.strip()
    if line.startswith('"'):
        return line[1:].split('"', 1)[0] == image
    return line == image or line.startswith(f"{image} ")


def chosen_package(name: str, package_ids: list[str]) -> str | None:
    """The installed package `name` among PackageKit's ids ("name;version;arch;data")."""
    return next((p for p in package_ids if p.split(";")[0] == name), None)


def transaction_failed(exit_code: int, error: str) -> str | None:
    """None when a PackageKit transaction succeeded, else why not (a cancelled password
    prompt included: then nothing changed)."""
    if error:
        return error
    return None if exit_code == SUCCESS else "the package was not removed"


def remove(chosen: Plan, env: Mapping[str, str] = os.environ) -> None:
    """Deletes the plan's folders and files; what is already gone is fine. Kept settings forget
    the consent to download the models, as "Remove Downloaded Models…" does: a new install asks
    again before it downloads gigabytes."""
    if chosen.kind is not None and chosen.keep_settings:
        with contextlib.suppress(OSError):
            if settings.store_path(env).exists():
                settings.update(settings.store_path(env), setup_agreed=False)
    for folder in chosen.folders:
        if folder.exists():
            shutil.rmtree(folder)
    for file in chosen.files:
        with contextlib.suppress(OSError):  # an entry the user cannot delete stays
            file.unlink(missing_ok=True)
