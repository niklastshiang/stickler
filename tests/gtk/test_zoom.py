"""Zoom of the sheet music: Ctrl+plus/minus in steps, Ctrl+scroll, Ctrl+0 (SPEC sheet-view)."""

import pytest

from stickler_gtk.logic import zoom


def test_steps_go_up_and_down_and_stop_at_the_limits():
    assert zoom.zoom_in(1.0) == pytest.approx(1.25)
    assert zoom.zoom_out(zoom.zoom_in(1.0)) == pytest.approx(1.0)
    assert zoom.zoom_in(zoom.LARGEST) == zoom.LARGEST
    assert zoom.zoom_out(zoom.SMALLEST) == zoom.SMALLEST


def test_scrolling_zooms_in_one_way_and_out_the_other():
    assert zoom.scrolled(1.0, -1.0) > 1.0  # scrolling up enlarges, as in GNOME's viewers
    assert zoom.scrolled(1.0, 1.0) < 1.0
    assert zoom.scrolled(1.0, 0.0) == 1.0
    assert zoom.scrolled(zoom.LARGEST, -50.0) == zoom.LARGEST


def test_a_pinch_scales_the_zoom_it_started_from_within_the_limits():
    """Touchpad and touchscreen pinch (owner, 2026-11-15: zoom did not work on the touchpad)."""
    assert zoom.pinched(1.0, 1.5) == pytest.approx(1.5)
    assert zoom.pinched(2.0, 0.5) == pytest.approx(1.0)
    assert zoom.pinched(2.0, 10.0) == zoom.LARGEST
    assert zoom.pinched(1.0, 0.1) == zoom.SMALLEST
