"""Export of the MusicXML and the drum track (design screen 8). The app writes only into its
own folders; an export copies or encodes into the place the save dialog returned."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stickler import api
from stickler_app import paths
from stickler_app.i18n import _, ngettext

# Demucs on the development laptop's CPU (docs/requirements.md: real-time factor 1.84)
SEPARATION_PER_SECOND = 1.84
SEPARATOR_DOWNLOAD_GB = 1.2  # environment and weights of Demucs


# the save dialogs propose the opened file's name (owner, 2026-11-15), not the tags' title


def _file_name(song: Path) -> str:
    return song.stem.strip() or "Stickler"


def musicxml_name(song: Path) -> str:
    return f"{_file_name(song)}.musicxml"


def pdf_name(song: Path) -> str:
    return f"{_file_name(song)}.pdf"


def drum_track_name(song: Path) -> str:
    return _("{title} (drums)").format(title=_file_name(song)) + ".flac"


@dataclass(frozen=True)
class Cost:
    minutes: int
    text: str


def drum_track_cost(song_seconds: float, *, download: bool) -> Cost:
    """What a drum track costs, said before it starts: Fast does not separate the drums."""
    minutes = max(1, round(song_seconds * SEPARATION_PER_SECOND / 60))
    text = ngettext(
        "Separating the drums takes about {minutes} minute on this computer.",
        "Separating the drums takes about {minutes} minutes on this computer.",
        minutes,
    ).format(minutes=minutes)
    if download:
        text += " " + _("Before that, Demucs is downloaded once (about {size:n} GB).").format(
            size=SEPARATOR_DOWNLOAD_GB
        )
    return Cost(minutes, text)


def save_musicxml(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest


def drum_track(
    song: Path,
    dest: Path,
    progress: Callable[[api.Step], None],
    cancel: api.CancelToken,
    *,
    setup: bool = False,
) -> Path:
    """Sets up the separator if `setup`, separates the drums (the transcription and beats come
    from the cache) and writes them to `dest` (FLAC, WAV, OGG or MP3 by its suffix)."""
    if setup:
        api.setup_adapters(
            api.DRUM_TRACK_SEPARATOR,
            adapters_root=paths.adapters_root(),
            progress=progress,
            cancel=cancel,
        )
    transcription = api.transcribe_song(
        song,
        drums=True,
        adapters_root=paths.adapters_root(),
        cache_dir=paths.results_cache(),
        progress=progress,
        cancel=cancel,
    )
    if transcription.stem is None:
        raise RuntimeError("no drum track was separated")
    return api.export_drum_track(transcription.stem, dest)
