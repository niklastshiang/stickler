"""Back Up… and Restore Backup… without GTK (SPEC.md "Release 10 (proposed): keep and remove",
scope A). One zip keeps what a user would miss on a new computer: the settings, the recent
songs, the corrections and the models' results (keyed by the song's content and the model's
code, so they are found again wherever the song now lies). Not in it: the models and their
programs (downloaded again), the separated drum tracks (made again by the next export), the
engraved scores and clicks (made again from the results), the user's songs and exports."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path, PurePosixPath

import stickler
from stickler_app import corrections, paths, recent, settings
from stickler_app.i18n import _

FORMAT = 1  # raised when a backup's layout changes; a newer one is refused
# A restore unpacks into a temporary folder (tmpfs on Fedora): a backup that would unpack to
# more is refused before anything is written. Results take well under a megabyte per song.
MAX_UNPACKED = 2 * 1024**3
MAX_FILES = 200_000
SEPARATORS = ("demucs", "roformer")  # their results are whole drum tracks: left out
META = "backup.json"
STORES = ("settings.json", "recent.json", "corrections.json")
RESULTS = "results"


class NotABackup(Exception):
    """The file is no backup this app can read: broken, foreign or of a newer format."""


@dataclass(frozen=True)
class Summary:
    created: date
    songs: int  # songs with saved analyses
    size: int  # bytes of the file


def question(summary: Summary, size: str) -> str:
    """The restore's question: what the backup holds and what happens (both apps show it)."""
    return _(
        "Made on {date}, analysed songs: {songs}, {size}. Songs and corrections already on"
        " this computer stay; the settings are replaced."
    ).format(date=summary.created.isoformat(), songs=summary.songs, size=size)


def file_name(today: date) -> str:
    return f"Stickler Backup {today.isoformat()}.zip"


def _stores(env: Mapping[str, str]) -> dict[str, Path]:
    return {
        "settings.json": settings.store_path(env),
        "recent.json": recent.store_path(env),
        "corrections.json": corrections.store_path(env),
    }


def _results(env: Mapping[str, str]) -> list[tuple[str, Path]]:
    """Every saved result file as (its name inside the zip, its path), without separators."""
    root = paths.results_cache(env)
    found = []
    if root.is_dir():
        for adapter in sorted(p for p in root.iterdir() if p.is_dir()):
            # the separators' tracks, and the analysis's own folders (`_decoded`: a FLAC copy of
            # an mp3 or m4a song, the song itself)
            if adapter.name in SEPARATORS or adapter.name.startswith("_"):
                continue
            for path in sorted(adapter.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    found.append((f"{RESULTS}/{path.relative_to(root).as_posix()}", path))
    return found


def _songs(names: list[str]) -> int:
    """Songs with saved analyses: the most result folders any one model has."""
    folders: dict[str, set[str]] = {}
    for name in names:
        parts = PurePosixPath(name).parts
        if len(parts) >= 4 and parts[0] == RESULTS:
            folders.setdefault(parts[1], set()).add(parts[2])
    return max((len(keys) for keys in folders.values()), default=0)


def write(dest: Path, env: Mapping[str, str] = os.environ, today: date | None = None) -> Summary:
    """Writes the backup to `dest` (through a partial file: a broken one never replaces it)."""
    created = today or date.today()
    results = _results(env)
    meta = {
        "format": FORMAT,
        "app": stickler.__version__,
        "created": created.isoformat(),
        "system": paths.packaged(env) or "checkout",
    }
    part = dest.with_name(dest.name + ".part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(META, json.dumps(meta, indent=1))
        for name, path in _stores(env).items():
            if path.is_file():
                z.write(path, name)
        for name, path in results:
            z.write(path, name)
    part.replace(dest)
    return Summary(created, _songs([n for n, _ in results]), dest.stat().st_size)


def _checked(src: Path) -> tuple[zipfile.ZipFile, dict]:
    try:
        z = zipfile.ZipFile(src)
    except (OSError, zipfile.BadZipFile) as exc:
        raise NotABackup(str(exc)) from exc
    try:
        meta = json.loads(z.read(META))
        fmt, created = meta["format"], date.fromisoformat(meta["created"])
    except (KeyError, ValueError, TypeError) as exc:
        z.close()
        raise NotABackup("not a Stickler backup") from exc
    if not isinstance(fmt, int) or fmt > FORMAT:
        z.close()
        raise NotABackup("made by a newer Stickler")
    infos = z.infolist()
    if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED:
        z.close()
        raise NotABackup("too large to be a Stickler backup")
    for name in z.namelist():
        parts = PurePosixPath(name).parts
        result = len(parts) >= 4 and parts[0] == RESULTS and not parts[1].startswith("_")
        safe = name in (META, *STORES) or result
        if not safe or ".." in parts or name.startswith("/"):
            z.close()
            raise NotABackup(f"an unexpected file: {name}")
    meta["created"] = created
    return z, meta


def read(src: Path) -> Summary:
    """What the backup holds, for the question before a restore; NotABackup if it is none."""
    z, meta = _checked(src)
    with z:
        return Summary(meta["created"], _songs(z.namelist()), src.stat().st_size)


def restore(src: Path, env: Mapping[str, str] = os.environ) -> None:
    """Adds the backup's results, recent songs and corrections this computer does not have yet
    (an entry here stays), and takes its settings, except the consent to download the models,
    which stays this computer's."""
    z, _meta = _checked(src)
    with z, tempfile.TemporaryDirectory() as tmp:
        unpacked = Path(tmp)
        z.extractall(unpacked)
        _restore_results(unpacked / RESULTS, paths.results_cache(env))
        stores = _stores(env)
        _restore_recent(unpacked / "recent.json", stores["recent.json"])
        _restore_corrections(unpacked / "corrections.json", stores["corrections.json"])
        _restore_settings(unpacked / "settings.json", stores["settings.json"])


def _restore_results(source: Path, cache: Path) -> None:
    if not source.is_dir():
        return
    for adapter in source.iterdir():
        for key in (k for k in adapter.iterdir() if k.is_dir()):
            target = cache / adapter.name / key.name
            if not target.exists():  # a result here stays
                # through a partial folder: a half-copied result is never taken for a whole one
                part = target.with_name(target.name + ".part")
                shutil.rmtree(part, ignore_errors=True)
                shutil.copytree(key, part)
                part.rename(target)


def _restore_recent(source: Path, store: Path) -> None:
    if not source.is_file():
        return
    here = recent.load(store)
    known = {s.path for s in here} | {s.digest for s in here if s.digest}
    added = [s for s in recent.load(source) if s.path not in known and s.digest not in known]
    if added:
        recent.save(store, (here + added)[: recent.LIMIT])


def _restore_corrections(source: Path, store: Path) -> None:
    if not source.is_file():
        return
    here = corrections.entries(store)
    digests = {v.get("digest") for v in here.values() if v.get("digest")}
    added = {
        song: values
        for song, values in corrections.entries(source).items()
        if song not in here and values.get("digest") not in digests
    }
    if added:
        corrections.write_entries(store, here | added)


def _restore_settings(source: Path, store: Path) -> None:
    if not source.is_file():
        return
    chosen = settings.load(source)
    settings.save(store, replace(chosen, setup_agreed=settings.load(store).setup_agreed))
