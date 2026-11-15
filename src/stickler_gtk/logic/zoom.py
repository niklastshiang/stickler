"""Zoom of the sheet music (SPEC.md, module `sheet-view`): 1.0 is the window's width."""

from __future__ import annotations

SMALLEST, LARGEST = 0.5, 3.0
STEP = 1.25  # one Ctrl+plus or Ctrl+minus


def _clamp(value: float) -> float:
    return min(LARGEST, max(SMALLEST, value))


def zoom_in(current: float) -> float:
    return _clamp(current * STEP)


def zoom_out(current: float) -> float:
    return _clamp(current / STEP)


def scrolled(current: float, dy: float) -> float:
    """Ctrl+scroll: `dy` < 0 (up) enlarges, a step per notch, finer for touchpads."""
    return _clamp(current * STEP ** (-dy))


def pinched(start: float, scale: float) -> float:
    """A pinch on a touchpad or touchscreen: the zoom it began at times the gesture's scale."""
    return _clamp(start * scale)
