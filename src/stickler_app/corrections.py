"""A song's corrections (SPEC.md, module `corrections`), without GTK: the changes the sidebar's
controls make, kept in range, and the store that remembers them per song."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
from collections.abc import Mapping
from pathlib import Path

from stickler import api
from stickler_app.i18n import _

DETECTED = api.Corrections()
FEWEST_BEATS, MOST_BEATS = 1, 12
FIELDS = ("tempo", "beats_per_bar", "first_downbeat", "simplify", "repeats")


def corrected(fix: api.Corrections) -> bool:
    """Anything to go "Back to Detected" from?"""
    return fix != DETECTED


def with_tempo(fix: api.Corrections, tempo: str) -> api.Corrections:
    """The first one is counted on the corrected beats, which a new tempo changes: it goes
    back to the detected one."""
    if tempo == fix.tempo:
        return fix
    return dataclasses.replace(fix, tempo=tempo, first_downbeat=None)


def with_beats(fix: api.Corrections, beats: int) -> api.Corrections:
    beats = min(max(beats, FEWEST_BEATS), MOST_BEATS)
    first = fix.first_downbeat
    if first is not None and first > beats:  # the same place in a shorter bar
        first = (first - 1) % beats + 1
    return dataclasses.replace(fix, beats_per_bar=beats, first_downbeat=first)


def with_first_one(fix: api.Corrections, beat: int, *, beats_per_bar: int) -> api.Corrections:
    """The first one within the first bar; the beats before it are the pickup."""
    return dataclasses.replace(fix, first_downbeat=min(max(beat, 1), beats_per_bar))


def with_simplify(fix: api.Corrections, on: bool) -> api.Corrections:
    return dataclasses.replace(fix, simplify=on)


def with_repeats(fix: api.Corrections, on: bool) -> api.Corrections:
    return dataclasses.replace(fix, repeats=on)


def beat_label(beat: int) -> str:
    return _("Beat {number}").format(number=beat)


# the store: $XDG_DATA_HOME/stickler/corrections.json, {song path: {field: value}}


def store_path(env: Mapping[str, str] = os.environ) -> Path:
    """Next to the recent songs (the Flatpak points XDG_DATA_HOME into its folder)."""
    base = env.get("XDG_DATA_HOME") or str(
        Path(env.get("HOME") or Path.home()) / ".local" / "share"
    )
    return Path(base) / "stickler" / "corrections.json"


def load(store: Path) -> dict[Path, api.Corrections]:
    """Every song's corrections; an entry that is no longer valid is dropped alone."""
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    found = {}
    for song, values in raw.items():
        fix = _parse(values)
        if fix is not None:
            found[Path(song)] = fix
    return found


def _parse(values: object) -> api.Corrections | None:
    if not isinstance(values, dict):
        return None
    known = {k: v for k, v in values.items() if k in FIELDS}
    with contextlib.suppress(TypeError, ValueError):
        fix = api.Corrections(**known)
        if _types_fit(fix):
            return fix
    return None


def _types_fit(fix: api.Corrections) -> bool:
    numbers = (fix.beats_per_bar, fix.first_downbeat)
    whole = all(n is None or (isinstance(n, int) and not isinstance(n, bool)) for n in numbers)
    return whole and isinstance(fix.simplify, bool) and isinstance(fix.repeats, bool)


def save(store: Path, songs: dict[Path, api.Corrections]) -> None:
    """Writes atomically (a half-written file would lose every song's corrections)."""
    store.parent.mkdir(parents=True, exist_ok=True)
    data = {
        str(song): {k: v for k, v in dataclasses.asdict(fix).items() if v != getattr(DETECTED, k)}
        for song, fix in songs.items()
    }
    part = store.with_suffix(".json.part")
    part.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    part.replace(store)


def remember(store: Path, song: Path, fix: api.Corrections) -> None:
    """Stores a song's corrections; the detected ones remove its entry."""
    songs = load(store)
    if corrected(fix):
        songs[song] = fix
    else:
        songs.pop(song, None)
    save(store, songs)
