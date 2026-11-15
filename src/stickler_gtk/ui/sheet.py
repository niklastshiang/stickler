"""The sheet music on the result page (SPEC.md, module `sheet-view`; design screen 6): Verovio's
pages one under the other, drawn with librsvg, as wide as the window, with zoom; inverted in
dark style. What is engraved where is `stickler_gtk.logic.engraving`'s business."""

from __future__ import annotations

import cairo
from gi.repository import Adw, Gdk, GLib, Gtk, Rsvg

from stickler_gtk.logic import engraving, zoom

GUTTER = 12  # pixels around the pages
RELAYOUT_AFTER_MS = 150  # wait for resizing to pause before engraving anew


class PageView(Gtk.DrawingArea):
    def __init__(self, page: engraving.Page) -> None:
        super().__init__(content_width=round(page.width), content_height=round(page.height))
        self.page = page
        self.handle = Rsvg.Handle.new_from_data(page.svg.encode())
        self.add_css_class("card")
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr: cairo.Context, width: int, height: int) -> None:
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        viewport = Rsvg.Rectangle()
        viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, width, height
        self.handle.render_document(cr, viewport)
        if Adw.StyleManager.get_default().get_dark():  # light notes on a dark page
            cr.set_operator(cairo.OPERATOR_DIFFERENCE)
            cr.set_source_rgb(0.88, 0.88, 0.89)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)


class Sheet(Gtk.ScrolledWindow):
    def __init__(self) -> None:
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
        self.musicxml: str | None = None
        self.zoom = 1.0
        self.pages: list[engraving.Page] = []
        self.views: list[PageView] = []
        self._width = 0
        self._pending = 0
        self.column = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=GUTTER,
            margin_top=GUTTER,
            margin_bottom=GUTTER,
            margin_start=GUTTER,
            margin_end=GUTTER,
        )
        self.set_child(self.column)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_a: self._redraw())

    # what the window asks

    def show_musicxml(self, musicxml: str) -> None:
        self.musicxml = musicxml
        self.relayout()

    def set_zoom(self, value: float) -> None:
        if value != self.zoom:
            self.zoom = value
            self.relayout()

    def relayout(self) -> None:
        width = self.get_width() - 2 * GUTTER
        if self.musicxml is None or width <= 0:
            return
        self.pages = engraving.engrave(self.musicxml, width=width, zoom=self.zoom)
        for view in self.views:
            self.column.remove(view)
        self.views = [PageView(page) for page in self.pages]
        for view in self.views:
            self.column.append(view)

    # what GTK tells it

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        Gtk.ScrolledWindow.do_size_allocate(self, width, height, baseline)
        if width != self._width:
            self._width = width
            if self._pending:
                GLib.source_remove(self._pending)
            self._pending = GLib.timeout_add(RELAYOUT_AFTER_MS, self._relayout_once)

    def _relayout_once(self) -> bool:
        self._pending = 0
        self.relayout()
        return GLib.SOURCE_REMOVE

    def _on_scroll(self, controller: Gtk.EventControllerScroll, _dx: float, dy: float) -> bool:
        if not controller.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return False  # an ordinary scroll moves the pages
        self.set_zoom(zoom.scrolled(self.zoom, dy))
        return True

    def _redraw(self) -> None:
        for view in self.views:
            view.queue_draw()
