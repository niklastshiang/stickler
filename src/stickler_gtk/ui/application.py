"""The libadwaita application: one main window; songs can also come from the command line or
"Open With" (HANDLES_OPEN)."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GLibUnix, Gtk

from stickler_gtk import APP_ID
from stickler_gtk.logic import settings
from stickler_gtk.ui import menu
from stickler_gtk.ui.window import Window

# The dashed drop area of design screen 4; :drop(active) while a file is dragged over it
STYLE = """
.drop-area { border: 2px dashed alpha(currentColor, 0.15); border-radius: 18px; margin: 24px; }
.drop-area:drop(active) { border-color: var(--accent-bg-color);
  background: color-mix(in srgb, var(--accent-bg-color) 8%, transparent); }
"""

# GNOME HIG standard shortcuts, plus Escape and Ctrl+E (SPEC.md, module `app-shell`)
ACCELS = {
    "win.open": ["<Control>o"],
    "win.cancel": ["Escape"],
    "win.export": ["<Control>e"],
    "win.close": ["<Control>w"],
    "app.shortcuts": ["<Control>question"],
    "app.quit": ["<Control>q"],
    "win.zoom-in": ["<Control>plus", "<Control>equal", "<Control>KP_Add"],
    "win.zoom-out": ["<Control>minus", "<Control>KP_Subtract"],
    "win.zoom-reset": ["<Control>0", "<Control>KP_0"],
    "win.play": ["space"],
    "win.previous-bar": ["Left"],
    "win.next-bar": ["Right"],
    "win.to-start": ["Home"],
    "win.corrections": ["F9"],
}


def register_icons() -> None:
    """The app's icons live in its prefix (the app environment, or /app in the Flatpak);
    GTK finds them there as the window's and the About dialog's icon."""
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    theme.add_search_path(str(Path(sys.prefix) / "share" / "icons"))
    Gtk.Window.set_default_icon_name(APP_ID)


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        register_icons()
        css = Gtk.CssProvider()
        css.load_from_string(STYLE + menu.STYLE)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        menu.apply_appearance(settings.load(settings.store_path()).appearance)
        for name, run in (
            ("shortcuts", lambda: menu.shortcuts_dialog().present(self.get_active_window())),
            ("about", lambda: menu.about_dialog().present(self.get_active_window())),
            ("quit", self._quit),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, run=run: run())
            self.add_action(action)
        for action, keys in ACCELS.items():
            self.set_accels_for_action(action, keys)
        # Models run in their own process group; ending the app by a signal (Ctrl+C in a
        # terminal, logging out) cancels them first, as closing the window does.
        for signum in (signal.SIGINT, signal.SIGTERM):
            GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signum, self._quit_on_signal)

    def _quit(self) -> None:
        for window in self.get_windows():
            window.close()  # the window cancels its job and waits for it on close-request
        self.quit()

    def _quit_on_signal(self) -> bool:
        self._quit()
        return GLib.SOURCE_REMOVE

    def _window(self) -> Window:
        window = self.get_active_window() or Window(application=self)
        window.present()
        return window

    def do_activate(self) -> None:
        self._window()

    def do_open(self, files: list[Gio.File], _count: int, _hint: str) -> None:
        window = self._window()
        songs = [Path(f.get_path()) for f in files if f.get_path()]
        if songs:
            window.open_song(songs[0])
