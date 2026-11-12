"""Tests for the public API."""

import pytest

from stickler import api, runner
from stickler.datasets import mdb


def test_fetch_dataset_mdb_uses_data_subfolder(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(mdb, "fetch", lambda target: seen.append(target) or 23)
    assert api.fetch_dataset("mdb", tmp_path) == 23
    assert seen == [tmp_path / "mdb"]


def test_fetch_unknown_dataset_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
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
    # rocm without an adapter given: only adapters with [tool.stickler.rocm]
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
    assert names[0] == "gpu" and "dataset mdb" in names


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
    """Synthetic song: 2 s silence, then 64 bars of groove at 120 BPM (128 s, above the
    2-minute minimum), as MIDI and WAV."""
    import mido
    import numpy as np

    from stickler import audio

    sr, offset = 22050, 2.0
    notes = []
    for bar in range(64):
        t0 = bar * 2.0
        notes += [(t0, 36), (t0 + 1.0, 36), (t0 + 0.5, 38), (t0 + 1.5, 38)]
        notes += [(t0 + k * 0.25, 42) for k in range(8)]
    sig = np.zeros(int((offset + 130) * sr), dtype=np.float32)
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
    beats = [offset + k * 0.5 for k in range(257)]  # Beat This! reports beats up to the end
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
        return ad.AdapterResult(True, wav, {}, None)  # stem = the mix itself

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
    assert any(b <= 2.0 for a, b in track.excluded)  # silence before the song is excluded


def test_align_songs_missing_score_is_reported(tmp_path, monkeypatch):
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "x.yaml").write_text('title: "X"\naudio: "/a.mp3"\n', encoding="utf-8")
    (report,) = api.align_songs(references_dir=refs, data_dir=tmp_path, cache_dir=tmp_path)
    assert not report.passed and "score.mid" in report.error


def test_align_songs_unknown_song_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        api.align_songs("nix", references_dir=tmp_path, data_dir=tmp_path, cache_dir=tmp_path)


def test_load_tracks_own_requires_alignment(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "REFERENCES_DIR", tmp_path)
    with pytest.raises(ValueError, match="stickler align"):
        api.load_tracks("own", tmp_path)


def test_results_dir_depends_on_config(tmp_path):
    assert api.results_dir_for(api.CONFIG) == api.RESULTS_DIR
    assert api.results_dir_for(tmp_path / "own.yaml") == api.RESULTS_DIR / "own"


def _write_summary(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.csv").write_text(
        "dataset,separator,transcriber,scheme,tracks,errors,micro_f1,macro_f1,f1_KD\n"
        "mdb,none,adtof,5,3,0,0.5,0.4,0.7\n",
        encoding="utf-8",
    )


def test_write_report_reads_default_and_subfolders(tmp_path):
    _write_summary(tmp_path)
    _write_summary(tmp_path / "own_songs")
    path = api.write_report(results_dir=tmp_path)
    assert path == tmp_path / "report.html"
    html = path.read_text(encoding="utf-8")
    assert "Config: default" in html and "Config: own_songs" in html


def test_write_report_for_given_configs(tmp_path):
    _write_summary(tmp_path)
    _write_summary(tmp_path / "own_songs")
    html = api.write_report([api.CONFIG, tmp_path / "own_songs.yaml"], tmp_path).read_text()
    assert "Config: default" in html and "Config: own_songs" in html
    only = api.write_report([tmp_path / "own_songs.yaml"], tmp_path).read_text()
    assert "Config: default" not in only


def test_write_report_without_results_still_writes_a_page(tmp_path):
    html = api.write_report(results_dir=tmp_path / "empty").read_text()
    assert "No results" in html


