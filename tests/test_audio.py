"""Tests for audio duration via ffprobe."""

import wave

import numpy as np
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
    for suffix in (".wav", ".flac", ".ogg", ".opus", ".aiff", ".WAV"):
        f = tmp_path / f"song{suffix}"
        f.write_bytes(b"x")
        assert audio.readable(f, tmp_path / "cache") == f


def test_mp3s_are_decoded_by_ffmpeg_because_libsndfile_gives_up_on_some(tmp_path):
    """libsndfile (mpg123) stopped with "Unspecified internal error" on MP3s with a Lyrics3 tag
    or a damaged frame, 18 of 1738 in the owner's music; ffmpeg reads them (owner, 2026-11-15)."""
    import subprocess

    wav = _tone(tmp_path / "tone.wav", seconds=2.0)
    mp3 = tmp_path / "song.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), str(mp3)], check=True)
    with mp3.open("ab") as f:  # a Lyrics3 v2 tag after the audio, as in the failing songs
        f.write(b"LYRICSBEGININD0000210" + b"000033LYRICS200")
    flac = audio.readable(mp3, tmp_path / "cache")
    assert flac.suffix == ".flac" and audio.duration(flac) == pytest.approx(2.0, abs=0.1)


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


def _peak_frequency(signal, sr: int) -> float:
    import numpy as np

    spectrum = np.abs(np.fft.rfft(signal, n=4 * sr))
    return float(np.fft.rfftfreq(4 * sr, 1 / sr)[int(np.argmax(spectrum))])


def test_clicks_sit_at_the_hits_with_one_pitch_per_group():
    import numpy as np

    sr = 22050
    signal = audio.clicks([(0.5, 0), (1.0, 1), (2.0, 2)], 3 * sr, sr)
    assert len(signal) == 3 * sr
    for t, freq in ((0.5, 700), (1.0, 1400), (2.0, 2800)):
        burst = signal[int(t * sr) : int((t + 0.02) * sr)]
        assert np.sqrt(np.mean(burst**2)) > 0.05
        assert _peak_frequency(burst, sr) == pytest.approx(freq, abs=60)
    quiet = np.concatenate([signal[: int(0.45 * sr)], signal[int(2.1 * sr) :]])
    assert np.max(np.abs(quiet)) == 0


def test_clicks_past_the_end_or_before_the_start_are_dropped_or_cut():
    sr = 22050
    signal = audio.clicks([(-0.1, 0), (0.995, 1), (5.0, 2)], sr, sr)
    assert len(signal) == sr and signal[int(0.995 * sr) :].any()  # cut at the end, not dropped
    assert not signal[: int(0.9 * sr)].any()


def test_ffprobe_and_ffmpeg_run_with_c_numbers(monkeypatch, tmp_path):
    """Arch's ffprobe 9.0 wrote "245,640000" under a German locale, and the AppImage could not
    read a song's length (owner, 2026-11-15)."""
    import re
    import subprocess
    from pathlib import Path

    seen = {}

    def run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="245.640000\n", stderr="")

    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setattr(audio.subprocess, "run", run)
    assert audio.duration(tmp_path / "song.flac") == 245.64
    assert seen["env"]["LC_ALL"] == "C"
    src = Path(audio.__file__).parent
    direct = [
        f"{path.name}:{n}"
        for path in src.rglob("*.py")
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"subprocess\.run\(\s*\[\s*\"ff(mpeg|probe)\"", line)
    ]
    assert direct == [], "call ffmpeg/ffprobe through audio.media_tool"


def _noise_song(level, seconds=4.0, sr=22050):
    rng = np.random.default_rng(1)
    return (level * rng.standard_normal(int(seconds * sr))).astype(np.float32)


def test_the_click_gain_puts_the_clicks_the_same_distance_above_any_song():
    """Clicks suited Eye of the Tiger but were too loud on a quieter song (owner, 2026-11-15)."""
    sr, times = 22050, [0.5 + 0.25 * k for k in range(12)]
    raw = audio.clicks([(t, 1) for t in times], 4 * sr, sr, seconds=0.06, decay=50.0, peak=1.4)
    for level in (0.3, 0.03):  # a loud song and a quiet one
        song = _noise_song(level)
        gain = audio.click_gain(song, raw, times, sr, over_db=4.0)
        clicks = np.tanh(raw * gain)
        offset = audio.level_at(clicks, times, sr) - audio.level_at(song, times, sr)
        assert offset == pytest.approx(4.0, abs=0.3)
        assert np.abs(clicks).max() < 1.0
    assert audio.click_gain(np.zeros(4 * sr), raw, times, sr, over_db=4.0) == 1.0  # silence
    assert audio.click_gain(_noise_song(0.3), raw, [], sr, over_db=4.0) == 1.0  # no hits
