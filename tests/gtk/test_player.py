"""The real GStreamer pipeline, without a loudspeaker (fakesink, in real time)."""

import time

import numpy as np
import pytest

pytestmark = pytest.mark.gtk


def _settle(predicate=lambda: False, seconds=1.0):
    from gi.repository import GLib

    context, end = GLib.MainContext.default(), time.monotonic() + seconds
    while time.monotonic() < end:
        context.iteration(False)
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _wavs(tmp_path, seconds=4.0):
    from stickler import audio

    rate = 44100
    t = np.arange(int(seconds * rate)) / rate
    song = audio.write_wav(tmp_path / "song.wav", 0.2 * np.sin(2 * np.pi * 220 * t), rate)
    hits = audio.write_wav(tmp_path / "hits.wav", np.zeros(int(seconds * 22050)), 22050)
    return song, hits


def test_the_player_plays_both_sources_seeks_and_stops(tmp_path):
    from gi.repository import Gst

    from stickler_gtk.ui.player import Player

    song, hits = _wavs(tmp_path)
    ended, errors = [], []
    player = Player(sink="fakesink", on_end=lambda: ended.append(True), on_error=errors.append)
    player.load(song, hits)
    assert player.duration() == pytest.approx(4.0, abs=0.05)
    player.play()
    assert _settle(lambda: player.position() > 0.3)
    player.pause()
    player.seek(2.0)
    assert player.position() == pytest.approx(2.0, abs=0.05)
    player.set_volumes(0.5, 0.0)
    assert player.volumes() == (0.5, 0.0)
    player.seek(3.8)
    player.play()
    assert _settle(lambda: bool(ended), seconds=2.0), "no end of stream"
    player.stop()
    assert player.state() == Gst.State.NULL
    assert errors == []


def test_a_song_without_its_clicks_still_plays(tmp_path):
    from stickler_gtk.ui.player import Player

    song, _ = _wavs(tmp_path)
    player = Player(sink="fakesink")
    player.load(song, None)
    player.play()
    assert _settle(lambda: player.position() > 0.2)
    player.stop()


def test_an_unreadable_song_reports_an_error(tmp_path):
    from stickler_gtk.ui.player import Player

    broken = tmp_path / "broken.flac"
    broken.write_bytes(b"not audio")
    errors = []
    player = Player(sink="fakesink", on_error=errors.append)
    player.load(broken, None)
    player.play()
    assert _settle(lambda: bool(errors))
    player.stop()
