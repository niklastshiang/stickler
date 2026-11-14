"""The main window (design screens 4 and 5, the result header of 6). It draws the state that
`stickler_gtk.logic.session` decides; analyses run in a worker thread."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, Gtk

from stickler import api
from stickler_gtk import APP_NAME
from stickler_gtk.i18n import _
from stickler_gtk.logic import paths, session
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
        self.analysing = Adw.StatusPage(
            title=_("Writing the Drum Part"),
            child=Adw.Clamp(maximum_size=460, child=self.steps),
        )
        self.result = Adw.StatusPage(
            icon_name="emblem-ok-symbolic",
            title=_("The Notes Are Ready"),
            description=_("The sheet music will be shown here."),
        )
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pages.add_named(_empty_page(), "empty")
        self.pages.add_named(self.analysing, "analysing")
        self.pages.add_named(self.result, "result")

        self.toasts = Adw.ToastOverlay(child=self.pages)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.pages.add_controller(drop)

        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect("activate", lambda *_args: self.choose_song())
        self.add_action(open_action)

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
        self.show(session.open_song(song))
        report = worker.on_main_loop(lambda step: self.show(session.on_step(self.state, step)))

        def analyse() -> tuple[api.SongInfo, api.Notation]:
            info = api.song_info(song)
            notation = api.notate(
                song,
                paths.score_path(song),
                title=info.title,
                artist=info.artist,
                pdf=False,
                progress=report,
            )
            return info, notation

        worker.run(
            analyse,
            lambda done: self.show(session.finished(self.state, *done)),
            lambda exc: self.show(session.failed(self.state, str(exc))),
        )

    # what the window shows

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text))

    def show(self, state: session.State) -> None:
        self.state = state
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
        else:
            self.heading.set_title(APP_NAME)
            self.heading.set_subtitle("")
            self.pages.set_visible_child_name("empty")
            if state.message:
                self.toast(state.message)
