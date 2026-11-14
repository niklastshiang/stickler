"""Widget smoke tests: need GTK and a display, so they run on the system Python only
(`scripts/gtk.sh test`), not in the default run or CI."""

import pytest

pytestmark = pytest.mark.gtk


def _labels(widget) -> list[str]:
    """Every label text and button label below `widget`."""
    found = []
    child = widget.get_first_child()
    while child is not None:
        for getter in ("get_label", "get_title"):
            text = getattr(child, getter, lambda: None)()
            if isinstance(text, str) and text:
                found.append(text)
        found.extend(_labels(child))
        child = child.get_next_sibling()
    return found


def test_the_empty_window_offers_to_open_a_song():
    from stickler_gtk.ui.window import Window

    window = Window()
    assert window.get_title() == "Stickler"
    labels = _labels(window)
    assert "Drop a Song Here" in labels
    assert "Open a Song…" in labels
