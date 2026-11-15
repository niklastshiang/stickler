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


def _find(widget, predicate) -> list:
    """Every widget below `widget` (itself included) for which `predicate` holds."""
    found = [widget] if predicate(widget) else []
    child = widget.get_first_child()
    while child is not None:
        found += _find(child, predicate)
        child = child.get_next_sibling()
    return found


def _wait(predicate, seconds=5.0) -> bool:
    """Runs the main loop until `predicate()` holds (the worker reports through it)."""
    import time

    from gi.repository import GLib

    context, deadline = GLib.MainContext.default(), time.monotonic() + seconds
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _fake_analysis(monkeypatch, tmp_path):
    """stickler.api without models: three steps, then a result in 4/4 at 109."""
    from pathlib import Path

    from stickler import api

    seen = []

    def notate(song, out, *, progress, **kw):
        for i, step_id in enumerate(("transcribe", "beats", "engrave"), 1):
            for state in ("started", "done"):
                step = api.Step(step_id, i, 3, state, False, None)
                seen.append(step)
                progress(step)
        t = api.SongTranscription(song, "fast", None, [], [], [])
        return api.Notation(Path(out), None, None, t, [], 109, (4, 4))

    monkeypatch.setattr(
        api, "song_info", lambda p: api.SongInfo("Eye of the Tiger", "Survivor", 246.0)
    )
    monkeypatch.setattr(api, "notate", notate)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return seen


def test_opening_a_song_shows_the_steps_and_ends_on_the_result(monkeypatch, tmp_path):
    from stickler_gtk.ui.window import Window

    seen = _fake_analysis(monkeypatch, tmp_path)
    window = Window()
    window.open_song(tmp_path / "eye.flac")
    assert window.pages.get_visible_child_name() == "analysing"
    assert _wait(lambda: window.pages.get_visible_child_name() == "result")
    assert len(seen) == 6
    assert window.heading.get_title() == "Eye of the Tiger"
    assert window.heading.get_subtitle() == "Survivor · ♩ = 109 · 4/4"


def test_a_failed_analysis_shows_the_error_page_and_can_try_again(monkeypatch, tmp_path):
    from stickler import api
    from stickler_gtk.ui.window import Window

    attempts = []

    def broken(song, out, **kw):
        attempts.append(song)
        raise RuntimeError("adtof (exit 1): out of memory")

    monkeypatch.setattr(api, "song_info", lambda p: api.SongInfo("x", "", 1.0))
    monkeypatch.setattr(api, "notate", broken)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    window = Window()
    window.open_song(tmp_path / "x.flac")
    assert _wait(lambda: window.pages.get_visible_child_name() == "error")
    assert window.error_details.get_label() == "adtof (exit 1): out of memory"
    assert window.retry_button.get_visible()
    window.activate_action("win.retry", None)
    assert _wait(lambda: len(attempts) == 2)


def test_a_missing_model_shows_the_setup_commands(monkeypatch, tmp_path):
    from stickler import api
    from stickler_gtk.ui.window import Window

    def missing(song, out, **kw):
        raise api.SetupMissing(["adtof"])

    monkeypatch.setattr(api, "song_info", lambda p: api.SongInfo("x", "", 1.0))
    monkeypatch.setattr(api, "notate", missing)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    window = Window()
    window.open_song(tmp_path / "x.flac")
    assert _wait(lambda: window.pages.get_visible_child_name() == "error")
    assert window.error_details.get_label() == "stickler setup --adapter adtof"
    assert window.error_expander.get_expanded() and not window.retry_button.get_visible()


def test_cancel_returns_at_once_and_stops_the_job(monkeypatch, tmp_path):
    import time

    from stickler import api
    from stickler_gtk.ui.window import Window

    stopped = []

    def slow(song, out, *, cancel, **kw):
        cancel.wait(10)  # a model running until the token is set
        stopped.append(cancel.is_set())
        raise api.Cancelled("cancelled")

    monkeypatch.setattr(api, "song_info", lambda p: api.SongInfo("x", "", 1.0))
    monkeypatch.setattr(api, "notate", slow)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    window = Window()
    window.open_song(tmp_path / "x.flac")
    assert window.pages.get_visible_child_name() == "analysing"
    start = time.monotonic()
    window.activate_action("win.cancel", None)
    assert window.pages.get_visible_child_name() == "empty"
    assert _wait(lambda: stopped == [True], seconds=1)
    assert time.monotonic() - start < 1
    assert not window.actions["cancel"].get_enabled()


