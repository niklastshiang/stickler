"""The playback bar under the sheet (SPEC.md, module `playback`; design screen 6): play/pause,
the time, a position slider, the song's length and the bar that sounds. The pipeline is loaded
on the first play, so showing a result never waits for GStreamer."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gi.repository import GLib, Gtk

from stickler import api
from stickler_gtk.i18n import _
from stickler_gtk.logic import playback
from stickler_gtk.ui.player import Player

TICK_MS = 50  # how often the time, the slider and the marker follow the song
PLAY_ICON = "media-playback-start-symbolic"
PAUSE_ICON = "media-playback-pause-symbolic"


class PlayBar(Gtk.Box):
    def __init__(self, on_position: Callable[[float], None]) -> None:
        super().__init__(spacing=12, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
        self.add_css_class("toolbar")
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
        for widget in (self.play, self.time, self.position, self.length, self.bar):
            self.append(widget)

    # what the window asks

    def set_song(self, song: Path, clicks: Path | None, seconds: float, bars) -> None:
        """A new result: stopped at the start, nothing loaded yet."""
        self.stop()
        self.song, self.clicks, self.bars = song, clicks, list(bars)
        self.position.set_range(0, max(seconds, 0.001))
        self.length.set_label(playback.clock(seconds))
        self._show(0.0)

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
