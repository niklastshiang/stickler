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


def test_the_window_speaks_german(monkeypatch):
    from stickler_gtk import i18n
    from stickler_gtk.ui.window import Window

    monkeypatch.setenv("LANGUAGE", "de")
    i18n.setup()  # the catalogues scripts/gtk.sh builds into the app environment
    try:
        labels = _labels(Window())
    finally:
        monkeypatch.setenv("LANGUAGE", "en")
        i18n.setup()
    assert "Song hier ablegen" in labels
    assert "Song öffnen …" in labels
