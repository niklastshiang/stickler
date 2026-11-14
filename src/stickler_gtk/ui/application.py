"""The libadwaita application: one main window; songs can also come from the command line or
"Open With" (HANDLES_OPEN)."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, Gtk

from stickler_gtk import APP_ID
from stickler_gtk.ui.window import Window

# The dashed drop area of design screen 4; :drop(active) while a file is dragged over it
STYLE = """
.drop-area { border: 2px dashed alpha(currentColor, 0.15); border-radius: 18px; margin: 24px; }
.drop-area:drop(active) { border-color: var(--accent-bg-color);
  background: color-mix(in srgb, var(--accent-bg-color) 8%, transparent); }
"""

ACCELS = {"win.open": ["<Control>o"]}


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(STYLE)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        for action, keys in ACCELS.items():
            self.set_accels_for_action(action, keys)

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
