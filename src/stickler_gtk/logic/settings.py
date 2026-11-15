"""The app's settings: the appearance and the note size (design screen 9), stored as JSON in
$XDG_CONFIG_HOME/stickler/settings.json. A missing or bad value falls back to its default
without spoiling the others."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from stickler_gtk.logic import zoom

APPEARANCES = ("system", "light", "dark")


@dataclass(frozen=True)
class Settings:
    appearance: str = "system"  # follow the system's light or dark style
    zoom: float = 1.0  # note size: 1.0 is the window's width


def store_path(env: Mapping[str, str] = os.environ) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME") or Path.home()) / ".config")
    return Path(base) / "stickler" / "settings.json"


def load(store: Path) -> Settings:
    """The stored settings; the default for each one that is missing or cannot be read."""
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    appearance = raw.get("appearance")
    size = raw.get("zoom")
    valid_size = isinstance(size, int | float) and zoom.SMALLEST <= size <= zoom.LARGEST
    return Settings(
        appearance if appearance in APPEARANCES else Settings.appearance,
        float(size) if valid_size else Settings.zoom,
    )


def save(store: Path, chosen: Settings) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    part = store.with_suffix(".json.part")
    part.write_text(json.dumps(asdict(chosen), indent=1), encoding="utf-8")
    part.replace(store)


def update(store: Path, **changes) -> Settings:
    """Changes some settings and keeps the others."""
    chosen = replace(load(store), **changes)
    save(store, chosen)
    return chosen
