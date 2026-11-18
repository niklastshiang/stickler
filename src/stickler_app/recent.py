"""Recent songs (design screen 4): newest first, at most LIMIT, stored as JSON in the XDG data
folder. A song is added once its analysis has finished."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from stickler_app import paths
from stickler_app.i18n import _

LIMIT = 10


@dataclass(frozen=True)
class Recent:
    path: Path
    title: str
    artist: str
    opened: date


@dataclass(frozen=True)
class Row:
    path: Path
    title: str
    detail: str
    missing: bool  # the file is gone: the row can only be removed


def store_path(env: Mapping[str, str] = os.environ) -> Path:
    """$XDG_DATA_HOME/stickler/recent.json (the Flatpak points XDG_DATA_HOME into its folder;
    the Mac app's data folder, see paths.data_home)."""
    return paths.data_home(env) / "recent.json"


def add(songs: list[Recent], song: Recent) -> list[Recent]:
    others = [s for s in songs if s.path != song.path]
    return [song, *others][:LIMIT]


def remove(songs: list[Recent], path: Path) -> list[Recent]:
    return [s for s in songs if s.path != path]


def load(store: Path) -> list[Recent]:
    """The stored list; an empty one if there is none or it cannot be read."""
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
        songs = [
            Recent(Path(e["path"]), e["title"], e["artist"], date.fromisoformat(e["opened"]))
            for e in raw
        ]
    except (OSError, ValueError, TypeError, KeyError):
        return []
    return songs[:LIMIT]


def save(store: Path, songs: list[Recent]) -> None:
    """Writes the list atomically (a half-written file would lose it)."""
    store.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {"path": str(s.path), "title": s.title, "artist": s.artist, "opened": s.opened.isoformat()}
        for s in songs
    ]
    part = store.with_suffix(".json.part")
    part.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    part.replace(store)


def _when(opened: date, today: date) -> str:
    if opened == today:
        return _("opened today")
    if opened == today - timedelta(days=1):
        return _("opened yesterday")
    # Translators: a date in strftime format, as in "12 November"
    return _("opened {date}").format(date=opened.strftime(_("%-d %B")))


def rows(
    songs: list[Recent],
    *,
    today: date | None = None,
    exists: Callable[[Path], bool] = Path.exists,
) -> list[Row]:
    today = today or date.today()
    shown = []
    for song in songs:
        missing = not exists(song.path)
        when = _("file not found") if missing else _when(song.opened, today)
        detail = " · ".join(p for p in (song.artist, when) if p)
        shown.append(Row(song.path, song.title, detail, missing))
    return shown


def opened_now(song: Path, title: str, artist: str) -> Recent:
    return Recent(song, title, artist, date.today())
