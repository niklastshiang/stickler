"""From song time, or a click, to the marked bar (SPEC.md, module `sheet-view`).

Song time → the song bar sounding then (`api.Notation.bars`, played order) → the written bar
it is engraved as → that bar's rectangle on a page. `playback` calls `written_at` with its
position; the sheet calls `bar_at_point` for a click."""

from __future__ import annotations

from bisect import bisect_right

from stickler import api
from stickler_gtk.logic.engraving import Box, Page


def written_at(bars: list[api.BarTime], seconds: float) -> int | None:
    """The written bar sounding at `seconds`; None before the first or after the last bar."""
    k = bisect_right([b.start for b in bars], seconds) - 1
    if k < 0 or seconds >= bars[k].end:
        return None
    return bars[k].written


def locate(pages: list[Page], written: int) -> tuple[int, Box] | None:
    """The page and rectangle of a written bar. A bar without a rectangle of its own (inside a
    multi-measure rest) is shown by the nearest engraved bar before it."""
    engraved = sorted((n, k) for k, page in enumerate(pages) for n in page.bars)
    before = [(n, k) for n, k in engraved if n <= written]
    if not before:
        return None
    n, k = before[-1]
    return k, pages[k].bars[n]


def bar_at_point(page: Page, x: float, y: float) -> int | None:
    """The written bar whose rectangle holds the point (page pixels)."""
    return next((n for n, box in page.bars.items() if box.contains(x, y)), None)
