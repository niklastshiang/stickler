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
    corrected = _fake_analysis.corrected = []

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
        fix = kw.get("corrections") or api.Corrections()
        corrected.append(fix)
        tempo = {"half": 54, "normal": 109, "double": 218}[fix.tempo]
        return api.Notation(Path(out), None, None, t, engraved.bars, tempo, (4, 4))

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


def test_a_song_without_models_asks_for_them_and_opens_once_they_are_there(monkeypatch, tmp_path):
    from stickler import api
    from stickler_gtk.ui.window import Window

    _fake_analysis(monkeypatch, tmp_path)
    analysed = api.notate
    done = _fake_setup(monkeypatch, missing=("adtof",))

    def notate(song, out, **kw):
        if "adtof" not in done:
            raise api.SetupMissing(["adtof"])
        return analysed(song, out, **kw)

    monkeypatch.setattr(api, "notate", notate)
    window = Window()
    try:
        assert _wait(lambda: window.pages.get_visible_child_name() == "consent")
        window.activate_action("win.setup-later", None)  # Not Now
        window.open_song(tmp_path / "eye.flac")
        assert _wait(lambda: window.pages.get_visible_child_name() == "consent")
        assert window.state.song == tmp_path / "eye.flac"
        window.activate_action("win.setup-download", None)
        assert _wait(lambda: window.pages.get_visible_child_name() == "result")
        assert done == ["adtof"]
    finally:
        window.close()


def test_a_server_that_does_not_answer_is_named_and_the_download_can_be_retried(monkeypatch):
    from stickler import api
    from stickler_gtk.logic import settings
    from stickler_gtk.ui.window import Window

    settings.update(settings.store_path(), setup_agreed=True)
    done = _fake_setup(monkeypatch, missing=("beat_this",))
    working = api.setup_adapters
    attempts = []

    def flaky(adapter, device="cpu", adapters_root=None, *, progress, cancel):
        attempts.append(adapter)
        if len(attempts) == 1:
            progress(api.Step("environment:beat_this", 1, 2, "started", False, None))
            progress(api.Step("environment:beat_this", 1, 2, "done", False, None))
            progress(api.Step("weights:beat_this", 2, 2, "started", False, None))
            raise RuntimeError("Beat This! model not downloaded. JKU Linz: 500")
        return working(adapter, device, adapters_root, progress=progress, cancel=cancel)

    monkeypatch.setattr(api, "setup_adapters", flaky)
    window = Window()
    try:
        assert _wait(lambda: window.pages.get_visible_child_name() == "setup-error")
        labels = _labels(window.pages.get_child_by_name("setup-error"))
        assert "A Download Server Is Not Answering" in labels
        assert any("cloud.cp.jku.at" in text for text in labels)
        assert "Try Again" in labels and "Later" in labels
        window.activate_action("win.setup-retry", None)
        assert _wait(lambda: window.pages.get_visible_child_name() == "empty")
        assert done == ["beat_this"] and len(attempts) == 2
    finally:
        window.close()


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

    def transcribe(song, *, drums, progress, cancel, adapters_root, cache_dir):
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
    from stickler_gtk.ui.application import ACCELS

    assert len(menu.SHORTCUTS) == 15
    keys = {key for key, _title in menu.SHORTCUTS}
    assert keys >= {"<Control>o", "<Control>q", "F10", "space", "Left", "Right", "Home", "F9"}
    assert all(any(key in accels for accels in ACCELS.values()) for key in keys - {"F10"})
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


@pytest.mark.parametrize("language", ["en", "de", "es"])
def test_every_page_fits_the_narrowest_window(monkeypatch, language):
    """No page needs more than the minimum width, so nothing scrolls sideways (SPEC
    app-shell, criterion 7); German texts are longer, so both languages are measured. The
    playback bar's one-row layout must fit where the narrow breakpoint (550 sp) ends."""
    from gi.repository import Gtk

    from stickler_gtk import i18n
    from stickler_gtk.logic import session, steps
    from stickler_gtk.ui.window import MINIMUM_SIZE, Window

    monkeypatch.setenv("LANGUAGE", language)
    i18n.setup()
    try:
        window = Window()
        wide = window.pages.get_child_by_name("result").measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        window.playbar.set_narrow(True)  # as the breakpoint does below 550 sp
        widths = {}
        for name in ("empty", "analysing", "result", "error"):
            page = window.pages.get_child_by_name(name)
            widths[name] = page.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        window.show(session.consent(("adtof", "beat_this")))
        failed_steps = steps.planned(("environment:beat_this", "weights:beat_this"))
        window.show(session.SetupFailed(failed_steps, "weights:beat_this", "HTTP 500", ()))
        for name in ("consent", "setup-error"):
            page = window.pages.get_child_by_name(name)
            widths[name] = page.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
    finally:
        monkeypatch.setenv("LANGUAGE", "en")
        i18n.setup()
    assert all(w <= MINIMUM_SIZE[0] for w in widths.values()), widths
    assert wide <= 550, wide


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


