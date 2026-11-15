"""Where the app reads and writes. It writes only into its own folders (in the Flatpak they
are inside the sandbox); songs come in, exports go out through portals."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

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
