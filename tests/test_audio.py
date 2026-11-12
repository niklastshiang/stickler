"""Tests für die Audiodauer per ffprobe."""

import wave

import pytest

from stickler import audio


def write_wav(path, seconds, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


def test_duration_of_wav(tmp_path):
    assert audio.duration(write_wav(tmp_path / "a.wav", 2.5)) == pytest.approx(2.5, abs=0.01)


def test_duration_of_invalid_file_raises(tmp_path):
    bad = tmp_path / "kaputt.wav"
    bad.write_bytes(b"kein audio")
    with pytest.raises(RuntimeError, match="kaputt.wav"):
        audio.duration(bad)
