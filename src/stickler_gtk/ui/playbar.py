"""The playback bar under the sheet (SPEC.md, module `playback`; design screen 6): play/pause,
the time, a position slider, the song's length, the bar that sounds, what to hear and how loud.
The pipeline is loaded on the first play, so showing a result never waits for GStreamer."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from gi.repository import Adw, GLib, Gtk

from stickler import api
from stickler_gtk.i18n import _
from stickler_gtk.logic import playback, settings
from stickler_gtk.ui.player import Player

TICK_MS = 50  # how often the time, the slider and the marker follow the song
PLAY_ICON = "media-playback-start-symbolic"
PAUSE_ICON = "media-playback-pause-symbolic"


class PlayBar(Gtk.Box):
    def __init__(self, on_position: Callable[[float], None]) -> None:
        super().__init__(spacing=12, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
        self.rows = [Gtk.Box(spacing=12, hexpand=True), Gtk.Box(spacing=12)]
        for row in self.rows:
            self.append(row)
        self.on_position = on_position  # the window marks the sounding bar
        self.player = Player(on_end=self._ended, on_error=self._failed)
        self.on_error: Callable[[str], None] | None = None
        self.song: Path | None = None
        self.clicks: Path | None = None
        self.bars: list[api.BarTime] = []
        self.loaded = False
        self.at_end = False
        self._ticking = 0

        self.play = Gtk.Button(
            icon_name=PLAY_ICON,
            action_name="win.play",
            tooltip_text=_("Play"),
            valign=Gtk.Align.CENTER,
            css_classes=["circular"],
        )
        self.time = Gtk.Label(label=playback.clock(0), css_classes=["numeric"])
        self.position = Gtk.Scale(hexpand=True, draw_value=False)
        self.position.update_property([Gtk.AccessibleProperty.LABEL], [_("Position")])
        self.position.connect("change-value", self._dragged)
        self.length = Gtk.Label(label=playback.clock(0), css_classes=["numeric", "dim-label"])
        self.bar = Gtk.Label(css_classes=["numeric", "dim-label"])
        self.hear = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        self.hear.update_property([Gtk.AccessibleProperty.LABEL], [_("What to Hear")])
        for name, label in (("song", _("Song")), ("hits", _("Hits")), ("both", _("Both"))):
            self.hear.add(Adw.Toggle(name=name, label=label))
        self.hear.set_active_name("both")
        self.hear.connect("notify::active-name", lambda *_a: self._apply_volumes())
        stored = settings.load(settings.store_path())
        self.song_volume = self._slider(stored.song_volume)
        self.hits_volume = self._slider(stored.hits_volume)
        self.volume = Gtk.MenuButton(
            icon_name="audio-volume-high-symbolic",
            tooltip_text=_("Volume"),
            valign=Gtk.Align.CENTER,
            popover=Gtk.Popover(child=self._volume_grid()),
        )
        self.narrow = None
        self.set_narrow(False)

    def set_narrow(self, narrow: bool) -> None:
        """Design screen 6 has one row; a narrow window (screen 10) two: the time and slider
        above, play, what to hear and the volume below, without the bar number."""
        if narrow == self.narrow:
            return
        self.narrow = narrow
        for row in self.rows:
            for child in list(_children(row)):
                row.remove(child)
        self.set_orientation(Gtk.Orientation.VERTICAL if narrow else Gtk.Orientation.HORIZONTAL)
        if narrow:
            layout = (
                (self.time, self.position, self.length),
                (self.play, self.hear, self.volume),
            )
        else:
            layout = (
                (self.play, self.time, self.position, self.length),
                (self.bar, self.volume, self.hear),
            )
        for row, widgets in zip(self.rows, layout, strict=True):
            for widget in widgets:
                row.append(widget)
        self.bar.set_visible(not narrow)
        self.hear.set_hexpand(narrow)

    def _slider(self, value: float) -> Gtk.Scale:
        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.05)
        slider.set_value(value)
        slider.set_size_request(160, -1)
        slider.connect("value-changed", lambda *_a: self._volume_changed())
        return slider

    def _volume_grid(self) -> Gtk.Grid:
        """Design screen 6: one slider for the song, one for the detected hits."""
        grid = Gtk.Grid(column_spacing=12, row_spacing=6, margin_top=6, margin_bottom=6)
        for row, (label, slider) in enumerate(
            ((_("Song"), self.song_volume), (_("Detected hits"), self.hits_volume))
        ):
            name = Gtk.Label(label=label, xalign=0)
            slider.update_property([Gtk.AccessibleProperty.LABEL], [label])
            grid.attach(name, 0, row, 1, 1)
            grid.attach(slider, 1, row, 1, 1)
        return grid

    # what the window asks

    def set_song(self, song: Path, clicks: Path | None, seconds: float, bars) -> None:
        """A new result: stopped at the start, nothing loaded yet."""
        self.stop()
        self.song, self.clicks, self.bars = song, clicks, list(bars)
        self.position.set_range(0, max(seconds, 0.001))
        self.length.set_label(playback.clock(seconds))
        self._show(0.0)

    def set_bars(self, bars) -> None:
        """A corrected notation of the same song: playing goes on, the bars are new."""
        self.bars = list(bars)
        self._show(self.now())

    def toggle(self) -> None:
        if self.song is None:
            return
        if self.player.playing():
            self.player.pause()
            self._stopped_ticking()
            return
        if not self.loaded:
            clicks = self.clicks if self.clicks is not None and self.clicks.exists() else None
            self.player.load(self.song, clicks)
            self.loaded = True
            self._apply_volumes()
            self.player.seek(self.position.get_value())
        if self.at_end:
            self.at_end = False
            self.player.seek(0.0)
        self.player.play()
        self.play.set_icon_name(PAUSE_ICON)
        self.play.set_tooltip_text(_("Pause"))
        if not self._ticking:
            self._ticking = GLib.timeout_add(TICK_MS, self._tick)

    def seek(self, seconds: float) -> None:
        seconds = min(max(seconds, 0.0), self.position.get_adjustment().get_upper())
        self.at_end = False
        if self.loaded:
            self.player.seek(seconds)
        self._show(seconds)

    def now(self) -> float:
        return self.player.position() if self.loaded else self.position.get_value()

    def stop(self) -> None:
        """Nothing plays or holds the sound device any more (a new song, closing)."""
        self.player.stop()
        self.loaded = self.at_end = False
        self._stopped_ticking()

    # what GStreamer and the user tell it

    def _volume_changed(self) -> None:
        self._apply_volumes()
        song, hits = self.song_volume.get_value(), self.hits_volume.get_value()
        # unsaved, the volumes still work for this session
        with contextlib.suppress(OSError):
            settings.update(settings.store_path(), song_volume=song, hits_volume=hits)

    def _apply_volumes(self) -> None:
        if self.loaded:
            self.player.set_volumes(
                *playback.volumes(
                    self.hear.get_active_name() or "both",
                    song=self.song_volume.get_value(),
                    hits=self.hits_volume.get_value(),
                )
            )

    def _dragged(self, _scale, _scroll, value: float) -> bool:
        self.seek(value)
        return True

    def _tick(self) -> bool:
        self._show(self.player.position())
        return GLib.SOURCE_CONTINUE

    def _ended(self) -> None:
        self.player.pause()
        self.at_end = True
        self._stopped_ticking()

    def _failed(self, message: str) -> None:
        self.stop()
        if self.on_error is not None:
            self.on_error(message)

    def _stopped_ticking(self) -> None:
        if self._ticking:
            GLib.source_remove(self._ticking)
            self._ticking = 0
        self.play.set_icon_name(PLAY_ICON)
        self.play.set_tooltip_text(_("Play"))

    def _show(self, seconds: float) -> None:
        self.position.set_value(seconds)
        self.time.set_label(playback.clock(seconds))
        self.bar.set_label(playback.bar_label(self.bars, seconds))
        self.on_position(seconds)


def _children(widget: Gtk.Widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()
