"""The main window (design screens 4 and 5, the result header of 6). It draws the state that
`stickler_gtk.logic.session` decides; analyses run in a worker thread."""

from __future__ import annotations

import contextlib
import threading
from dataclasses import replace
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from stickler import adapters, api
from stickler_gtk import APP_NAME
from stickler_gtk.i18n import _
from stickler_gtk.logic import (
    analysis,
    corrections,
    engraving,
    exports,
    paths,
    playback,
    recent,
    session,
    settings,
    setup,
    zoom,
)
from stickler_gtk.logic.steps import StepRow
from stickler_gtk.ui import corrections as corrections_ui
from stickler_gtk.ui import menu, pdf, worker
from stickler_gtk.ui import setup as setup_ui
from stickler_gtk.ui.playbar import PlayBar
from stickler_gtk.ui.sheet import Sheet

DEFAULT_SIZE = (1000, 700)
SAMPLE_MS = 500  # how often a download's progress is measured
CORRECT_AFTER_MS = 250  # a correction waits for the changes to pause
MINIMUM_SIZE = (360, 294)  # GNOME HIG: the smallest a window should get
NARROW = "max-width: 550sp"  # below this the header keeps icon buttons only


def _open_button(label: str) -> Gtk.Button:
    button = Gtk.Button(label=label, halign=Gtk.Align.CENTER, action_name="win.open")
    button.add_css_class("pill")
    button.add_css_class("suggested-action")
    return button


def _empty_page(recent_songs: Gtk.Widget) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=36)
    box.append(_open_button(_("Open a Song…")))
    box.append(Adw.Clamp(maximum_size=560, child=recent_songs))
    page = Adw.StatusPage(
        icon_name="audio-x-generic-symbolic",
        title=_("Drop a Song Here"),
        description=_(
            "Stickler listens to the drums and writes them as sheet music. "
            "MP3, FLAC, WAV or OGG; a song takes about 15 seconds."
        ),
        child=box,
    )
    page.add_css_class("drop-area")
    return page


def _children(widget: Gtk.Widget) -> list[Gtk.Widget]:
    found, child = [], widget.get_first_child()
    while child is not None:
        found.append(child)
        child = child.get_next_sibling()
    return found


def _step_row(step: StepRow) -> Adw.ActionRow:
    row = Adw.ActionRow(title=step.label, subtitle=step.detail)
    if step.state == "done":
        icon = Gtk.Image(icon_name="object-select-symbolic", tooltip_text=_("Done"))
        icon.add_css_class("success")
        row.add_prefix(icon)
    elif step.state == "running":
        row.add_prefix(Adw.Spinner())
        row.add_css_class("property")
    else:
        row.add_prefix(Gtk.Image(icon_name="content-loading-symbolic", opacity=0.4))
        row.add_suffix(Gtk.Label(label=_("Waiting"), css_classes=["dim-label"]))
    return row