def test_a_pinch_zooms_once_the_fingers_pause(monkeypatch, tmp_path):
    window = _result_window(monkeypatch, tmp_path)
    try:
        normal = window.sheet.pages[0].bars[1].height
        window.sheet._pinch_from = window.sheet.zoom
        window.sheet.pinch(1.6)
        assert window.sheet.zoom == 1.6
        assert _wait(lambda: window.sheet.pages[0].bars[1].height > normal * 1.4)
    finally:
        window.close()


def test_the_note_size_is_shown_in_the_menu_and_kept_for_the_next_song():
    from stickler_gtk.logic import settings
    from stickler_gtk.ui.window import Window

    window = Window()
    assert window.zoom_label.get_label() == "100%"
    window.activate_action("win.zoom-in", None)  # works before any song, too
    assert window.zoom_label.get_label() == "125%"
    assert settings.load(settings.store_path()).zoom == 1.25
    assert Window().sheet.zoom == 1.25  # the next window starts at the chosen size
    window.activate_action("win.zoom-reset", None)
    assert settings.load(settings.store_path()).zoom == 1.0


def test_a_pinch_scales_the_drawn_pages_at_once_and_lays_them_out_after(monkeypatch, tmp_path):
    """Smooth zoom (owner, 2026-11-15: the pinch was not smooth): during the gesture the drawn
    page is scaled at once; Verovio lays it out anew once the fingers pause."""
    window = _result_window(monkeypatch, tmp_path)
    try:
        view = window.sheet.views[0]
        width = view.get_content_width()
        window.sheet._pinch_from = window.sheet.zoom
        window.sheet.pinch(1.5)
        assert window.sheet.views[0] is view  # same page, not laid out yet
        assert view.get_content_width() == round(width * 1.5)
        assert _wait(lambda: window.sheet.views[0] is not view)  # laid out anew
        assert abs(window.sheet.views[0].get_content_width() - width) <= 2  # as wide again
    finally:
        window.close()


def test_the_app_finds_its_own_icon():
    from gi.repository import Gdk, Gtk

    from stickler_gtk import APP_ID
    from stickler_gtk.ui import application

    application.register_icons()
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    assert theme.has_icon(APP_ID) and theme.has_icon(f"{APP_ID}-symbolic")


class _FakePlayer:
    """ui.player.Player's interface, without sound."""

    made: list = []

    def __init__(self, **kw):
        self.on_end, self.loaded, self.at, self.is_playing = kw.get("on_end"), None, 0.0, False
        _FakePlayer.made.append(self)

    def load(self, song, clicks):
        self.loaded, self.at = (song, clicks), 0.0

    def play(self):
        self.is_playing = True

    def pause(self):
        self.is_playing = False

    def seek(self, seconds):
        self.at = seconds

    def position(self):
        return self.at

    def playing(self):
        return self.is_playing

    def set_volumes(self, song, clicks):
        self.volumes = (song, clicks)

    def stop(self):
        self.loaded, self.is_playing = None, False


def _playing_window(monkeypatch, tmp_path):
    from stickler_gtk.ui import playbar

    _FakePlayer.made = []
    monkeypatch.setattr(playbar, "Player", _FakePlayer)
    return _result_window(monkeypatch, tmp_path)


