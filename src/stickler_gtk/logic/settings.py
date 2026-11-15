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
    song_volume: float = 0.7  # playback, 0 to 1; a little down, so the clicks stand out
    hits_volume: float = 1.0


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
    return Settings(
        appearance if appearance in APPEARANCES else Settings.appearance,
        _number(raw.get("zoom"), zoom.SMALLEST, zoom.LARGEST, Settings.zoom),
        _number(raw.get("song_volume"), 0.0, 1.0, Settings.song_volume),
        _number(raw.get("hits_volume"), 0.0, 1.0, Settings.hits_volume),
    )


def _number(value: object, lowest: float, highest: float, default: float) -> float:
    valid = isinstance(value, int | float) and not isinstance(value, bool)
    return float(value) if valid and lowest <= value <= highest else default


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
