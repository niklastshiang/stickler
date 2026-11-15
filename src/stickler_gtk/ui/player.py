"""The player (SPEC.md, module `playback`): one GStreamer pipeline mixing the song and the
detected hits as clicks, so play, pause and seek always move both.

    song  ─ uridecodebin ─ audioconvert ─ audioresample ─ caps ─ volume ─┐
    clicks ─ uridecodebin ─ audioconvert ─ audioresample ─ caps ─ volume ─┴ audiomixer ─ sink

What to play and how loud is `stickler_gtk.logic.playback`'s business."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gi.repository import Gst

Gst.init(None)

MIXED = "audio/x-raw,format=F32LE,rate=48000,channels=2,layout=interleaved"
SETTLE = 2 * Gst.SECOND  # how long a seek or a pause may take to finish


class Player:
    def __init__(
        self,
        *,
        sink: str = "autoaudiosink",
        on_end: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.sink_name = sink
        self.on_end, self.on_error = on_end, on_error
        self.pipeline: Gst.Pipeline | None = None
        self.levels: list[Gst.Element] = []  # the song's and the clicks' volume

    def load(self, song: Path, clicks: Path | None) -> None:
        """A new pipeline, paused at the start (stops the one before)."""
        self.stop()
        pipeline = Gst.Pipeline.new("stickler")
        mixer = Gst.ElementFactory.make("audiomixer")
        sink = Gst.ElementFactory.make(self.sink_name)
        if self.sink_name == "fakesink":
            sink.set_property("sync", True)  # real time, as a loudspeaker would play it
        pipeline.add(mixer)
        pipeline.add(sink)
        mixer.link(sink)
        self.levels = [self._branch(pipeline, mixer, path) for path in (song, clicks) if path]
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", lambda *_a: self.on_end and self.on_end())
        bus.connect("message::error", self._error)
        self.pipeline = pipeline
        pipeline.set_state(Gst.State.PAUSED)
        pipeline.get_state(SETTLE)

    def _branch(self, pipeline: Gst.Pipeline, mixer: Gst.Element, path: Path) -> Gst.Element:
        source = Gst.ElementFactory.make("uridecodebin")
        source.set_property("uri", Gst.filename_to_uri(str(path)))
        convert = Gst.ElementFactory.make("audioconvert")
        resample = Gst.ElementFactory.make("audioresample")
        caps = Gst.ElementFactory.make("capsfilter")
        caps.set_property("caps", Gst.Caps.from_string(MIXED))
        level = Gst.ElementFactory.make("volume")
        for element in (source, convert, resample, caps, level):
            pipeline.add(element)
        convert.link(resample)
        resample.link(caps)
        caps.link(level)
        level.link(mixer)

        def linked(_source, pad: Gst.Pad) -> None:
            target = convert.get_static_pad("sink")
            if not target.is_linked() and pad.query_caps(None).to_string().startswith("audio"):
                pad.link(target)

        source.connect("pad-added", linked)
        return level

    def _error(self, _bus, message: Gst.Message) -> None:
        error, _debug = message.parse_error()
        if self.on_error is not None:
            self.on_error(error.message)

    # what the window asks

    def play(self) -> None:
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.PLAYING)

    def pause(self) -> None:
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.pipeline.get_state(SETTLE)

    def seek(self, seconds: float) -> None:
        if self.pipeline is not None:
            self.pipeline.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                max(0, int(seconds * Gst.SECOND)),
            )
            self.pipeline.get_state(SETTLE)

    def position(self) -> float:
        if self.pipeline is None:
            return 0.0
        found, value = self.pipeline.query_position(Gst.Format.TIME)
        return value / Gst.SECOND if found else 0.0

    def duration(self) -> float:
        if self.pipeline is None:
            return 0.0
        found, value = self.pipeline.query_duration(Gst.Format.TIME)
        return value / Gst.SECOND if found else 0.0

    def playing(self) -> bool:
        return self.state() == Gst.State.PLAYING

    def state(self) -> Gst.State:
        if self.pipeline is None:
            return Gst.State.NULL
        return self.pipeline.get_state(0)[1]

    def set_volumes(self, song: float, clicks: float) -> None:
        for level, value in zip(self.levels, (song, clicks), strict=False):
            level.set_property("volume", value)

    def volumes(self) -> tuple[float, ...]:
        return tuple(level.get_property("volume") for level in self.levels)

    def stop(self) -> None:
        """NULL: nothing plays or holds the sound device any more."""
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline.get_bus().remove_signal_watch()
            self.pipeline = None
            self.levels = []
