"""The sheet music on the result page (SPEC.md, module `sheet-view`; design screen 6): Verovio's
pages one under the other, drawn with librsvg, as wide as the window, with zoom; inverted in
dark style; the marked bar in blue. What is engraved where, and which bar a time or a click
means, is `stickler_gtk.logic`'s business (engraving, marker)."""

from __future__ import annotations

import math

import cairo
from gi.repository import Adw, Gdk, GLib, Gtk, Rsvg

from stickler import api
from stickler_gtk.logic import engraving, marker, zoom

GUTTER = 12  # pixels around the pages
RELAYOUT_AFTER_MS = 150  # wait for resizing to pause before engraving anew
MARK = (0.21, 0.52, 0.89, 0.25)  # libadwaita's blue accent, see-through
MARK_RADIUS = 6


class PageView(Gtk.DrawingArea):
    """One page. It is drawn once into a picture (at the screen's pixel density, inverted in
    dark style); drawing the widget only paints that picture, scaled while a zoom gesture
    runs, so zooming and scrolling stay smooth."""

    def __init__(self, page: engraving.Page, on_click) -> None:
        super().__init__(content_width=round(page.width), content_height=round(page.height))
        self.page = page
        self.scale = 1.0  # shown size / laid-out size, while a zoom waits for a new layout
        self.mark: engraving.Box | None = None
        self.handle = Rsvg.Handle.new_from_data(page.svg.encode())
        self._picture: cairo.ImageSurface | None = None
        self._picture_for: tuple[bool, int] | None = None  # (dark, pixel density)
        self.add_css_class("card")
        self.set_draw_func(self._draw)
        click = Gtk.GestureClick()
        click.connect("released", lambda _g, _n, x, y: on_click(x / self.scale, y / self.scale))
        self.add_controller(click)

    def set_mark(self, box: engraving.Box | None) -> None:
        if box != self.mark:
            self.mark = box
            self.queue_draw()

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        self.set_content_width(round(self.page.width * scale))
        self.set_content_height(round(self.page.height * scale))
        self.queue_draw()

    def restyle(self) -> None:
        self._picture = None
        self.queue_draw()

    def _render(self) -> cairo.ImageSurface:
        dark = Adw.StyleManager.get_default().get_dark()
        density = self.get_scale_factor()
        if self._picture is not None and self._picture_for == (dark, density):
            return self._picture
        width, height = math.ceil(self.page.width), math.ceil(self.page.height)
        picture = cairo.ImageSurface(cairo.FORMAT_RGB24, width * density, height * density)
        cr = cairo.Context(picture)
        cr.scale(density, density)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        viewport = Rsvg.Rectangle()
        viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, width, height
        self.handle.render_document(cr, viewport)
        if dark:  # light notes on a dark page
            cr.set_operator(cairo.OPERATOR_DIFFERENCE)
            cr.set_source_rgb(0.88, 0.88, 0.89)
            cr.paint()
        self._picture, self._picture_for = picture, (dark, density)
        return picture

    def _draw(self, _area, cr: cairo.Context, _width: int, _height: int) -> None:
        picture = self._render()
        cr.save()
        cr.scale(self.scale / self.get_scale_factor(), self.scale / self.get_scale_factor())
        cr.set_source_surface(picture, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        cr.restore()
        if self.mark is not None:  # over the inverted page, so blue in both styles
            cr.scale(self.scale, self.scale)
            box = self.mark
            cr.new_sub_path()
            for cx, cy, start in (
                (box.x + box.width - MARK_RADIUS, box.y + MARK_RADIUS, -0.5),
                (box.x + box.width - MARK_RADIUS, box.y + box.height - MARK_RADIUS, 0.0),
                (box.x + MARK_RADIUS, box.y + box.height - MARK_RADIUS, 0.5),
                (box.x + MARK_RADIUS, box.y + MARK_RADIUS, 1.0),
            ):
                cr.arc(cx, cy, MARK_RADIUS, start * math.pi, (start + 0.5) * math.pi)
            cr.close_path()
            cr.set_source_rgba(*MARK)
            cr.fill()


class Sheet(Gtk.ScrolledWindow):
    def __init__(self, zoom_level: float = 1.0, on_zoom=None) -> None:
        # EXTERNAL: no sideways scroll bar, and the pages' width is not the window's minimum,
        # so the window can shrink and the pages are laid out anew for it (NEVER kept it wide)
        super().__init__(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, vexpand=True, hexpand=True)
        self.musicxml: str | None = None
        self.zoom = zoom_level
        self.laid_out = zoom_level  # the zoom the current pages were engraved at
        self.on_zoom = on_zoom  # told every new zoom (the window remembers it)
        self.on_bar = None  # told the written bar a click hit (playback jumps there)
        self.pages: list[engraving.Page] = []
        self.views: list[PageView] = []
        self.marked: int | None = None  # the written bar shown in blue
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
        pinch = Gtk.GestureZoom()  # two fingers on a touchpad or touchscreen
        pinch.connect("begin", lambda *_a: setattr(self, "_pinch_from", self.zoom))
        pinch.connect("scale-changed", lambda _g, scale: self.pinch(scale))
        self.add_controller(pinch)
        self._pinch_from = 1.0
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_a: self._redraw())

    # what the window asks

    def show_musicxml(self, musicxml: str) -> None:
        self.musicxml = musicxml
        self.relayout()

    def set_zoom(self, value: float) -> None:
        if value != self.zoom:
            self.zoom = value
            self._zoomed()
            self.relayout()

    def _zoomed(self) -> None:
        if self.on_zoom is not None:
            self.on_zoom(self.zoom)

    def pinch(self, scale: float) -> None:
        """Follows a pinch: the zoom is set at once, the new layout once the fingers pause
        (Verovio for every step of the gesture would stutter)."""
        self.preview_zoom(zoom.pinched(self._pinch_from, scale))

    def preview_zoom(self, value: float) -> None:
        """Shows `value` at once by scaling the drawn pages; the sharp layout follows."""
        if value == self.zoom:
            return
        self.zoom = value
        self._zoomed()
        for view in self.views:
            view.set_scale(self.zoom / self.laid_out)
        self._relayout_soon()

    def _relayout_soon(self) -> None:
        if self._pending:
            GLib.source_remove(self._pending)
        self._pending = GLib.timeout_add(RELAYOUT_AFTER_MS, self._relayout_once)

    def relayout(self) -> None:
        width = self.get_width() - 2 * GUTTER
        if self.musicxml is None or width <= 0:
            return
        self.pages = engraving.engrave(self.musicxml, width=width, zoom=self.zoom)
        self.laid_out = self.zoom
        for view in self.views:
            self.column.remove(view)
        self.views = [
            PageView(page, lambda x, y, k=k: self.mark_at(k, x, y))
            for k, page in enumerate(self.pages)
        ]
        for view in self.views:
            self.column.append(view)
        self._show_mark(scroll=False)

    def mark_at(self, page: int, x: float, y: float) -> None:
        """A click on page `page` at (x, y): marks the bar there; beside every bar, nothing
        changes."""
        found = marker.bar_at_point(self.pages[page], x, y)
        if found is not None:
            self.marked = found
            self._show_mark(scroll=False)
            if self.on_bar is not None:
                self.on_bar(found)

    def mark_time(self, bars: list[api.BarTime], seconds: float) -> None:
        """Marks the bar sounding at `seconds` and scrolls it into view (`playback` calls it)."""
        self.marked = marker.written_at(bars, seconds)
        self._show_mark(scroll=True)

    def marked_box(self) -> tuple[int, engraving.Box] | None:
        return None if self.marked is None else marker.locate(self.pages, self.marked)

    def _show_mark(self, *, scroll: bool) -> None:
        found = self.marked_box()
        for k, view in enumerate(self.views):
            view.set_mark(found[1] if found and found[0] == k else None)
        if scroll and found:
            self._scroll_to(*found)

    def _scroll_to(self, page: int, box: engraving.Box) -> None:
        """Brings the box into view, a third down from the top, when it is not visible."""
        top = GUTTER + sum(p.height + GUTTER for p in self.pages[:page]) + box.y
        adjustment = self.get_vadjustment()
        visible = adjustment.get_value(), adjustment.get_value() + adjustment.get_page_size()
        if top >= visible[0] and top + box.height <= visible[1]:
            return
        target = top - adjustment.get_page_size() / 3
        upper = adjustment.get_upper() - adjustment.get_page_size()
        adjustment.set_value(min(max(target, adjustment.get_lower()), max(upper, 0)))

    # what GTK tells it

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        Gtk.ScrolledWindow.do_size_allocate(self, width, height, baseline)
        if width != self._width:
            self._width = width
            self._relayout_soon()

    def _relayout_once(self) -> bool:
        self._pending = 0
        self.relayout()
        return GLib.SOURCE_REMOVE

    def _on_scroll(self, controller: Gtk.EventControllerScroll, _dx: float, dy: float) -> bool:
        if not controller.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return False  # an ordinary scroll moves the pages
        self.preview_zoom(zoom.scrolled(self.zoom, dy))
        return True

    def _redraw(self) -> None:
        for view in self.views:
            view.restyle()
