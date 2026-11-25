"""Where the app reads and writes. It writes only into its own folders (in the Flatpak they
are inside the sandbox); songs come in, exports go out through portals. On Linux these are the
XDG folders; the Mac app keeps its files in Apple's folders under ~/Library (SPEC.md, module
`core-bridge`), unless XDG variables are set."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from stickler import api
from stickler_app import APP_ID

AUDIO_SUFFIXES = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".aif", ".aiff"}


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_SUFFIXES


MAC_NAME = "Stickler"  # the folder under ~/Library/Application Support and ~/Library/Caches


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME") or Path.home())


def _mac(env: Mapping[str, str], folder: str) -> Path:
    return _home(env) / "Library" / folder / MAC_NAME


def cache_home(env: Mapping[str, str] = os.environ) -> Path:
    """$XDG_CACHE_HOME/stickler (the Flatpak points XDG_CACHE_HOME into the app's folder); in
    the Mac app ~/Library/Caches/Stickler."""
    if env.get("XDG_CACHE_HOME"):
        return Path(env["XDG_CACHE_HOME"]) / "stickler"
    if packaged(env) == "macos":
        return _mac(env, "Caches")
    return _home(env) / ".cache" / "stickler"


def score_path(song: Path, env: Mapping[str, str] = os.environ) -> Path:
    """The MusicXML of a song inside the app's cache; the file name keeps songs with the same
    name in different folders apart."""
    key = hashlib.sha1(str(song.absolute()).encode()).hexdigest()[:10]
    return cache_home(env) / "scores" / f"{song.stem}-{key}.musicxml"


def song_digest(song: Path) -> str:
    """The song's content as the models' results cache keys it (SHA-1 of the file), so a song is
    found again after it moved or on another computer (SPEC.md "Release 10", scope A3); empty
    when it cannot be read."""
    try:
        with song.open("rb") as f:
            return hashlib.file_digest(f, "sha1").hexdigest()
    except OSError:
        return ""


def hits_path(song: Path, env: Mapping[str, str] = os.environ) -> Path:
    """The detected hits of a song as clicks (api.render_hits), next to its score's name."""
    return cache_home(env) / "hits" / f"{score_path(song, env).stem}.wav"


def playable_path(song: Path, env: Mapping[str, str] = os.environ) -> Path:
    """A FLAC copy of a song the Mac app cannot play itself, next to its score's name."""
    return cache_home(env) / "playable" / f"{score_path(song, env).stem}.flac"


def packaged(env: Mapping[str, str] = os.environ) -> str | None:
    """ "flatpak", "appimage", "macos" or "system" (a `.deb` or `.rpm`) when installed as one;
    None when run from the checkout. The launchers of the Mac app and of the `.deb`/`.rpm` set
    STICKLER_PACKAGED."""
    if env.get("FLATPAK_ID") == APP_ID:
        return "flatpak"
    if env.get("APPIMAGE") and env.get("SHARUN_DIR"):  # ours: another AppImage has no SHARUN_DIR
        return "appimage"
    if env.get("STICKLER_PACKAGED") in ("macos", "system"):
        return env["STICKLER_PACKAGED"]
    return None


def data_home(env: Mapping[str, str] = os.environ) -> Path:
    """$XDG_DATA_HOME/stickler; in the Mac app ~/Library/Application Support/Stickler."""
    if env.get("XDG_DATA_HOME"):
        return Path(env["XDG_DATA_HOME"]) / "stickler"
    if packaged(env) == "macos":
        return _mac(env, "Application Support")
    return _home(env) / ".local" / "share" / "stickler"


def config_home(env: Mapping[str, str] = os.environ) -> Path:
    """$XDG_CONFIG_HOME/stickler; in the Mac app the settings sit with its data."""
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"]) / "stickler"
    if packaged(env) == "macos":
        return _mac(env, "Application Support")
    return _home(env) / ".config" / "stickler"


def adapters_root(env: Mapping[str, str] = os.environ) -> Path:
    """Where the models are set up: $STICKLER_ADAPTERS (to try a fresh setup without touching
    the models in use); in a packaged app its data folder (SPEC.md, module `packaging`); from
    the checkout the library's folder, as before."""
    chosen = env.get("STICKLER_ADAPTERS")
    if chosen:
        return Path(chosen)
    return data_home(env) / "adapters" if packaged(env) else api.ADAPTERS_ROOT


def results_cache(env: Mapping[str, str] = os.environ) -> Path:
    """The models' cached results: $STICKLER_RESULTS_CACHE (the README's recording starts from
    an empty one, so its analysis really runs); the app's cache folder when packaged (the Mac
    app's data folder: macOS may empty Caches, and a result takes minutes), else the
    library's."""
    chosen = env.get("STICKLER_RESULTS_CACHE")
    if chosen:
        return Path(chosen)
    kind = packaged(env)
    if kind == "macos" and not env.get("XDG_CACHE_HOME"):
        return data_home(env) / "results"
    return cache_home(env) / "results" if kind else api.CACHE_DIR


def packaged_env(env: Mapping[str, str] = os.environ) -> dict[str, str]:
    """What an AppImage sets for itself (the Flatpak's manifest sets the same), a `.deb` or
    `.rpm` (module `linux-packages`), and the Mac app that brings its own core (module
    `mac-package`): where its adapters' sources are; that
    uv uses a Python of its own, never the AppImage's, whose path changes with every mount; and
    that uv keeps its downloads and that Python in Stickler's folders. The Python settings
    always apply (otherwise uv may take the AppImage's own); other values already set stay."""
    kind = packaged(env)
    if kind not in ("appimage", "macos", "system"):
        return {}
    import stickler_app

    shipped = stickler_app.prefix(env=env) / "share/stickler/adapters"
    if kind == "macos" and not shipped.is_dir():
        return {}  # the Mac app over a checkout (`uv run`): the folder's own uv and Pythons
    wanted = {
        "STICKLER_ADAPTER_SOURCES": str(shipped),
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_PYTHON_DOWNLOADS": "automatic",
        # uv's downloads and Python in Stickler's own folders: removing the app's three folders
        # removes everything, and nothing of another uv user's is touched (owner, 2026-11-15)
        "UV_CACHE_DIR": str(cache_home(env) / "uv"),
        "UV_PYTHON_INSTALL_DIR": str(data_home(env) / "python"),
    }
    forced = ("UV_PYTHON_PREFERENCE", "UV_PYTHON_DOWNLOADS")  # requirements, not preferences
    return {key: value for key, value in wanted.items() if key in forced or key not in env}


def adapter_sources(env: Mapping[str, str] = os.environ) -> Path | None:
    """The adapters' sources a packaged app ships (read-only), set by its launcher."""
    shipped = env.get("STICKLER_ADAPTER_SOURCES")
    return Path(shipped) if shipped else None