def test_recent_songs_open_or_can_be_removed(monkeypatch, tmp_path):
    import os
    from datetime import date
    from pathlib import Path

    from stickler_gtk.logic import recent
    from stickler_gtk.ui.window import Window

    there = tmp_path / "there.flac"
    there.write_bytes(b"x")
    store = recent.store_path()
    recent.save(
        store,
        [
            recent.Recent(there, "There", "Band", date.today()),
            recent.Recent(tmp_path / "gone.flac", "Gone", "", date.today()),
        ],
    )
    seen = _fake_analysis(monkeypatch, tmp_path)
    window = Window()
    assert [r.get_title() for r in window.recent_rows] == ["There", "Gone"]
    (remove,) = _find(window.recent_rows[1], lambda w: "flat" in w.get_css_classes())
    remove.emit("clicked")
    assert [s.title for s in recent.load(store)] == ["There"]
    window.recent_rows[0].emit("activated")
    assert _wait(lambda: window.pages.get_visible_child_name() == "result")
    assert seen and os.path.samefile(recent.load(store)[0].path, there)
    assert recent.load(store)[0].title == "Eye of the Tiger"  # the analysis's own title
    assert Path(store).parent.is_relative_to(tmp_path)


def test_the_drum_track_export_runs_with_steps_and_returns_to_the_result(monkeypatch, tmp_path):
    from stickler import api
    from stickler_gtk.ui.window import Window

    _fake_analysis(monkeypatch, tmp_path)
    stem = tmp_path / "stem.wav"
    stem.write_bytes(b"RIFF")

    def transcribe(song, *, drums, progress, cancel):
        progress(api.Step("separate", 1, 1, "started", False, "demucs"))
        progress(api.Step("separate", 1, 1, "done", False, "demucs"))
        return api.SongTranscription(song, "fast", stem, [], [], [])

    monkeypatch.setattr(api, "transcribe_song", transcribe)
    monkeypatch.setattr(api, "export_drum_track", lambda s, d: d.write_bytes(s.read_bytes()) or d)
    window = Window()
    assert not window.export_button.get_visible()
    window.open_song(tmp_path / "eye.flac")
    assert _wait(lambda: window.pages.get_visible_child_name() == "result")
    assert window.export_button.get_visible()
    dest = tmp_path / "out" / "Eye of the Tiger (drums).flac"
    dest.parent.mkdir()
    window._start_drums(window.state, dest, setup=False)
    assert window.pages.get_visible_child_name() == "analysing"
    assert window.analysing.get_title() == "Saving the Drum Track"
    assert _wait(lambda: window.pages.get_visible_child_name() == "result")
    assert dest.read_bytes() == b"RIFF"


def test_the_appearance_switch_applies_and_remembers_the_choice():
    from gi.repository import Adw, Gtk

    from stickler_gtk.logic import settings
    from stickler_gtk.ui import menu
    from stickler_gtk.ui.window import Window

    window = Window()
    (button,) = _find(window, lambda w: isinstance(w, Gtk.MenuButton) and w.get_primary())
    (dark,) = _find(button.get_popover(), lambda w: "dark" in w.get_css_classes())
    dark.set_active(True)
    assert settings.load(settings.store_path()).appearance == "dark"
    assert Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_DARK
    menu.choose_appearance("system")
    assert Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT


def test_the_shortcuts_dialog_lists_every_shortcut_and_about_names_the_version():
    import stickler
    from stickler_gtk.ui import menu

    assert len(menu.SHORTCUTS) == 7
    assert {key for key, _title in menu.SHORTCUTS} >= {"<Control>o", "<Control>q", "F10"}
    assert menu.shortcuts_dialog() is not None
    assert menu.about_dialog().get_version() == stickler.__version__
