"""Where the app reads and writes. It writes only into its own folders (in the Flatpak they
are inside the sandbox); songs come in, exports go out through portals."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from stickler import api
from stickler_gtk import APP_ID

AUDIO_SUFFIXES = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".aif", ".aiff"}


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_SUFFIXES


def cache_home(env: Mapping[str, str] = os.environ) -> Path:
    """$XDG_CACHE_HOME/stickler (the Flatpak points XDG_CACHE_HOME into the app's folder)."""
    base = env.get("XDG_CACHE_HOME") or str(Path(env.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "stickler"


def score_path(song: Path, env: Mapping[str, str] = os.environ) -> Path:
    """The MusicXML of a song inside the app's cache; the file name keeps songs with the same
    name in different folders apart."""
    key = hashlib.sha1(str(song.absolute()).encode()).hexdigest()[:10]
    return cache_home(env) / "scores" / f"{song.stem}-{key}.musicxml"


def hits_path(song: Path, env: Mapping[str, str] = os.environ) -> Path:
    """The detected hits of a song as clicks (api.render_hits), next to its score's name."""
    return cache_home(env) / "hits" / f"{score_path(song, env).stem}.wav"


def packaged(env: Mapping[str, str] = os.environ) -> str | None:
    """ "flatpak" or "appimage" when installed as one; None when run from the checkout."""
    if env.get("FLATPAK_ID") == APP_ID:
        return "flatpak"
    if env.get("APPIMAGE"):
        return "appimage"
    return None


def _data_home(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_DATA_HOME") or str(
        Path(env.get("HOME") or Path.home()) / ".local" / "share"
    )
    return Path(base) / "stickler"


def adapters_root(env: Mapping[str, str] = os.environ) -> Path:
    """Where the models are set up: $STICKLER_ADAPTERS (to try a fresh setup without touching
    the models in use); in a packaged app its data folder (SPEC.md, module `packaging`); from
    the checkout the library's folder, as before."""
    chosen = env.get("STICKLER_ADAPTERS")
    if chosen:
        return Path(chosen)
    return _data_home(env) / "adapters" if packaged(env) else api.ADAPTERS_ROOT


def results_cache(env: Mapping[str, str] = os.environ) -> Path:
    """The models' cached results: the app's cache folder when packaged, else the library's."""
    return cache_home(env) / "results" if packaged(env) else api.CACHE_DIR


def packaged_env(env: Mapping[str, str] = os.environ) -> dict[str, str]:
    """What an AppImage sets for itself (the Flatpak's manifest sets the same): where its
    adapters' sources are; that uv uses a Python of its own, never the AppImage's, whose path
    changes with every mount; and that uv keeps its downloads and that Python in Stickler's
    folders. Values already set stay."""
    if packaged(env) != "appimage":
        return {}
    import stickler_gtk

    wanted = {
        "STICKLER_ADAPTER_SOURCES": str(stickler_gtk.prefix(env=env) / "share/stickler/adapters"),
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_PYTHON_DOWNLOADS": "automatic",
        # uv's downloads and Python in Stickler's own folders: removing the app's three folders
        # removes everything, and nothing of another uv user's is touched (owner, 2026-11-15)
        "UV_CACHE_DIR": str(cache_home(env) / "uv"),
        "UV_PYTHON_INSTALL_DIR": str(_data_home(env) / "python"),
    }
    return {key: value for key, value in wanted.items() if key not in env}


def adapter_sources(env: Mapping[str, str] = os.environ) -> Path | None:
    """The adapters' sources a packaged app ships (read-only), set by its launcher."""
    shipped = env.get("STICKLER_ADAPTER_SOURCES")
    return Path(shipped) if shipped else None