def test_the_playback_bar_plays_follows_and_seeks(monkeypatch, tmp_path):
    from gi.repository import Gtk

    window = _playing_window(monkeypatch, tmp_path)
    try:
        bar = window.playbar
        assert bar.length.get_label() == "4:06" and bar.time.get_label() == "0:00"
        assert bar.bar.get_label() == "Bar 1 of 8"
        window.activate_action("win.play", None)
        player = _FakePlayer.made[-1]
        assert player.is_playing and player.loaded[0] == tmp_path / "eye.flac"
        assert bar.play.get_icon_name() == "media-playback-pause-symbolic"
        player.at = 5.0
        assert _wait(lambda: bar.time.get_label() == "0:05")
        assert bar.bar.get_label() == "Bar 3 of 8" and window.sheet.marked == 3
        bar.position.emit("change-value", Gtk.ScrollType.JUMP, 10.0)
        assert player.at == 10.0
        window.activate_action("win.play", None)
        assert not player.is_playing
        assert bar.play.get_icon_name() == "media-playback-start-symbolic"
    finally:
        window.close()


def test_at_the_end_playback_stops_and_starts_again_from_the_top(monkeypatch, tmp_path):
    window = _playing_window(monkeypatch, tmp_path)
    try:
        window.activate_action("win.play", None)
        player = _FakePlayer.made[-1]
        player.at = 16.0
        player.on_end()
        assert window.playbar.play.get_icon_name() == "media-playback-start-symbolic"
        window.activate_action("win.play", None)
        assert player.is_playing and player.at == 0.0
    finally:
        window.close()


def test_what_to_hear_and_the_volumes_reach_the_player_and_are_remembered(monkeypatch, tmp_path):
    from stickler_gtk.logic import settings

    window = _playing_window(monkeypatch, tmp_path)
    try:
        bar = window.playbar
        window.activate_action("win.play", None)
        player = _FakePlayer.made[-1]
        assert player.volumes == (0.7, 1.0)  # both; the song a little down, so clicks stand out
        bar.song_volume.set_value(0.6)
        bar.hits_volume.set_value(0.3)
        assert player.volumes == (0.6, 0.3)
        bar.hear.set_active_name("song")
        assert player.volumes == (0.6, 0.0)
        bar.hear.set_active_name("hits")
        assert player.volumes == (0.0, 0.3)
        stored = settings.load(settings.store_path())
        assert (stored.song_volume, stored.hits_volume) == (0.6, 0.3)
    finally:
        window.close()


def test_a_click_on_a_bar_jumps_there(monkeypatch, tmp_path):
    window = _playing_window(monkeypatch, tmp_path)
    try:
        window.activate_action("win.play", None)
        player = _FakePlayer.made[-1]
        box = window.sheet.pages[0].bars[3]
        window.sheet.mark_at(0, box.x + box.width / 2, box.y + box.height / 2)
        assert player.at == 4.0  # bar 3 starts at 4 s
        assert window.playbar.time.get_label() == "0:04" and window.sheet.marked == 3
    finally:
        window.close()


def test_a_narrow_window_shows_the_playback_bar_in_two_rows(monkeypatch, tmp_path):
    from gi.repository import Gtk

    window = _playing_window(monkeypatch, tmp_path)
    window.set_default_size(400, 700)
    try:
        bar = window.playbar
        assert _wait(lambda: bar.narrow)
        assert bar.get_orientation() == Gtk.Orientation.VERTICAL and not bar.bar.get_visible()
        window.set_default_size(900, 700)
        assert _wait(lambda: not bar.narrow) and bar.bar.get_visible()
    finally:
        window.close()


def test_the_keys_play_and_move_bar_by_bar(monkeypatch, tmp_path):
    window = _playing_window(monkeypatch, tmp_path)
    try:
        bar = window.playbar
        window.activate_action("win.next-bar", None)
        window.activate_action("win.next-bar", None)
        assert bar.time.get_label() == "0:04" and window.sheet.marked == 3
        window.activate_action("win.previous-bar", None)
        assert bar.time.get_label() == "0:02"
        window.activate_action("win.play", None)
        player = _FakePlayer.made[-1]
        assert player.at == 2.0  # playing starts where the keys went
        window.activate_action("win.next-bar", None)
        assert player.at == 4.0
        window.activate_action("win.to-start", None)
        assert player.at == 0.0 and player.is_playing
    finally:
        window.close()


def test_playback_stops_for_another_song_and_on_close(monkeypatch, tmp_path):
    window = _playing_window(monkeypatch, tmp_path)
    window.activate_action("win.play", None)
    player = _FakePlayer.made[-1]
    window.open_song(tmp_path / "other.flac")
    assert player.loaded is None and not player.is_playing
    assert _wait(lambda: window.pages.get_visible_child_name() == "result")
    window.activate_action("win.play", None)
    assert player.is_playing
    window.close()
    assert player.loaded is None and not player.is_playing


