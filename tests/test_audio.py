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


def test_load_mono_resamples_and_mixes(tmp_path):
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x40\x00\x00" * 44100)  # links 0,5, rechts 0
    signal = audio.load_mono(path, sr=22050)
    assert signal.dtype.name == "float32"
    assert len(signal) == pytest.approx(22050, abs=50)
    assert float(signal[1000:-1000].mean()) == pytest.approx(0.25, abs=0.01)


def test_load_mono_invalid_raises(tmp_path):
    bad = tmp_path / "kaputt.wav"
    bad.write_bytes(b"kein audio")
    with pytest.raises(RuntimeError, match="kaputt.wav"):
        audio.load_mono(bad)


def test_write_stereo_wav(tmp_path):
    import numpy as np

    left, right = np.full(100, 0.5, dtype=np.float32), np.full(100, -2.0, dtype=np.float32)
    path = audio.write_wav(tmp_path / "out.wav", np.stack([left, right], axis=1), 8000)
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getframerate(), w.getnframes()) == (2, 8000, 100)
        frames = np.frombuffer(w.readframes(1), dtype="<i2")
    assert frames[0] == pytest.approx(16383, abs=1) and frames[1] == -32767  # rechts begrenzt