def _fake_pipeline(tmp_path, monkeypatch):
    """Cached adapter results for a fake song: stem, drum MIDI and beats."""
    import json

    import mido

    from stickler import adapters as ad

    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    stem = tmp_path / "drums.wav"
    stem.write_bytes(b"stem")
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    for k in range(8):
        track.append(
            mido.Message(
                "note_on",
                channel=9,
                note=36 if k % 2 == 0 else 38,
                velocity=90,
                time=0 if k == 0 else 480,
            )
        )
    midi_path = tmp_path / "drums.mid"
    mid.save(midi_path)
    beats = tmp_path / "beats.json"
    beats.write_text(json.dumps({"beats": [k * 0.5 for k in range(9)], "downbeats": [0.0, 2.0]}))
    calls = []

    def fake(spec, audio_in, cache, device, execute, timeout=None):
        calls.append((spec.id, audio_in))
        out = {"separators": stem, "transcribers": midi_path, "beats": beats}[spec.stage]
        return ad.AdapterResult(True, out, {}, None)

    registry = {
        "demucs": ad.AdapterSpec("demucs", "separators", tmp_path),
        "adtof": ad.AdapterSpec("adtof", "transcribers", tmp_path),
        "beat_this": ad.AdapterSpec("beat_this", "beats", tmp_path),
    }
    monkeypatch.setattr(runner, "cached_or_run", fake)
    monkeypatch.setattr(api.adapters, "discover", lambda root: registry)
    return audio, stem, calls


def test_transcribe_song_runs_the_pipeline(tmp_path, monkeypatch):
    audio, stem, calls = _fake_pipeline(tmp_path, monkeypatch)
    t = api.transcribe_song(audio, "demucs+adtof", cache_dir=tmp_path)
    assert calls == [("demucs", audio), ("adtof", stem), ("beat_this", audio)]
    assert t.stem == stem and len(t.hits) == 8 and t.hits[1] == (0.5, 38, 90)
    assert t.beats[:2] == [0.0, 0.5] and t.downbeats == [0.0, 2.0]


def test_transcribe_song_without_separation_uses_the_mix(tmp_path, monkeypatch):
    audio, _, calls = _fake_pipeline(tmp_path, monkeypatch)
    t = api.transcribe_song(audio, "none+adtof", cache_dir=tmp_path)
    assert calls[0] == ("adtof", audio) and t.stem == audio


@pytest.mark.parametrize("pipeline", ["adtof", "demucs+nix", "nix+adtof", "adtof+demucs"])
def test_transcribe_song_rejects_bad_pipelines(tmp_path, monkeypatch, pipeline):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="pipeline"):
        api.transcribe_song(audio, pipeline, cache_dir=tmp_path)


def test_notate_writes_musicxml_and_reports_missing_musescore(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(api.musescore, "find", lambda: None)
    result = api.notate(audio, cache_dir=tmp_path, results_dir=tmp_path / "res")
    assert result.musicxml == tmp_path / "res" / "notation" / "song.musicxml"
    assert "<score-partwise" in result.musicxml.read_text()
    assert result.pdf is None and "MuseScore" in result.pdf_error


def test_notate_exports_pdf_when_musescore_is_there(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(api.musescore, "find", lambda: ["mscore"])
    monkeypatch.setattr(api.musescore, "export_pdf", lambda xml, pdf, cmd: pdf)
    result = api.notate(audio, tmp_path / "out.musicxml", cache_dir=tmp_path, title="T")
    assert result.pdf == tmp_path / "out.pdf" and result.pdf_error is None


def test_notate_keeps_musicxml_when_pdf_export_fails(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(api.musescore, "find", lambda: ["mscore"])

    def boom(xml, pdf, cmd):
        raise RuntimeError("MuseScore: crashed")

    monkeypatch.setattr(api.musescore, "export_pdf", boom)
    result = api.notate(audio, tmp_path / "out.musicxml", cache_dir=tmp_path)
    assert result.musicxml.exists() and result.pdf is None and "crashed" in result.pdf_error


@pytest.mark.parametrize("suffix", [".wav", ".flac"])
def test_export_drum_track(tmp_path, suffix):
    from test_audio import write_wav

    stem = write_wav(tmp_path / "drums.wav", 0.5)
    out = api.export_drum_track(stem, tmp_path / f"export{suffix}")
    assert out.exists() and out.suffix == suffix
    assert abs(__import__("stickler").audio.duration(out) - 0.5) < 0.05


def test_export_drum_track_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError, match="format"):
        api.export_drum_track(tmp_path / "drums.wav", tmp_path / "x.doc")
