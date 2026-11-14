"""The libadwaita application: one main window."""

from __future__ import annotations

from gi.repository import Adw

from stickler_gtk import APP_ID
from stickler_gtk.ui.window import Window


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)

    def do_activate(self) -> None:
        window = self.get_active_window() or Window(application=self)
        window.present()
