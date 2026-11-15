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


def _groove_score():
    """Eight bars of a plain groove, engraved like the app's own results."""
    from stickler import notation

    beats = [k * 0.5 for k in range(33)]
    notes = [(b * 2.0 + k * 0.5, 36 + (b % 2) * 2, 100) for b in range(8) for k in range(4)]
    return notation.engrave(notes, beats, beats[:-1:4], repeats=False)


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
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        engraved = _groove_score()
        Path(out).write_text(engraved.musicxml, encoding="utf-8")
        t = api.SongTranscription(song, "fast", None, [], [], [])
        return api.Notation(Path(out), None, None, t, engraved.bars, 109, (4, 4))

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
    assert not window.export_box.get_visible()
    window.open_song(tmp_path / "eye.flac")
    assert _wait(lambda: window.pages.get_visible_child_name() == "result")
    assert window.export_box.get_visible()
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

    assert len(menu.SHORTCUTS) == 10
    assert {key for key, _title in menu.SHORTCUTS} >= {"<Control>o", "<Control>q", "F10"}
    assert menu.shortcuts_dialog() is not None
    assert menu.about_dialog().get_version() == stickler.__version__


def test_a_narrow_window_keeps_icon_buttons_in_the_header():
    from stickler_gtk.ui.window import Window

    window = Window()
    assert window.get_size_request() == (360, 294)
    assert window.open_wide.get_visible() and not window.open_narrow.get_visible()
    window.set_default_size(400, 700)
    window.present()
    try:
        assert _wait(lambda: window.open_narrow.get_visible())
        assert not window.open_wide.get_visible()
        assert window.export_narrow.get_icon_name() == "document-save-symbolic"
    finally:
        window.close()


@pytest.mark.parametrize("language", ["en", "de"])
def test_every_page_fits_the_narrowest_window(monkeypatch, language):
    """No page needs more than the minimum width, so nothing scrolls sideways (SPEC
    app-shell, criterion 7); German texts are longer, so both languages are measured."""
    from gi.repository import Gtk

    from stickler_gtk import i18n
    from stickler_gtk.ui.window import MINIMUM_SIZE, Window

    monkeypatch.setenv("LANGUAGE", language)
    i18n.setup()
    try:
        window = Window()
        widths = {}
        for name in ("empty", "analysing", "result", "error"):
            page = window.pages.get_child_by_name(name)
            widths[name] = page.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
    finally:
        monkeypatch.setenv("LANGUAGE", "en")
        i18n.setup()
    assert all(w <= MINIMUM_SIZE[0] for w in widths.values()), widths


def test_the_app_environment_finds_the_leipzig_font():
    """scripts/gtk.sh points fontconfig at the app's font folder (librsvg's only way in)."""
    import subprocess

    families = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    assert "Leipzig" in families


def test_the_about_dialog_names_what_the_app_ships_from_others():
    from stickler_gtk.ui import menu

    assert [title for title, *_rest in menu.LEGAL] == ["Verovio", "Leipzig"]
    assert menu.about_dialog() is not None


def test_the_result_page_shows_the_sheet_as_wide_as_the_window_and_zooms(monkeypatch, tmp_path):
    from stickler_gtk.ui.sheet import GUTTER
    from stickler_gtk.ui.window import Window

    _fake_analysis(monkeypatch, tmp_path)
    window = Window()
    window.set_default_size(900, 700)
    window.present()
    try:
        window.open_song(tmp_path / "eye.flac")
        assert _wait(lambda: window.pages.get_visible_child_name() == "result")
        assert _wait(lambda: bool(window.sheet.views))
        page = window.sheet.pages[0]
        assert abs(page.width - (window.sheet.get_width() - 2 * GUTTER)) <= 1
        assert len(page.bars) == 8
        normal = page.bars[1].height
        window.activate_action("win.zoom-in", None)
        assert window.sheet.pages[0].bars[1].height > normal
        window.activate_action("win.zoom-reset", None)
        assert abs(window.sheet.pages[0].bars[1].height - normal) < 0.5
    finally:
        window.close()


def _result_window(monkeypatch, tmp_path, width=900, height=700):
    from stickler_gtk.ui.window import Window

    _fake_analysis(monkeypatch, tmp_path)
    window = Window()
    window.set_default_size(width, height)
    window.present()
    window.open_song(tmp_path / "eye.flac")
    assert _wait(lambda: bool(window.sheet.views))
    return window


def test_a_click_marks_the_bar_under_it_and_the_mark_survives_a_zoom(monkeypatch, tmp_path):
    window = _result_window(monkeypatch, tmp_path)
    try:
        box = window.sheet.pages[0].bars[3]
        window.sheet.mark_at(0, box.x + box.width / 2, box.y + box.height / 2)
        assert window.sheet.marked == 3
        window.sheet.mark_at(0, -5, -5)  # beside every bar: the mark stays
        assert window.sheet.marked == 3
        window.activate_action("win.zoom-in", None)
        assert window.sheet.marked == 3 and window.sheet.marked_box() is not None
    finally:
        window.close()


def test_a_time_marks_its_bar_and_scrolls_it_into_view(monkeypatch, tmp_path):
    window = _result_window(monkeypatch, tmp_path, width=360, height=400)
    try:
        assert _wait(lambda: window.sheet.get_vadjustment().get_upper() > 600)
        window.show_position(15.0)  # bar 8, far below at 360 px
        assert window.sheet.marked == 8
        adjustment = window.sheet.get_vadjustment()
        assert adjustment.get_value() > 0
        window.show_position(0.5)
        assert window.sheet.marked == 1 and adjustment.get_value() == 0
        window.show_position(99.0)  # after the song: nothing sounds, nothing marked
        assert window.sheet.marked is None
    finally:
        window.close()


def test_the_pdf_has_one_a4_page_per_print_page(tmp_path):
    """Read back with Poppler (cairo compresses the page objects, so no text search)."""
    import gi

    gi.require_version("Poppler", "0.18")
    from gi.repository import Poppler

    from stickler_gtk.logic import engraving
    from stickler_gtk.ui import pdf

    pages = engraving.a4_pages(_groove_score().musicxml)
    out = pdf.write_pdf(pages, tmp_path / "groove.pdf", title="Groove")
    document = Poppler.Document.new_from_file(out.as_uri(), None)
    assert document.get_n_pages() == len(pages)
    assert document.get_title() == "Groove"
    width, height = document.get_page(0).get_size()
    assert (round(width), round(height)) == (595, 842)


def test_the_window_can_be_made_narrow_while_the_sheet_is_shown(monkeypatch, tmp_path):
    """The pages must not set the window's minimum width, or it cannot shrink and Verovio
    never lays the song out for the narrower width (found by the owner, 2026-11-15)."""
    from gi.repository import Gtk

    from stickler_gtk.ui.window import MINIMUM_SIZE

    window = _result_window(monkeypatch, tmp_path, width=1000)
    try:
        assert window.sheet.pages[0].width > 900
        assert window.sheet.measure(Gtk.Orientation.HORIZONTAL, -1)[0] <= MINIMUM_SIZE[0]
        # the labelled header buttons need a little more, but less than the width at which
        # the narrow layout swaps them for icons (NARROW, 550sp)
        assert window.get_content().measure(Gtk.Orientation.HORIZONTAL, -1)[0] < 550
    finally:
        window.close()