class Window(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(title=APP_NAME, **kwargs)
        self.set_default_size(*DEFAULT_SIZE)
        self.set_size_request(*MINIMUM_SIZE)
        self.state: session.State = session.Empty()

        self.note_size = settings.load(settings.store_path()).zoom
        self.playbar = PlayBar(on_position=self.show_position)
        self.zoom_label = Gtk.Label(label=zoom.percent(self.note_size))
        self.heading = Adw.WindowTitle(title=APP_NAME)
        header = Adw.HeaderBar(title_widget=self.heading)
        # Wide windows show labelled buttons, narrow ones icon buttons (design screen 10)
        self.export_wide = Gtk.MenuButton(label=_("Export"), popover=self._export_menu())
        self.export_narrow = Gtk.MenuButton(
            icon_name="document-save-symbolic",
            popover=self._export_menu(),
            tooltip_text=_("Export"),
            visible=False,
        )
        self.export_box = Gtk.Box(visible=False)
        self.export_box.append(self.export_wide)
        self.export_box.append(self.export_narrow)
        header.pack_end(menu.main_menu(self.zoom_label))
        self.corrections_button = Gtk.ToggleButton(
            icon_name="sidebar-show-right-symbolic",
            tooltip_text=_("Corrections"),
            visible=False,
        )
        header.pack_end(self.corrections_button)
        header.pack_end(self.export_box)
        self.open_wide = Gtk.Button(
            child=Adw.ButtonContent(icon_name="document-open-symbolic", label=_("Open…")),
            action_name="win.open",
            tooltip_text=_("Open a Song"),
        )
        self.open_narrow = Gtk.Button(
            icon_name="document-open-symbolic",
            action_name="win.open",
            tooltip_text=_("Open a Song"),
            visible=False,
        )
        header.pack_start(self.open_wide)
        header.pack_start(self.open_narrow)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(NARROW))
        for wide_one, narrow_one in (
            (self.open_wide, self.open_narrow),
            (self.export_wide, self.export_narrow),
        ):
            narrow.add_setter(wide_one, "visible", False)
            narrow.add_setter(narrow_one, "visible", True)
        narrow.connect("apply", lambda _b: self._set_narrow(True))
        narrow.connect("unapply", lambda _b: self._set_narrow(False))
        self.add_breakpoint(narrow)

        self.steps = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        cancel_button = Gtk.Button(
            label=_("Cancel"), halign=Gtk.Align.CENTER, action_name="win.cancel"
        )
        cancel_button.add_css_class("pill")
        analysing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        analysing_box.append(Adw.Clamp(maximum_size=460, child=self.steps))
        analysing_box.append(cancel_button)
        self.analysing = Adw.StatusPage(title=_("Writing the Drum Part"), child=analysing_box)

        self.error_details = Gtk.Label(selectable=True, wrap=True, xalign=0)
        self.error_details.add_css_class("monospace")
        self.error_expander = Gtk.Expander(label=_("Technical Details"))
        self.error_expander.set_child(self.error_details)
        self.retry_button = Gtk.Button(label=_("Try Again"), action_name="win.retry")
        self.retry_button.add_css_class("pill")
        self.retry_button.add_css_class("suggested-action")
        other_button = Gtk.Button(label=_("Open Another Song…"), action_name="win.open")
        other_button.add_css_class("pill")
        # side by side, or one under the other in a narrow window
        buttons = Adw.WrapBox(child_spacing=12, line_spacing=12, align=0.5)
        buttons.append(other_button)
        buttons.append(self.retry_button)
        error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        error_box.append(Adw.Clamp(maximum_size=560, child=self.error_expander))
        error_box.append(buttons)
        self.error = Adw.StatusPage(icon_name="dialog-warning-symbolic", child=error_box)
        self.sheet = Sheet(self.note_size, on_zoom=self._zoom_changed)
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.recent_store = recent.store_path()
        self.recent = recent.load(self.recent_store)
        self.recent_group = Adw.PreferencesGroup(title=_("Recent"))
        self.recent_rows: list[Gtk.Widget] = []
        self._show_recent()
        self.pages.add_named(_empty_page(self.recent_group), "empty")
        self.pages.add_named(self.analysing, "analysing")
        self.playbar.on_error = lambda reason: self.toast(
            _("The song cannot be played: {reason}").format(reason=reason)
        )
        self.sheet.on_bar = self.jump_to_bar
        result_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        result_page.append(self.sheet)
        result_page.append(Gtk.Separator())
        result_page.append(self.playbar)
        self.panel = corrections_ui.CorrectionsPanel(on_change=self.change_corrections)
        # One set of controls: in the sidebar, or in a narrow window in a bottom sheet
        # (design screens 7 and 11); the header toggle and F9 open whichever is in use.
        self.sidebar_scroller = Gtk.ScrolledWindow(
            child=self.panel,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_width=True,
        )
        self.sheet_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True
        )
        self.bottom_sheet = Adw.BottomSheet(content=result_page, sheet=self.sheet_scroller)
        self.split = Adw.OverlaySplitView(
            content=self.bottom_sheet,
            sidebar=self.sidebar_scroller,
            sidebar_position=Gtk.PackType.END,
            show_sidebar=False,
            min_sidebar_width=corrections_ui.WIDTH,
            max_sidebar_width=corrections_ui.WIDTH,
        )
        self.corrections_narrow = False
        self.corrections_button.connect(
            "toggled", lambda b: self.set_corrections_open(b.get_active())
        )
        for widget, prop in ((self.split, "show-sidebar"), (self.bottom_sheet, "open")):
            widget.connect(f"notify::{prop}", lambda *_a: self._sync_corrections_button())
        self.pages.add_named(self.split, "result")
        self.pages.add_named(self.error, "error")
        self.consent = Adw.Bin()  # filled with the missing models (design screen 1)
        self.pages.add_named(self.consent, "consent")
        self.setup_error = Adw.Bin()  # design screen 3
        self.pages.add_named(self.setup_error, "setup-error")

        self.toasts = Adw.ToastOverlay(child=self.pages)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.pages.add_controller(drop)

        self.token: api.CancelToken | None = None
        self._shown: api.Notation | None = None  # the notation on the sheet
        self._shown_info: api.SongInfo | None = None  # a correction keeps it, a new analysis not
        self._correcting = 0  # the timer of a correction waiting for a quiet moment
        self.job_thread: threading.Thread | None = None
        self.actions: dict[str, Gio.SimpleAction] = {}
        for name, handler in (
            ("open", self.choose_song),
            ("cancel", self.cancel),
            ("retry", self.retry),
            ("export", self._open_export_menu),
            ("export-pdf", self.export_pdf),
            ("export-musicxml", self.export_musicxml),
            ("open-with", self.open_with),
            ("export-drums", self.export_drums),
            ("close", self.close),
            ("play", self.playbar.toggle),
            (
                "corrections",
                lambda: self.set_corrections_open(not self.corrections_open()),
            ),
            ("previous-bar", lambda: self.step_bars(-1)),
            ("next-bar", lambda: self.step_bars(1)),
            ("to-start", lambda: self.playbar.seek(0.0)),
            ("zoom-in", lambda: self.sheet.set_zoom(zoom.zoom_in(self.sheet.zoom))),
            ("zoom-out", lambda: self.sheet.set_zoom(zoom.zoom_out(self.sheet.zoom))),
            ("zoom-reset", lambda: self.sheet.set_zoom(1.0)),
            ("setup-download", self.agree_to_setup),
            ("setup-later", lambda: self.show(session.Empty())),
            ("setup-retry", self.retry_setup),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, run=handler: run())
            self.add_action(action)
            self.actions[name] = action
        self.connect("close-request", self._on_close)
        self._sampling = 0  # the timer that measures a download
        self._consent_for: tuple[str, ...] = ()
        self._free_before = 0
        self.show(self.state)
        self._check_setup()

    def _export_menu(self) -> Gtk.Popover:
        """Design screen 8: each export with a line on what it is for."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for action, title, detail in (
            ("win.export-pdf", _("Sheet Music (PDF)…"), _("To print or to read on a tablet")),
            (
                "win.export-musicxml",
                _("MusicXML…"),
                _("To edit in MuseScore or another notation program"),
            ),
            ("win.export-drums", _("Drum Track…"), _("As FLAC or WAV")),
            ("win.open-with", _("Open With…"), _("The MusicXML in another program")),
        ):
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.append(Gtk.Label(label=title, xalign=0))
            text.append(Gtk.Label(label=detail, xalign=0, css_classes=["caption", "dim-label"]))
            button = Gtk.Button(child=text, action_name=action, css_classes=["flat"])
            box.append(button)
        popover = Gtk.Popover(child=box)
        for button in _children(box):
            button.connect("clicked", lambda _b: popover.popdown())
        return popover

    def _open_export_menu(self) -> None:
        wide = self.export_wide.get_visible()
        (self.export_wide if wide else self.export_narrow).popup()

    # what the user does

    def choose_song(self) -> None:
        audio = Gtk.FileFilter(name=_("Songs"))
        audio.add_mime_type("audio/*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(audio)
        dialog = Gtk.FileDialog(title=_("Open a Song"), filters=filters, default_filter=audio)
        dialog.open(self, None, self._on_chosen)

    def _on_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            chosen = dialog.open_finish(result)
        except Exception:  # dismissed: GLib reports it as an error
            return
        if chosen is not None and chosen.get_path():
            self.open_song(Path(chosen.get_path()))

    def _on_drop(self, _target, files: Gdk.FileList, _x: float, _y: float) -> bool:
        dropped = [Path(f.get_path()) for f in files.get_files() if f.get_path()]
        songs = [p for p in dropped if paths.is_audio(p)]
        if not songs:
            self.toast(_("Not an audio file"))
            return False
        self.open_song(songs[0])
        return True

    def open_song(self, song: Path) -> None:
        self._start(session.open_song(song, self.state, self._stored(song)))

    def retry(self) -> None:
        if isinstance(self.state, session.Failed) and self.state.can_retry:
            song = self.state.song
            self._start(session.open_song(song, self.state.previous, self._stored(song)))

    @staticmethod
    def _stored(song: Path) -> api.Corrections:
        """The song's remembered corrections (SPEC.md, module `corrections`)."""
        stored = corrections.load(corrections.store_path())
        return stored.get(song.absolute(), corrections.DETECTED)

    def cancel(self) -> None:
        self._stop_job()
        self.show(session.cancel(self.state))

    def _stop_job(self) -> bool:
        if self.token is not None:
            self.token.cancel()  # the worker ends the model's processes within a second
            self.token = None
        return False  # let a closing window close

    def _on_close(self, _window) -> bool:
        self.playbar.stop()
        self.wait_for_job(2.0)  # a cancel takes well under a second
        return False  # close

    def _save_dialog(self, name: str, then) -> None:
        dialog = Gtk.FileDialog(title=_("Save As"), initial_name=name)

        def saved(dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                chosen = dialog.save_finish(result)
            except Exception:  # dismissed: GLib reports it as an error
                return
            if chosen is not None and chosen.get_path():
                then(Path(chosen.get_path()))

        dialog.save(self, None, saved)

    def _zoom_changed(self, value: float) -> None:
        """Every song is shown at the chosen note size; the menu shows it."""
        self.zoom_label.set_label(zoom.percent(value))
        # unsaved, the size still works for this session; a toast on every zoom step would nag
        with contextlib.suppress(OSError):
            settings.update(settings.store_path(), zoom=value)

    def show_position(self, seconds: float) -> None:
        """Marks the bar sounding at `seconds` (for `playback`, which follows the song)."""
        if isinstance(self.state, session.Result):
            self.sheet.mark_time(self.state.notation.bars, seconds)

    def _set_narrow(self, narrow: bool) -> None:
        self.playbar.set_narrow(narrow)
        if narrow == self.corrections_narrow:
            return
        was_open = self.corrections_open()
        self.split.set_show_sidebar(False)
        self.bottom_sheet.set_open(False)
        viewport = self.panel.get_parent()  # the scroller wraps the panel in a viewport
        viewport.set_child(None)
        (self.sidebar_scroller if narrow else self.sheet_scroller).set_child(None)
        self.corrections_narrow = narrow
        (self.sheet_scroller if narrow else self.sidebar_scroller).set_child(self.panel)
        self.set_corrections_open(was_open)

    def corrections_open(self) -> bool:
        if self.corrections_narrow:
            return self.bottom_sheet.get_open()
        return self.split.get_show_sidebar()

    def set_corrections_open(self, open_it: bool) -> None:
        if self.corrections_narrow:
            self.bottom_sheet.set_open(open_it)
        else:
            self.split.set_show_sidebar(open_it)
        self._sync_corrections_button()

    def _sync_corrections_button(self) -> None:
        if self.corrections_button.get_active() != self.corrections_open():
            self.corrections_button.set_active(self.corrections_open())

    def change_corrections(self, fix: api.Corrections) -> None:
        """A change in the sidebar: the controls show it at once, the sheet follows once the
        changes pause (a few quick clicks make one run)."""
        if not isinstance(self.state, session.Result):
            return
        self.state = session.correct(self.state, fix)
        if self._correcting:
            GLib.source_remove(self._correcting)
        self._correcting = GLib.timeout_add(CORRECT_AFTER_MS, self._start_correction)

    def _start_correction(self) -> bool:
        self._correcting = 0
        result = self.state
        if not isinstance(result, session.Result) or result.pending is None:
            return GLib.SOURCE_REMOVE
        job, fix, song = result.pending.job, result.pending.corrections, result.song
        self._stop_job()
        self.token = token = api.CancelToken()

        def done(finished: tuple[api.SongInfo, api.Notation]) -> None:
            state = session.corrected(self.state, job, finished[1])
            if state is not self.state:
                self.show(state)
                self._remember(song, fix)

        def failed(exc: BaseException) -> None:
            state = session.correction_failed(self.state, job)
            if state is not self.state:
                self.show(state)
                self.toast(_("The correction did not work: {reason}").format(reason=exc))

        self.job_thread = worker.run(
            lambda: analysis.analyse(
                song, paths.score_path(song), lambda _step: None, token, corrections=fix
            ),
            done,
            failed,
        )
        return GLib.SOURCE_REMOVE

    def _remember(self, song: Path, fix: api.Corrections) -> None:
        try:
            corrections.remember(corrections.store_path(), song.absolute(), fix)
        except OSError as exc:  # the correction still shows for this session
            self.toast(_("The correction could not be saved: {reason}").format(reason=exc.strerror))

    def step_bars(self, by: int) -> None:
        """Left and Right: one song bar back or on."""
        if isinstance(self.state, session.Result):
            bars = self.state.notation.bars
            self.playbar.seek(playback.step(bars, self.playbar.now(), by))

    def jump_to_bar(self, written: int) -> None:
        """A click on a bar: playback goes to its next pass (owner, 2026-11-15)."""
        if isinstance(self.state, session.Result):
            target = playback.jump_target(self.state.notation.bars, written, self.playbar.now())
            if target is not None:
                self.playbar.seek(target)

    def export_pdf(self) -> None:
        result = self.state
        if not isinstance(result, session.Result):
            return

        def save(dest: Path) -> None:
            try:
                xml = result.notation.musicxml.read_text(encoding="utf-8")
                pdf.write_pdf(engraving.a4_pages(xml), dest, title=result.title)
            except OSError as exc:
                self.toast(_("Could not save: {reason}").format(reason=exc.strerror))
                return
            self._saved(dest)

        self._save_dialog(exports.pdf_name(result.title), save)

    def open_with(self) -> None:
        """The system's app chooser for the MusicXML (OpenURI portal in the Flatpak)."""
        if isinstance(self.state, session.Result):
            musicxml = Gio.File.new_for_path(str(self.state.notation.musicxml))
            Gtk.FileLauncher(file=musicxml, always_ask=True).launch(self, None, None, None)

    def export_musicxml(self) -> None:
        result = self.state
        if not isinstance(result, session.Result):
            return

        def save(dest: Path) -> None:
            try:
                exports.save_musicxml(result.notation.musicxml, dest)
            except OSError as exc:
                self.toast(_("Could not save: {reason}").format(reason=exc.strerror))
                return
            self._saved(dest)

        self._save_dialog(exports.musicxml_name(result.title), save)

    def export_drums(self) -> None:
        result = self.state
        if not isinstance(result, session.Result):
            return
        setup = api.DRUM_TRACK_SEPARATOR in api.mode_ready(drums=True)
        cost = exports.drum_track_cost(result.info.seconds, download=setup)
        alert = Adw.AlertDialog(heading=_("Save the Drum Track?"), body=cost.text)
        alert.add_response("cancel", _("Cancel"))
        alert.add_response("save", _("Choose Where to Save…"))
        alert.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        alert.set_default_response("save")

        def answered(_alert, response: str) -> None:
            if response == "save":
                name = exports.drum_track_name(result.title)
                self._save_dialog(name, lambda dest: self._start_drums(result, dest, setup))

        alert.connect("response", answered)
        alert.present(self)

    def _start_drums(self, result: session.Result, dest: Path, setup: bool) -> None:
        self._stop_job()
        self.token = token = api.CancelToken()
        state = session.export_drums(result, dest, setup=setup)
        job = state.job
        self.show(state)
        report = worker.on_main_loop(lambda step: self.show(session.on_step(self.state, job, step)))

        def done(saved: Path) -> None:
            state = session.exported(self.state, job)
            if state is not self.state:
                self.show(state)
                self._saved(saved)

        self.job_thread = worker.run(
            lambda: exports.drum_track(result.song, dest, report, token, setup=setup),
            done,
            lambda exc: self.show(session.failed(self.state, job, exc)),
        )

    def _saved(self, dest: Path) -> None:
        toast = Adw.Toast(
            title=_("Saved “{name}”").format(name=dest.name), button_label=_("Open"), timeout=8
        )
        toast.connect(
            "button-clicked",
            lambda _t: Gtk.FileLauncher.new(Gio.File.new_for_path(str(dest))).launch(
                self, None, None, None
            ),
        )
        self.toasts.add_toast(toast)

    def _finished(self, job: int, info: api.SongInfo, notation: api.Notation) -> None:
        state = session.finished(self.state, job, info, notation)
        if isinstance(state, session.Result):
            entry = recent.opened_now(state.song, info.title, info.artist)
            self._set_recent(recent.add(self.recent, entry))
        self.show(state)

    def _set_recent(self, songs: list[recent.Recent]) -> None:
        self.recent = songs
        try:
            recent.save(self.recent_store, songs)
        except OSError as exc:  # the list still works for this session
            self.toast(_("Recent songs could not be saved: {reason}").format(reason=exc.strerror))
        self._show_recent()

    def _show_recent(self) -> None:
        for row in self.recent_rows:
            self.recent_group.remove(row)
        self.recent_rows = []
        for entry in recent.rows(self.recent):
            row = Adw.ActionRow(title=entry.title, subtitle=entry.detail)
            if entry.missing:
                row.add_css_class("dim-label")
                button = Gtk.Button(
                    icon_name="user-trash-symbolic",
                    tooltip_text=_("Remove from the List"),
                    valign=Gtk.Align.CENTER,
                    css_classes=["flat"],
                )
                button.connect(
                    "clicked",
                    lambda _b, path=entry.path: self._set_recent(recent.remove(self.recent, path)),
                )
                row.add_suffix(button)
            else:
                row.set_activatable(True)
                row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                row.connect("activated", lambda _r, path=entry.path: self.open_song(path))
            self.recent_group.add(row)
            self.recent_rows.append(row)
        self.recent_group.set_visible(bool(self.recent_rows))

    def wait_for_job(self, seconds: float) -> None:
        """Cancels the running job and waits until it has cleaned up (its half-written cache
        folder removed), so that quitting leaves nothing behind."""
        self._stop_job()
        if self.job_thread is not None:
            self.job_thread.join(seconds)

    def _start(self, state: session.Analysing) -> None:
        self._stop_job()
        self.token = token = api.CancelToken()
        job, song = state.job, state.song
        self.show(state)
        report = worker.on_main_loop(lambda step: self.show(session.on_step(self.state, job, step)))
        self.job_thread = worker.run(
            lambda: analysis.analyse(
                song,
                paths.score_path(song),
                report,
                token,
                paths.hits_path(song),
                state.corrections,
            ),
            lambda done: self._finished(job, *done),
            lambda exc: self.show(session.failed(self.state, job, exc)),
        )

    # what the window shows

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text))

    def _show_steps(self, rows) -> None:
        self.steps.remove_all()
        for step in rows:
            self.steps.append(_step_row(step))
        self.pages.set_visible_child_name("analysing")

    # the setup assistant (SPEC.md, module `setup-assistant`)

    def _check_setup(self) -> None:
        """At start, in the worker: are the models there? (a few uv checks, under 0.1 s)"""
        root = paths.adapters_root()

        def checked(missing: list[str]) -> None:
            if not isinstance(self.state, session.Empty):
                return  # the reader has started something meanwhile
            agreed = settings.load(settings.store_path()).setup_agreed
            page = setup.start_page(missing, agreed=agreed)
            if page == "consent":
                self.show(session.consent(tuple(missing)))
            elif page == "download":
                self._start_setup(tuple(missing), None)

        worker.run(
            lambda: api.mode_ready(adapters_root=root),
            checked,
            lambda exc: self.toast(_("Could not check the models: {reason}").format(reason=exc)),
        )

    def agree_to_setup(self) -> None:
        if not isinstance(self.state, session.Consent):
            return
        with contextlib.suppress(OSError):  # unsaved, the download still runs now
            settings.update(settings.store_path(), setup_agreed=True)
        self._start_setup(self.state.missing, self.state.song)

    def retry_setup(self) -> None:
        """Goes on from where it failed: steps already done are quick (api.setup_adapters)."""
        if isinstance(self.state, session.SetupFailed):
            self._start_setup(self.state.missing, self.state.song)

    def _start_setup(self, missing: tuple[str, ...], song: Path | None) -> None:
        root = paths.adapters_root()
        registry = adapters.discover(root)
        ids = setup.step_ids(list(missing), lambda a: adapters.needs_weights(registry[a]))
        self._stop_job()
        self.token = token = api.CancelToken()
        state = session.start_setup(ids, song, missing)
        job = state.job
        self.show(state)

        def step(reported: api.Step) -> None:
            if reported.state == "started":
                self._free_before = setup.free_space(root)
            self.show(session.on_setup_step(self.state, job, reported))

        def sample() -> bool:
            if not (isinstance(self.state, session.SettingUp) and self.state.job == job):
                self._sampling = 0
                return GLib.SOURCE_REMOVE
            grown = self._free_before - setup.free_space(root)
            self.show(session.setup_grew(self.state, job, grown))
            return GLib.SOURCE_CONTINUE

        def done(_ids) -> None:
            state = session.setup_done(self.state, job)
            if state is not self.state:
                self.show(state)
                if song is not None:
                    self.open_song(song)

        def run_setup() -> list[str]:
            report = worker.on_main_loop(step)
            for adapter in missing:
                api.setup_adapters(adapter, "cpu", root, progress=report, cancel=token)
            return list(missing)

        if not self._sampling:
            self._sampling = GLib.timeout_add(SAMPLE_MS, sample)
        self.job_thread = worker.run(
            run_setup, done, lambda exc: self.show(session.failed(self.state, job, exc))
        )

    def _setup_rows(self, state: session.SettingUp):
        """The running step shows how much it has downloaded."""
        rows = []
        for row in state.steps:
            amount = setup.amount(row.id, state.grown) if row.state == "running" else ""
            rows.append(replace(row, detail=amount) if amount else row)
        return rows

    def show(self, state: session.State) -> None:
        self.state = state
        self.actions["retry"].set_enabled(isinstance(state, session.Failed) and state.can_retry)
        is_result = isinstance(state, session.Result)
        for name in (
            "export",
            "export-pdf",
            "export-musicxml",
            "export-drums",
            "open-with",
            "play",
            "corrections",
            "previous-bar",
            "next-bar",
            "to-start",
        ):
            self.actions[name].set_enabled(is_result)
        if not is_result:
            self.playbar.stop()
        self.export_box.set_visible(is_result)
        self.corrections_button.set_visible(is_result)
        busy = session.Analysing | session.Exporting | session.SettingUp
        self.actions["cancel"].set_enabled(isinstance(state, busy))
        self.analysing.set_description("")
        if isinstance(state, session.Consent):
            self.heading.set_title(APP_NAME)
            self.heading.set_subtitle("")
            if self.consent.get_child() is None or self._consent_for != state.missing:
                self._consent_for = state.missing
                self.consent.set_child(setup_ui.consent_page(state.missing))
            self.pages.set_visible_child_name("consent")
        elif isinstance(state, session.SetupFailed):
            self.heading.set_title(APP_NAME)
            self.heading.set_subtitle("")
            page = setup_ui.error_page(
                state.steps, setup.server(state.step), setup.details(state.details)
            )
            self.setup_error.set_child(page)
            self.pages.set_visible_child_name("setup-error")
        elif isinstance(state, session.SettingUp):
            self.heading.set_title(APP_NAME)
            self.heading.set_subtitle("")
            self.analysing.set_title(_("Downloading the Models"))
            self.analysing.set_description(
                _(
                    "If this is interrupted, Stickler picks up where it stopped the next time "
                    "you open it."
                )
            )
            self._show_steps(self._setup_rows(state))
        elif isinstance(state, session.Exporting):
            self.heading.set_title(state.previous.title)
            self.heading.set_subtitle(state.previous.subtitle)
            self.analysing.set_title(_("Saving the Drum Track"))
            self._show_steps(state.steps)
        elif isinstance(state, session.Analysing):
            self.heading.set_title(state.song.stem)
            self.heading.set_subtitle("")
            self.analysing.set_title(_("Writing the Drum Part"))
            self._show_steps(state.steps)
        elif isinstance(state, session.Result):
            self.heading.set_title(state.title)
            self.heading.set_subtitle(state.subtitle)
            if state.notation is not self._shown:
                corrected = state.info is self._shown_info  # same analysis, new notation
                self._shown, self._shown_info = state.notation, state.info
                self.sheet.show_musicxml(state.notation.musicxml.read_text(encoding="utf-8"))
                if corrected:  # the music goes on; the marker follows the new bars
                    self.playbar.set_bars(state.notation.bars)
                else:
                    self.playbar.set_song(
                        state.song,
                        paths.hits_path(state.song),
                        state.info.seconds,
                        state.notation.bars,
                    )
            self.panel.show_values(
                state.wanted,
                beats_per_bar=state.notation.meter[0],
                first_one=state.notation.first_downbeat,
            )
            self.pages.set_visible_child_name("result")
        elif isinstance(state, session.Failed):
            self.heading.set_title(state.song.stem)
            self.heading.set_subtitle("")
            self.error.set_title(state.title)
            self.error.set_description(state.description)
            self.error_details.set_label(state.details)
            self.error_expander.set_expanded(False)
            self.retry_button.set_visible(state.can_retry)
            self.pages.set_visible_child_name("error")
        else:
            self.heading.set_title(APP_NAME)
            self.heading.set_subtitle("")
            self.pages.set_visible_child_name("empty")
