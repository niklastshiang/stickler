"""The main window (design screens 4 and 5, the result header of 6). It draws the state that
`stickler_gtk.logic.session` decides; analyses run in a worker thread."""

from __future__ import annotations

import threading
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, Gtk

from stickler import api
from stickler_gtk import APP_NAME
from stickler_gtk.i18n import _
from stickler_gtk.logic import analysis, paths, session
from stickler_gtk.logic.steps import StepRow
from stickler_gtk.ui import worker

DEFAULT_SIZE = (1000, 700)


def _open_button(label: str) -> Gtk.Button:
    button = Gtk.Button(label=label, halign=Gtk.Align.CENTER, action_name="win.open")
    button.add_css_class("pill")
    button.add_css_class("suggested-action")
    return button


def _empty_page() -> Gtk.Widget:
    page = Adw.StatusPage(
        icon_name="audio-x-generic-symbolic",
        title=_("Drop a Song Here"),
        description=_(
            "Stickler listens to the drums and writes them as sheet music. "
            "MP3, FLAC, WAV or OGG; a song takes about 15 seconds."
        ),
        child=_open_button(_("Open a Song…")),
    )
    page.add_css_class("drop-area")
    return page


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
        self.state: session.State = session.Empty()

        self.heading = Adw.WindowTitle(title=APP_NAME)
        header = Adw.HeaderBar(title_widget=self.heading)
        header.pack_start(
            Gtk.Button(
                child=Adw.ButtonContent(icon_name="document-open-symbolic", label=_("Open…")),
                action_name="win.open",
                tooltip_text=_("Open a Song"),
            )
        )

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
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        buttons.append(other_button)
        buttons.append(self.retry_button)
        error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        error_box.append(Adw.Clamp(maximum_size=560, child=self.error_expander))
        error_box.append(buttons)
        self.error = Adw.StatusPage(icon_name="dialog-warning-symbolic", child=error_box)
        self.result = Adw.StatusPage(
            icon_name="emblem-ok-symbolic",
            title=_("The Notes Are Ready"),
            description=_("The sheet music will be shown here."),
        )
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pages.add_named(_empty_page(), "empty")
        self.pages.add_named(self.analysing, "analysing")
        self.pages.add_named(self.result, "result")
        self.pages.add_named(self.error, "error")

        self.toasts = Adw.ToastOverlay(child=self.pages)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.pages.add_controller(drop)

        self.token: api.CancelToken | None = None
        self.job_thread: threading.Thread | None = None
        self.actions: dict[str, Gio.SimpleAction] = {}
        for name, handler in (
            ("open", self.choose_song),
            ("cancel", self.cancel),
            ("retry", self.retry),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, run=handler: run())
            self.add_action(action)
            self.actions[name] = action
        self.connect("close-request", self._on_close)
        self.show(self.state)

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
        self._start(session.open_song(song, self.state))

    def retry(self) -> None:
        if isinstance(self.state, session.Failed) and self.state.can_retry:
            self._start(session.retry(self.state))

    def cancel(self) -> None:
        self._stop_job()
        self.show(session.cancel(self.state))

    def _stop_job(self) -> bool:
        if self.token is not None:
            self.token.cancel()  # the worker ends the model's processes within a second
            self.token = None
        return False  # let a closing window close

    def _on_close(self, _window) -> bool:
        self.wait_for_job(2.0)  # a cancel takes well under a second
        return False  # close

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
            lambda: analysis.analyse(song, paths.score_path(song), report, token),
            lambda done: self.show(session.finished(self.state, job, *done)),
            lambda exc: self.show(session.failed(self.state, job, exc)),
        )

    # what the window shows

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text))

    def show(self, state: session.State) -> None:
        self.state = state
        self.actions["cancel"].set_enabled(isinstance(state, session.Analysing))
        self.actions["retry"].set_enabled(isinstance(state, session.Failed) and state.can_retry)
        if isinstance(state, session.Analysing):
            self.heading.set_title(state.song.stem)
            self.heading.set_subtitle("")
            self.steps.remove_all()
            for step in state.steps:
                self.steps.append(_step_row(step))
            self.pages.set_visible_child_name("analysing")
        elif isinstance(state, session.Result):
            self.heading.set_title(state.title)
            self.heading.set_subtitle(state.subtitle)
            self.pages.set_visible_child_name("result")
        elif isinstance(state, session.Failed):
            self.heading.set_title(state.song.stem)
            self.heading.set_subtitle("")
            self.error.set_title(state.title)
            self.error.set_description(state.description)
            self.error_details.set_label(state.details)
            setup = state.kind == "setup"  # the commands are the point, so they stay open
            self.error_expander.set_label(_("Commands") if setup else _("Technical Details"))
            self.error_expander.set_expanded(setup)
            self.retry_button.set_visible(state.can_retry)
            self.pages.set_visible_child_name("error")
        else:
            self.heading.set_title(APP_NAME)
            self.heading.set_subtitle("")
            self.pages.set_visible_child_name("empty")
