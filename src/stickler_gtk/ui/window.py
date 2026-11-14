"""The main window (design screen 4: drop or open a song)."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from stickler_gtk import APP_NAME
from stickler_gtk.i18n import _

DEFAULT_SIZE = (1000, 700)


def _empty_page() -> Gtk.Widget:
    open_button = Gtk.Button(label=_("Open a Song…"), halign=Gtk.Align.CENTER)
    open_button.add_css_class("pill")
    open_button.add_css_class("suggested-action")
    page = Adw.StatusPage(
        icon_name="audio-x-generic-symbolic",
        title=_("Drop a Song Here"),
        description=_(
            "Stickler listens to the drums and writes them as sheet music. "
            "MP3, FLAC, WAV or OGG; a song takes about 15 seconds."
        ),
        child=open_button,
    )
    return page


class Window(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(title=APP_NAME, **kwargs)
        self.set_default_size(*DEFAULT_SIZE)
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title=APP_NAME))
        view = Adw.ToolbarView(content=_empty_page())
        view.add_top_bar(header)
        self.set_content(view)
