"""Tests für die öffentliche API."""

import pytest

from stickler import api, runner
from stickler.datasets import mdb


def test_fetch_dataset_mdb_uses_data_subfolder(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(mdb, "fetch", lambda target: seen.append(target) or 23)
    assert api.fetch_dataset("mdb", tmp_path) == 23
    assert seen == [tmp_path / "mdb"]


def test_fetch_unknown_dataset_raises(tmp_path):
    with pytest.raises(ValueError, match="unbekannt"):
        api.fetch_dataset("foo", tmp_path)


def test_setup_adapters_selects_one_or_all(monkeypatch, tmp_path):
    from stickler import adapters

    for name in ("a", "b"):
        d = tmp_path / "transcribers" / name
        d.mkdir(parents=True)
        (d / "run.py").write_text("", encoding="utf-8")
    done = []
    monkeypatch.setattr(
        adapters, "setup_adapter", lambda spec, device="cpu": done.append((spec.id, device))
    )
    assert api.setup_adapters("a", adapters_root=tmp_path) == ["a"]
    assert api.setup_adapters(None, adapters_root=tmp_path) == ["a", "b"]
    assert done == [("a", "cpu"), ("a", "cpu"), ("b", "cpu")]
    # rocm ohne Angabe: nur Adapter mit [tool.stickler.rocm]
    (tmp_path / "transcribers" / "b" / "pyproject.toml").write_text(
        '[tool.stickler.rocm]\nindex = "i"\nreplace = []\npackages = []\n', encoding="utf-8"
    )
    (tmp_path / "transcribers" / "a" / "pyproject.toml").write_text("", encoding="utf-8")
    assert api.setup_adapters(None, device="rocm", adapters_root=tmp_path) == ["b"]
    with pytest.raises(ValueError, match="zzz"):
        api.setup_adapters("zzz", adapters_root=tmp_path)


def _bench(tmp_path, transcribers="[dummy]"):
    cfg = tmp_path / "bench.yaml"
    cfg.write_text(
        f"datasets: [mdb]\nseparators: [none]\ntranscribers: {transcribers}\n"
        'device: cpu\nschemes: ["5"]\n',
        encoding="utf-8",
    )
    return cfg


def _fake_mdb(monkeypatch, tmp_path):
    from pathlib import Path

    from stickler.datasets import mdb as mdb_mod

    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"x")
    ann = tmp_path / "t_subclass.txt"
    ann.write_text("0.5 \t KD \n1.0 \t SD \n", encoding="utf-8")
    track = mdb_mod.Track(id="t", mix=mix, drums=None, annotation=ann)
    monkeypatch.setattr(mdb_mod, "tracks", lambda target: [track])
    return Path(__file__).parent / "fixtures" / "adapters"


