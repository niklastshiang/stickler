"""Playback decisions (SPEC.md, module `playback`), without GStreamer: what is heard how loud,
where a bar click or an arrow key goes, and the playback bar's texts."""

from __future__ import annotations

from bisect import bisect_right

from stickler import api
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
    number = min((current if current is not None else 0) + 1, len(bars))
    return _("Bar {number} of {total}").format(number=number, total=len(bars))
