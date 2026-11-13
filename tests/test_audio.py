"""Tests for audio duration via ffprobe."""

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
        w.writeframes(b"\x00\x40\x00\x00" * 44100)  # left 0.5, right 0
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
    assert frames[0] == pytest.approx(16383, abs=1) and frames[1] == -32767  # right clipped


def test_load_mono_tolerates_trailing_separator_in_channel_count(tmp_path, monkeypatch):
    """Some MP3s (e.g. with side data) make ffprobe print "2," instead of "2"."""
    import subprocess

    import numpy as np

    stereo = np.array([[0.5, 0.0], [0.5, 0.0]], dtype="<f4").tobytes()
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, "2,\n", "")
        if cmd[0] == "ffmpeg":
            return subprocess.CompletedProcess(cmd, 0, stereo, b"")
        return real_run(cmd, **kw)

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    signal = audio.load_mono(tmp_path / "song.mp3")
    assert signal.tolist() == pytest.approx([0.25, 0.25])


def test_tags_reads_title_and_artist(tmp_path):
    import subprocess

    src = write_wav(tmp_path / "a.wav", 0.2)
    flac = tmp_path / "a.flac"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(src),
            "-metadata",
            "title=Song",
            "-metadata",
            "ARTIST=Band",
            str(flac),
        ],
        check=True,
    )
    assert audio.tags(flac) == {"title": "Song", "artist": "Band"}
    assert audio.tags(src) == {}


def test_tags_of_unreadable_file_are_empty(tmp_path):
    bad = tmp_path / "kaputt.mp3"
    bad.write_bytes(b"x")
    assert audio.tags(bad) == {}


def _tone(path, seconds=0.5, sr=8000):
    import numpy as np

    t = np.arange(int(seconds * sr)) / sr
    audio.write_wav(path, 0.3 * np.sin(2 * np.pi * 440 * t), sr)
    return path


def test_formats_every_model_reads_are_passed_on_unchanged(tmp_path):
    for suffix in (".wav", ".flac", ".mp3", ".ogg", ".opus", ".aiff", ".WAV"):
        f = tmp_path / f"song{suffix}"
        f.write_bytes(b"x")
        assert audio.readable(f, tmp_path / "cache") == f


def test_other_formats_are_decoded_once_to_flac(tmp_path):
    import subprocess

    wav = _tone(tmp_path / "tone.wav")
    m4a = tmp_path / "song.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-c:a", "aac", str(m4a)], check=True)
    flac = audio.readable(m4a, tmp_path / "cache")
    assert flac.suffix == ".flac" and flac.parent == tmp_path / "cache" / "_decoded"
    assert audio.duration(flac) == pytest.approx(audio.duration(m4a), abs=0.05)
    mtime = flac.stat().st_mtime_ns
    assert audio.readable(m4a, tmp_path / "cache") == flac and flac.stat().st_mtime_ns == mtime


def test_undecodable_input_raises(tmp_path):
    bad = tmp_path / "song.m4a"
    bad.write_bytes(b"not audio")
    with pytest.raises(RuntimeError, match="decode"):
        audio.readable(bad, tmp_path / "cache")
