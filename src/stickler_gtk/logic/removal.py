"""What "Remove Downloaded Models…" deletes (SPEC.md, module `polish`), without GTK. Only the
installed app's own folders: from the checkout the models are the benchmark's, so nothing.

By default the models with their programs and downloads and the saved analyses go; settings,
recent songs and corrections stay. "Everything" removes Stickler's three folders, as a new
install would have them (owner, 2026-11-15)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from stickler_gtk import APP_ID
from stickler_gtk.logic import paths, settings


def targets(env: Mapping[str, str] = os.environ, *, everything: bool) -> list[Path]:
    if paths.packaged(env) is None:
        return []
    data, cache = paths.data_home(env), paths.cache_home(env)
    if everything:
        chosen = [data, cache, settings.store_path(env).parent]
    else:
        # the models and their environments, uv's Python (AppImage), analyses and uv's downloads
        chosen = [data / "adapters", data / "python", cache]
    sandbox_cache = cache.parent  # in the Flatpak, uv keeps its downloads in the app's own cache
    if paths.packaged(env) == "flatpak" and f"/.var/app/{APP_ID}/" in f"{sandbox_cache}/":
        chosen.append(sandbox_cache / "uv")
    return chosen


def size(folders: list[Path]) -> int:
    """Bytes the folders hold (links not followed)."""
    total = 0
    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                path = Path(root) / name
                if not path.is_symlink():
                    total += path.stat().st_size
    return total


def remove(folders: list[Path]) -> None:
    for folder in folders:
        if folder.exists():
            shutil.rmtree(folder)
