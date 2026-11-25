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
from stickler_app import paths
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


@dataclasses.dataclass(frozen=True)
class Controls:
    """What the corrections controls show, in every app (SPEC.md "Mac corrections")."""

    tempo: str
    beats_per_bar: int
    first_one: int
    first_one_label: str
    earlier: bool  # the first one can move to an earlier beat
    later: bool
    simplify: bool
    repeats: bool
    corrected: bool  # "Back to Detected" has something to undo


def controls(fix: api.Corrections, *, beats_per_bar: int, first_one: int) -> Controls:
    """`fix` as the controls show it; `beats_per_bar` and `first_one` as engraved, for the
    values the reader has not set (the engraved first one kept within a corrected bar)."""
    beats = fix.beats_per_bar or beats_per_bar
    first = fix.first_downbeat or min(first_one, beats)
    return Controls(
        tempo=fix.tempo,
        beats_per_bar=beats,
        first_one=first,
        first_one_label=beat_label(first),
        earlier=first > 1,
        later=first < beats,
        simplify=fix.simplify,
        repeats=fix.repeats,
        corrected=corrected(fix),
    )


CHANGES = (
    "tempo",
    "beats_per_bar",
    "beats_per_bar_by",
    "first_one",
    "first_one_by",
    "simplify",
    "repeats",
    "detected",
)


def change(
    fix: api.Corrections, name: str, value: str | int | bool, *, shown: Controls
) -> api.Corrections:
    """One control's change, kept in range. `shown` is what the controls show for `fix`; the
    `_by` changes step from it (a stepper's click, counted on the newest values). `name` is
    one of CHANGES and `value` of its type (the caller checks them)."""
    if name == "tempo":
        return with_tempo(fix, str(value))
    if name in ("beats_per_bar", "beats_per_bar_by"):
        base = shown.beats_per_bar if name.endswith("_by") else 0
        return with_beats(fix, base + int(value))
    if name in ("first_one", "first_one_by"):
        base = shown.first_one if name.endswith("_by") else 0
        return with_first_one(fix, base + int(value), beats_per_bar=shown.beats_per_bar)
    if name == "simplify":
        return with_simplify(fix, bool(value))
    if name == "repeats":
        return with_repeats(fix, bool(value))
    return DETECTED


# the store: corrections.json in the app's data folder, {song path: {field: value}}


def store_path(env: Mapping[str, str] = os.environ) -> Path:
    """Next to the recent songs (the Flatpak points XDG_DATA_HOME into its folder)."""
    return paths.data_home(env) / "corrections.json"


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


def entries(store: Path) -> dict[str, dict]:
    """The stored entries as written: {song path: {field: value, "digest": …}}."""
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def write_entries(store: Path, raw: dict[str, dict]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    part = store.with_suffix(".json.part")
    part.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    part.replace(store)


def remember(store: Path, song: Path, fix: api.Corrections, digest: str = "") -> None:
    """Stores a song's corrections with its content's digest (paths.song_digest), so they are
    found again after the song moved; the detected ones remove its entry."""
    raw = entries(store)
    key = str(song)
    digest = digest or raw.get(key, {}).get("digest", "")
    if digest:  # an entry of the same song at another path is this one, moved
        raw = {k: v for k, v in raw.items() if k == key or v.get("digest") != digest}
    if corrected(fix):
        values = {k: v for k, v in dataclasses.asdict(fix).items() if v != getattr(DETECTED, k)}
        raw[key] = values | ({"digest": digest} if digest else {})
    else:
        raw.pop(key, None)
    write_entries(store, raw)


def lookup(store: Path, song: Path, digest: str) -> api.Corrections:
    """The song's corrections, found by its path or, when it moved (or came from a backup), by
    its content; the entry then moves to the new path, and one without a digest gets it
    (SPEC.md "Release 10", scope A3). An unknown song has the detected values."""
    raw = entries(store)
    key = str(song)
    found = (
        key
        if key in raw
        else next((k for k, v in raw.items() if digest and v.get("digest") == digest), None)
    )
    if found is None:
        return DETECTED
    fix = _parse(raw[found])
    if fix is None:
        return DETECTED
    if digest and (found != key or raw[found].get("digest") != digest):
        values = raw.pop(found)
        raw[key] = values | {"digest": digest}
        with contextlib.suppress(OSError):  # the corrections still apply this time
            write_entries(store, raw)
    return fix
