"""Playback decisions (SPEC.md, module `playback`), without GStreamer: what is heard how loud,
where a bar click or an arrow key goes, and the playback bar's texts. The Mac app gets them
through the bridge (SPEC.md "Mac playback"), and a copy of a song it cannot play."""

from __future__ import annotations

from bisect import bisect_right
from pathlib import Path

from stickler import api
from stickler.audio import media_tool
from stickler_app.i18n import _

HEAR = ("song", "hits", "both")  # design screen 6: Song / Hits / Both


def volumes(hear: str, *, song: float, hits: float) -> tuple[float, float]:
    """The song's and the clicks' volume: the source not heard is silent."""
    return (song if hear != "hits" else 0.0, hits if hear != "song" else 0.0)


def jump_target(bars: list[api.BarTime], written: int, now: float) -> float | None:
    """Where a click on a written bar goes (owner, 2026-11-15): the start of its next pass after
    `now`; inside or after its last pass, its first. None if the song never plays it."""
    starts = [b.start for b in bars if b.written == written]
    if not starts:
        return None
    current = _index(bars, now)
    later = [s for s in starts if current is None or s > bars[current].start]
    return later[0] if later else starts[0]


def _index(bars: list[api.BarTime], now: float) -> int | None:
    k = bisect_right([b.start for b in bars], now) - 1
    return k if k >= 0 else None


def step(bars: list[api.BarTime], now: float, by: int) -> float:
    """The start of the song bar `by` bars away (arrow keys), kept inside the song."""
    if not bars:
        return now
    current = _index(bars, now)
    k = min(max((current if current is not None else 0) + by, 0), len(bars) - 1)
    return bars[k].start


def clock(seconds: float) -> str:
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def bar_label(bars: list[api.BarTime], now: float) -> str:
    """ "Bar 3 of 110": the song bar sounding (played order, repeats counted)."""
    if not bars:
        return ""
    current = _index(bars, now)
    return _label(min((current if current is not None else 0) + 1, len(bars)), len(bars))


def labels(bars: list[api.BarTime]) -> list[str]:
    """Each song bar's "Bar n of N", in played order (the Mac app shows the sounding one)."""
    return [_label(number, len(bars)) for number in range(1, len(bars) + 1)]


def _label(number: int, total: int) -> str:
    return _("Bar {number} of {total}").format(number=number, total=total)


def playable(song: Path, dest: Path) -> Path:
    """A FLAC copy of `song` at `dest`, decoded once with ffmpeg, for a player that cannot
    read the song's own format. RuntimeError, and nothing left behind, when ffmpeg cannot."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part.flac")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(song), "-map", "0:a:0", "-c:a", "flac"]
    proc = media_tool([*cmd, str(part)], capture_output=True, text=True)
    if proc.returncode != 0:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg cannot decode {song.name}: {proc.stderr.strip()[-200:]}")
    part.replace(dest)
    return dest
