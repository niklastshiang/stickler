"""The analysis job the window runs in a worker thread: read the song, then notate it."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from stickler import api


class Unreadable(Exception):
    """The song cannot be read (not audio, or damaged); nothing was analysed."""


def analyse(
    song: Path,
    out: Path,
    progress: Callable[[api.Step], None],
    cancel: api.CancelToken,
    clicks: Path | None = None,
) -> tuple[api.SongInfo, api.Notation]:
    """Fast mode without PDF, the MusicXML at `out`, the detected hits as clicks at `clicks`
    (for playback); raises Unreadable, api.SetupMissing, api.Cancelled or the analysis's own
    error. Clicks that cannot be written are left out: the song still plays on its own."""
    try:
        info = api.song_info(song)
    except RuntimeError as exc:
        raise Unreadable(str(exc)) from exc
    notation = api.notate(
        song,
        out,
        title=info.title,
        artist=info.artist,
        pdf=False,
        progress=progress,
        cancel=cancel,
    )
    if clicks is not None:
        with contextlib.suppress(OSError, RuntimeError):
            api.render_hits(notation.transcription, clicks)
    return info, notation