def test_load_config_validates(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("datasets: [mdb]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="separators"):
        api.load_benchmark_config(cfg)


def test_run_and_evaluate_benchmark(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    seen = []
    records = api.run_benchmark(cfg, progress=lambda d, t, label: seen.append(label), **kw)
    assert [r.ok for r in records] == [True]
    assert seen == ["mdb/t: none → dummy"]
    summary = api.evaluate_benchmark(cfg, results_dir=tmp_path / "results", **kw)
    assert summary[0]["micro_f1"] == 1.0
    assert (tmp_path / "results" / "metrics.csv").exists()
    assert (tmp_path / "results" / "summary.csv").exists()


def test_run_benchmark_device_override(monkeypatch, tmp_path):
    from stickler import runner

    fixtures = _fake_mdb(monkeypatch, tmp_path)
    captured = {}

    def fake_matrix(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(runner, "run_matrix", fake_matrix)
    api.run_benchmark(
        _bench(tmp_path),
        data_dir=tmp_path,
        cache_dir=tmp_path,
        adapters_root=fixtures,
        device="gpu",
    )
    assert captured["device"] == "gpu"


def test_missing_dataset_raises(monkeypatch, tmp_path):
    from stickler.datasets import mdb as mdb_mod

    monkeypatch.setattr(mdb_mod, "tracks", lambda target: [])
    with pytest.raises(ValueError, match="stickler fetch mdb"):
        api.run_benchmark(_bench(tmp_path), data_dir=tmp_path, cache_dir=tmp_path)


def test_run_doctor_returns_checks(tmp_path):
    names = [c.name for c in api.run_doctor(adapters_root=tmp_path, data_dir=tmp_path)]
    assert names[0] == "gpu" and "datensatz mdb" in names


def test_config_timeout_optional(tmp_path):
    cfg = _bench(tmp_path)
    assert api.load_benchmark_config(cfg).timeout is None
    cfg.write_text(cfg.read_text() + "timeout: 1800\n", encoding="utf-8")
    assert api.load_benchmark_config(cfg).timeout == 1800.0


def test_config_timeout_per_stage(tmp_path):
    cfg = _bench(tmp_path)
    cfg.write_text(
        cfg.read_text() + "timeout:\n  separators: 1800\n  transcribers: 300\n", encoding="utf-8"
    )
    assert api.load_benchmark_config(cfg).timeout == {"separators": 1800.0, "transcribers": 300.0}


def test_config_timeout_relative(tmp_path):
    cfg = _bench(tmp_path)
    cfg.write_text(
        cfg.read_text() + "timeout:\n  separators: 1800\n  transcribers: {factor: 10, min: 120}\n",
        encoding="utf-8",
    )
    assert api.load_benchmark_config(cfg).timeout == {
        "separators": 1800.0,
        "transcribers": runner.RelativeLimit(factor=10.0, minimum=120.0),
    }


def test_config_timeout_relative_needs_factor(tmp_path):
    cfg = _bench(tmp_path)
    cfg.write_text(cfg.read_text() + "timeout:\n  transcribers: {min: 120}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="factor"):
        api.load_benchmark_config(cfg)


def _synth_song(tmp_path):
    """Synthetischer Song: 2 s Stille, dann 16 Takte Groove bei 120 BPM, als MIDI und WAV."""
    import mido
    import numpy as np

    from stickler import audio

    sr, offset = 22050, 2.0
    notes = []
    for bar in range(16):
        t0 = bar * 2.0
        notes += [(t0, 36), (t0 + 1.0, 36), (t0 + 0.5, 38), (t0 + 1.5, 38)]
        notes += [(t0 + k * 0.25, 42) for k in range(8)]
    sig = np.zeros(int((offset + 34) * sr), dtype=np.float32)
    rng = np.random.default_rng(0)
    t = np.arange(int(0.15 * sr)) / sr
    sounds = {
        36: 0.9 * np.exp(-t * 30) * np.sin(2 * np.pi * 60 * t),
        38: 0.6 * np.exp(-t * 40) * np.sin(2 * np.pi * 900 * t),
        42: 0.3 * np.exp(-t * 90) * np.diff(rng.standard_normal(len(t) + 1)),
    }
    for time, pitch in notes:
        start = int((offset + time) * sr)
        sig[start : start + len(t)] += sounds[pitch]
    wav = audio.write_wav(tmp_path / "song.wav", sig, sr)

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    now = 0
    for time, pitch in sorted(notes):
        tick = round(time * 960)
        track.append(mido.Message("note_on", channel=9, note=pitch, velocity=90, time=tick - now))
        now = tick
    beats = [offset + k * 0.5 for k in range(65)]  # Beat This! meldet Beats bis zum Ende
    return wav, mid, notes, beats


def test_align_songs_end_to_end(tmp_path, monkeypatch):
    import json

    from stickler import adapters as ad
    from stickler.datasets import own

    wav, mid, notes, beats = _synth_song(tmp_path)
    refs, data = tmp_path / "references", tmp_path / "data"
    refs.mkdir()
    (refs / "synth.yaml").write_text(f'title: "Synth"\naudio: "{wav}"\n', encoding="utf-8")
    (data / "own" / "synth").mkdir(parents=True)
    mid.save(data / "own" / "synth" / "score.mid")

    def fake_cached_or_run(spec, audio_in, cache, device, execute, timeout=None):
        if spec.stage == "beats":
            out = tmp_path / "beats.json"
            out.write_text(json.dumps({"beats": beats, "downbeats": beats[::4]}))
            return ad.AdapterResult(True, out, {}, None)
        return ad.AdapterResult(True, wav, {}, None)  # Stem = der Mix selbst

    monkeypatch.setattr(runner, "cached_or_run", fake_cached_or_run)
    registry = {
        "demucs": ad.AdapterSpec("demucs", "separators", tmp_path),
        "beat_this": ad.AdapterSpec("beat_this", "beats", tmp_path),
    }
    monkeypatch.setattr(ad, "discover", lambda root: registry)
    (report,) = api.align_songs(references_dir=refs, data_dir=data, cache_dir=tmp_path)
    assert report.passed, report.reasons
    assert report.click is not None and report.click.exists()
    (track,) = own.tracks(refs, data)
    got = track.reference_notes()
    assert len(got) == len(notes)
    assert all(abs(g[0] - (n[0] + 2.0)) < 0.03 for g, n in zip(got, sorted(notes), strict=True))
    assert any(b <= 2.0 for a, b in track.excluded)  # Stille vor dem Song ist ausgeklammert


def test_align_songs_missing_score_is_reported(tmp_path, monkeypatch):
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "x.yaml").write_text('title: "X"\naudio: "/a.mp3"\n', encoding="utf-8")
    (report,) = api.align_songs(references_dir=refs, data_dir=tmp_path, cache_dir=tmp_path)
    assert not report.passed and "score.mid" in report.error


def test_align_songs_unknown_song_raises(tmp_path):
    with pytest.raises(ValueError, match="unbekannt"):
        api.align_songs("nix", references_dir=tmp_path, data_dir=tmp_path, cache_dir=tmp_path)


def test_load_tracks_own_requires_alignment(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "REFERENCES_DIR", tmp_path)
    with pytest.raises(ValueError, match="stickler align"):
        api.load_tracks("own", tmp_path)