def test_the_corrections_panel_shows_values_and_reports_each_change():
    from stickler import api
    from stickler_gtk.ui.corrections import CorrectionsPanel

    changes = []
    panel = CorrectionsPanel(on_change=changes.append)
    panel.show_values(api.Corrections(), beats_per_bar=4, first_one=1)
    assert panel.tempo.get_active_name() == "normal" and changes == []
    assert panel.beats.get_value() == 4 and panel.first_one.get_label() == "Beat 1"
    assert panel.simplify.get_active() and panel.repeats.get_active()
    assert not panel.back.get_sensitive()
    panel.beats.set_value(3)
    assert changes[-1] == api.Corrections(beats_per_bar=3)
    panel.later.emit("clicked")
    assert changes[-1].first_downbeat == 2
    panel.tempo.set_active_name("half")
    assert changes[-1].tempo == "half"
    panel.simplify.set_active(False)
    assert changes[-1].simplify is False
    panel.show_values(changes[-1], beats_per_bar=3, first_one=1)
    assert panel.back.get_sensitive()
    count = len(changes)
    panel.back.emit("clicked")
    assert changes[-1] == api.Corrections() and len(changes) == count + 1


def test_f9_opens_and_closes_the_corrections_sidebar(monkeypatch, tmp_path):
    window = _playing_window(monkeypatch, tmp_path)
    try:
        assert not window.split.get_show_sidebar() and window.corrections_button.get_visible()
        window.activate_action("win.corrections", None)
        assert window.split.get_show_sidebar() and window.corrections_button.get_active()
        assert window.panel.beats.get_value() == 4
        window.activate_action("win.corrections", None)
        assert not window.split.get_show_sidebar()
    finally:
        window.close()


def test_a_correction_applies_at_once_is_remembered_and_can_be_taken_back(monkeypatch, tmp_path):
    from stickler import api
    from stickler_gtk.logic import corrections

    window = _playing_window(monkeypatch, tmp_path)
    song = tmp_path / "eye.flac"
    try:
        window.activate_action("win.play", None)
        player = _FakePlayer.made[-1]
        window.panel.tempo.set_active_name("half")
        assert _wait(lambda: "♩ = 54" in window.heading.get_subtitle())
        assert _fake_analysis.corrected[-1] == api.Corrections(tempo="half")
        assert player.is_playing and player.loaded is not None  # the music goes on
        assert window.state.corrections == api.Corrections(tempo="half")
        stored = corrections.load(corrections.store_path())
        assert stored == {song: api.Corrections(tempo="half")}
        assert window.panel.back.get_sensitive()

        window.open_song(song)  # opened again: with its corrections
        assert _wait(lambda: window.pages.get_visible_child_name() == "result")
        assert _fake_analysis.corrected[-1] == api.Corrections(tempo="half")
        assert "♩ = 54" in window.heading.get_subtitle()

        window.panel.back.emit("clicked")
        assert _wait(lambda: "♩ = 109" in window.heading.get_subtitle())
        assert corrections.load(corrections.store_path()) == {}
        assert not window.panel.back.get_sensitive()
    finally:
        window.close()


def test_quick_changes_make_one_run(monkeypatch, tmp_path):
    from stickler import api

    window = _playing_window(monkeypatch, tmp_path)
    try:
        runs = len(_fake_analysis.corrected)
        for beats in (3, 5, 6):
            window.panel.beats.set_value(beats)
        assert _wait(lambda: window.state.pending is None and len(_fake_analysis.corrected) > runs)
        assert _fake_analysis.corrected[runs:] == [api.Corrections(beats_per_bar=6)]
    finally:
        window.close()


def test_a_narrow_window_shows_the_corrections_in_a_bottom_sheet(monkeypatch, tmp_path):
    window = _playing_window(monkeypatch, tmp_path)
    try:
        window.activate_action("win.corrections", None)  # open in the wide window
        window.set_default_size(400, 700)
        assert _wait(lambda: window.playbar.narrow)
        assert window.bottom_sheet.get_open() and not window.split.get_show_sidebar()
        assert window.panel.get_parent().get_parent() is window.sheet_scroller
        window.activate_action("win.corrections", None)
        assert not window.bottom_sheet.get_open() and not window.corrections_button.get_active()
        window.corrections_button.set_active(True)
        assert window.bottom_sheet.get_open()
        window.set_default_size(1000, 700)
        assert _wait(lambda: not window.playbar.narrow)
        assert window.split.get_show_sidebar() and not window.bottom_sheet.get_open()
        assert window.panel.get_parent().get_parent() is window.sidebar_scroller
    finally:
        window.close()


