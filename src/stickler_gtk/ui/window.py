"""The main window (design screens 4 and 5, the result header of 6). Its flows (analysis,
setup, exports, corrections, recent songs, removal) live in `stickler_app.controller`, shared
with the Mac app's bridge; the window turns clicks into the controller's commands and draws
the state, recent songs and notices it reports (SPEC.md, module `core-bridge`, scope 7)."""

from __future__ import annotations

import contextlib
from dataclasses import replace
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from stickler import api
from stickler_app import (
    APP_NAME,
    controller,
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
from stickler_app.i18n import _
from stickler_app.steps import StepRow
from stickler_gtk.ui import corrections as corrections_ui
from stickler_gtk.ui import menu, pdf, worker
from stickler_gtk.ui import setup as setup_ui
from stickler_gtk.ui.playbar import PlayBar
from stickler_gtk.ui.sheet import Sheet

DEFAULT_SIZE = (1000, 700)
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
        self.state: session.State = session.Empty()  # the state drawn
        self.controller = controller.Controller(post=worker.to_main_loop(self._on_event))

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
        header.pack_end(menu.main_menu(self.zoom_label, removable=paths.packaged() is not None))
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

        self._shown: api.Notation | None = None  # the notation on the sheet
        self._shown_info: api.SongInfo | None = None  # a correction keeps it, a new analysis not
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
            ("setup-download", self.controller.agree),
            ("setup-later", self.controller.not_now),
            ("setup-retry", self.controller.retry_setup),
            ("remove-models", self.ask_to_remove_models),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, run=handler: run())
            self.add_action(action)
            self.actions[name] = action
        self.connect("close-request", self._on_close)
        self._consent_for: tuple[str, ...] = ()
        self._step_rows: list[tuple[StepRow, Adw.ActionRow]] = []  # what the step list shows
        self.show(self.state)
        self.controller.start()  # are the models there? (in a thread)

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
        self.controller.open(song)

    def retry(self) -> None:
        self.controller.retry()

    def cancel(self) -> None:
        self.controller.cancel()

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
        self.controller.correct(fix)

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
                # the legend (module `legend`) is deferred (owner, 2026-11-17); to switch it
                # back on: engraving.a4_pages(xml, legend=legend.score(xml))
                pages = engraving.a4_pages(xml)
                pdf.write_pdf(pages, dest, title=result.title)
            except OSError as exc:
                self.toast(_("Could not save: {reason}").format(reason=exc.strerror))
                return
            self._saved(_("Saved “{name}”").format(name=dest.name), dest)

        self._save_dialog(exports.pdf_name(result.song), save)

    def open_with(self) -> None:
        """The system's app chooser for the MusicXML (OpenURI portal in the Flatpak)."""
        if isinstance(self.state, session.Result):
            musicxml = Gio.File.new_for_path(str(self.state.notation.musicxml))
            Gtk.FileLauncher(file=musicxml, always_ask=True).launch(self, None, None, None)

    def export_musicxml(self) -> None:
        result = self.state
        if isinstance(result, session.Result):
            name = exports.musicxml_name(result.song)
            self._save_dialog(name, self.controller.export_musicxml)

    def export_drums(self) -> None:
        result = self.state
        cost = self.controller.drum_track_cost()
        if not isinstance(result, session.Result) or cost is None:
            return
        alert = Adw.AlertDialog(heading=_("Save the Drum Track?"), body=cost.text)
        alert.add_response("cancel", _("Cancel"))
        alert.add_response("save", _("Choose Where to Save…"))
        alert.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        alert.set_default_response("save")

        def answered(_alert, response: str) -> None:
            if response == "save":
                name = exports.drum_track_name(result.song)
                self._save_dialog(name, lambda dest: self._start_drums(result, dest))

        alert.connect("response", answered)
        alert.present(self)

    def _start_drums(self, _result: session.Result, dest: Path, *, setup: bool = False) -> None:
        """The dialog's answer for the result it was asked about. The controller checks again
        whether a result is shown and whether Demucs is missing (`setup`, the cost the dialog
        named, is only what it saw then)."""
        self.controller.export_drum_track(dest)

    def _saved(self, text: str, dest: Path) -> None:
        toast = Adw.Toast(title=text, button_label=_("Open"), timeout=8)
        toast.connect(
            "button-clicked",
            lambda _t: Gtk.FileLauncher.new(Gio.File.new_for_path(str(dest))).launch(
                self, None, None, None
            ),
        )
        self.toasts.add_toast(toast)

    @property
    def recent(self) -> list[recent.Recent]:
        return list(self.controller.recent)

    @property
    def _removing(self) -> bool:
        return self.controller.removing

    def _on_event(self, event: controller.Event) -> None:
        """What the controller reports, on the main loop. A late event (queued from a thread
        while a click changed things here) draws the newest state and list, not its own."""
        if isinstance(event, controller.Changed):
            self.show(self.controller.state)
        elif isinstance(event, controller.RecentChanged):
            self._show_recent()
        elif event.opens is not None:
            self._saved(event.text, event.opens)
        else:
            self.toast(event.text)

    def _show_recent(self) -> None:
        for row in self.recent_rows:
            self.recent_group.remove(row)
        self.recent_rows = []
        for entry in recent.rows(self.controller.recent):
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
                    lambda _b, path=entry.path: self.controller.forget_recent(path),
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
        self.controller.shutdown(seconds)

    # what the window shows

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text))

    def _show_steps(self, rows) -> None:
        """Rows whose step and state stay are kept, so a running spinner is not restarted by
        each progress report (the download reports twice a second); only their line changes."""
        shown = self._step_rows
        if [r.id for r in rows] != [r.id for r, _w in shown]:
            self.steps.remove_all()
            shown = []
        kept = []
        for k, step in enumerate(rows):
            if k < len(shown) and shown[k][0].state == step.state:
                widget = shown[k][1]
                if widget.get_subtitle() != step.detail:
                    widget.set_subtitle(step.detail)
            else:
                widget = _step_row(step)
                if k < len(shown):
                    self.steps.remove(shown[k][1])
                self.steps.insert(widget, k)
            kept.append((step, widget))
        self._step_rows = kept
        self.pages.set_visible_child_name("analysing")

    # removing the downloaded models (SPEC.md, module `polish`)

    def ask_to_remove_models(self) -> None:
        """Measures what would go (in the worker), then asks."""
        worker.run(
            self.controller.removal_sizes,
            lambda sizes: self._ask_to_remove(*sizes),
            lambda exc: self.toast(_("Could not check the models: {reason}").format(reason=exc)),
        )

    def _ask_to_remove(self, models: int, everything: int) -> None:
        def body(all_of_it: bool) -> str:
            freed = GLib.format_size(everything if all_of_it else models)
            return _(
                "This frees {size}. Stickler asks before it downloads the models again."
            ).format(size=freed)

        also = Gtk.CheckButton(label=_("Also remove settings, recent songs and corrections"))
        alert = Adw.AlertDialog(
            heading=_("Remove Downloaded Models?"), body=body(False), extra_child=also
        )
        also.connect("toggled", lambda b: alert.set_body(body(b.get_active())))
        alert.add_response("cancel", _("Cancel"))
        alert.add_response("remove", _("Remove"))
        alert.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_default_response("cancel")
        alert.set_close_response("cancel")
        alert.connect(
            "response",
            lambda _a, answer: answer == "remove" and self.remove_models_now(also.get_active()),
        )
        alert.present(self)

    def remove_models_now(self, everything: bool) -> None:
        """The alert's answer. Something may have started while it was open (a download
        that goes on by itself): then nothing is removed, and the reader is told why."""
        if not self.controller.remove_models(everything):
            self.toast(_("The models can be removed once the current work is done"))
            return
        self.playbar.stop()

    # the setup assistant (SPEC.md, module `setup-assistant`)

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
        self.actions["cancel"].set_enabled(isinstance(state, controller.BUSY))
        self.actions["remove-models"].set_enabled(
            paths.packaged() is not None
            and not isinstance(state, controller.BUSY)
            and not self._removing
        )
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
