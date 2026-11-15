"""The app's settings: today only the appearance (design screen 9), stored as JSON in
$XDG_CONFIG_HOME/stickler/settings.json."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

APPEARANCES = ("system", "light", "dark")


@dataclass(frozen=True)
class Settings:
    appearance: str = "system"  # follow the system's light or dark style


def store_path(env: Mapping[str, str] = os.environ) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME") or Path.home()) / ".config")
    return Path(base) / "stickler" / "settings.json"


def load(store: Path) -> Settings:
    """The stored settings; the defaults where there are none or they cannot be read."""
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
        appearance = raw["appearance"]
    except (OSError, ValueError, TypeError, KeyError):
        return Settings()
    return Settings(appearance) if appearance in APPEARANCES else Settings()


def save(store: Path, chosen: Settings) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    part = store.with_suffix(".json.part")
    part.write_text(json.dumps(asdict(chosen), indent=1), encoding="utf-8")
    part.replace(store)