def _fake_setup(monkeypatch, missing=("adtof", "beat_this"), block=None):
    """api without downloads: `missing` are not set up; setup_adapters reports its steps."""
    from stickler import api

    done = []
    monkeypatch.setattr(api, "mode_ready", lambda *a, **kw: [m for m in missing if m not in done])

    def setup_adapters(adapter, device="cpu", adapters_root=None, *, progress, cancel):
        ids = [f"environment:{adapter}"] + (["weights:beat_this"] if adapter == "beat_this" else [])
        for i, step_id in enumerate(ids, 1):
            progress(api.Step(step_id, i, len(ids), "started", False, None))
            if block is not None:
                while not cancel.is_set():
                    block.wait(0.01)
                raise api.Cancelled()
            progress(api.Step(step_id, i, len(ids), "done", False, None))
        done.append(adapter)
        return [adapter]

    monkeypatch.setattr(api, "setup_adapters", setup_adapters)
    return done


def test_the_first_start_asks_then_downloads_then_shows_the_empty_window(monkeypatch):
    from stickler_gtk.logic import settings, setup
    from stickler_gtk.ui.window import Window

    done = _fake_setup(monkeypatch)
    window = Window()
    try:
        assert _wait(lambda: window.pages.get_visible_child_name() == "consent")
        labels = _labels(window.pages.get_child_by_name("consent"))
        size = setup.total_size(["adtof", "beat_this"])  # "2.2 GB", "2,2 GB" by the locale
        assert f"Download {size}" in labels and "Not Now" in labels
        window.activate_action("win.setup-download", None)
        assert _wait(lambda: window.pages.get_visible_child_name() == "empty")
        assert done == ["adtof", "beat_this"]
        assert settings.load(settings.store_path()).setup_agreed
    finally:
        window.close()


def test_not_now_shows_the_empty_window(monkeypatch):
    from stickler_gtk.ui.window import Window

    _fake_setup(monkeypatch)
    window = Window()
    try:
        assert _wait(lambda: window.pages.get_visible_child_name() == "consent")
        window.activate_action("win.setup-later", None)
        assert window.pages.get_visible_child_name() == "empty"
    finally:
        window.close()


def test_an_agreed_setup_goes_on_by_itself_and_can_be_cancelled(monkeypatch):
    import threading

    from stickler_gtk.logic import settings
    from stickler_gtk.ui.window import Window

    settings.update(settings.store_path(), setup_agreed=True)
    _fake_setup(monkeypatch, block=threading.Event())
    window = Window()
    try:
        assert _wait(lambda: window.pages.get_visible_child_name() == "analysing")
        assert window.analysing.get_title() == "Downloading the Models"
        assert _wait(lambda: window.state.steps[0].state == "running")
        window.activate_action("win.cancel", None)
        assert window.pages.get_visible_child_name() == "empty"
    finally:
        window.close()


def test_progress_updates_keep_the_running_steps_row_so_its_spinner_runs_on():
    """The owner saw the spinner stutter during the download: every report rebuilt the list."""
    from stickler import api
    from stickler_gtk.logic import session
    from stickler_gtk.ui.window import Window

    window = Window()
    try:
        state = session.start_setup(("environment:adtof", "weights:beat_this"), None, ("adtof",))
        step = api.Step("environment:adtof", 1, 2, "started", False, None)
        window.show(session.on_setup_step(state, state.job, step))
        row = window.steps.get_row_at_index(0)
        window.show(session.setup_grew(window.state, state.job, 650_000_000))
        assert window.steps.get_row_at_index(0) is row  # the same row, its spinner untouched
        assert "650 MB" in row.get_subtitle()
        done = api.Step("environment:adtof", 1, 2, "done", False, None)
        window.show(session.on_setup_step(window.state, state.job, done))
        assert window.steps.get_row_at_index(0) is not row  # done: a check mark instead
        assert window.steps.get_row_at_index(1) is not None
    finally:
        window.close()
