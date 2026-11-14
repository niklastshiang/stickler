"""The main window (design screen 4: drop or open a song)."""

from __future__ import annotations

from gi.repository import Adw, Gtk

DEFAULT_SIZE = (1000, 700)


def _empty_page() -> Gtk.Widget:
    open_button = Gtk.Button(label="Open a Song…", halign=Gtk.Align.CENTER)
    open_button.add_css_class("pill")
    open_button.add_css_class("suggested-action")
    page = Adw.StatusPage(
        icon_name="audio-x-generic-symbolic",
        title="Drop a Song Here",
        description=(
            "Stickler listens to the drums and writes them as sheet music. "
            "MP3, FLAC, WAV or OGG; a song takes about 15 seconds."
        ),
        child=open_button,
    )
    return page


class Window(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(title="Stickler", **kwargs)
        self.set_default_size(*DEFAULT_SIZE)
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Stickler"))
        view = Adw.ToolbarView(content=_empty_page())
        view.add_top_bar(header)
        self.set_content(view)
