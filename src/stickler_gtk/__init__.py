"""Stickler's GTK application. It uses only `stickler.api`; `logic/` holds what the window
decides (no GTK), `ui/` the widgets that show it."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

APP_ID = "ng.tshia.Stickler"
APP_NAME = "Stickler"  # a name, not translated


def prefix(
    module_file: Path | None = None,
    sys_prefix: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Where the app is installed: in the Flatpak /app, while Python's own prefix is the
    runtime's /usr; in an AppImage its mounted folder ($SHARUN_DIR). From the checkout (an
    editable install) Python's prefix, as before. Translations, icons and fonts lie below it."""
    env = os.environ if env is None else env
    if env.get("APPIMAGE") and env.get("SHARUN_DIR"):
        return Path(env["SHARUN_DIR"])
    here = Path(module_file or __file__)
    parts = here.parts
    if "site-packages" in parts and parts.index("site-packages") >= 3:
        k = parts.index("site-packages")
        if parts[k - 2] == "lib":  # <prefix>/lib/pythonX.Y/site-packages/stickler_gtk
            return Path(*parts[: k - 2])
    return Path(sys_prefix if sys_prefix is not None else sys.prefix)
