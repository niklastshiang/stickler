"""Tests for the public API."""

from pathlib import Path

import pytest

from stickler import api, runner
from stickler.datasets import mdb


def test_fetch_dataset_mdb_uses_data_subfolder(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(mdb, "fetch", lambda target: seen.append(target) or 23)
    assert api.fetch_dataset("mdb", tmp_path) == 23
    assert seen == [tmp_path / "mdb"]


def test_enst_is_prepared_locally_and_loaded(monkeypatch, tmp_path):
    from stickler.datasets import enst

    seen = []
    monkeypatch.setattr(enst, "fetch", lambda target: seen.append(target) or 64)
    assert api.fetch_dataset("enst", tmp_path) == 64 and seen == [tmp_path / "enst"]
    with pytest.raises(ValueError, match="stickler fetch enst"):
        api.load_tracks("enst", tmp_path)
    monkeypatch.setattr(enst, "tracks", lambda target: ["t"])
    assert api.load_tracks("enst", tmp_path) == ["t"]


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
        adapters,
        "setup_environment",
        lambda spec, device="cpu", cancel=None: done.append((spec.id, device)) or [],
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


def test_error_breakdown_of_a_pipeline(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)  # reference KD 0.5, SD 1.0; dummy echoes it
    cfg = _bench(tmp_path)
    cfg.write_text(cfg.read_text() + "combos:\n  kick:\n    none+dummy: [KD]\n", encoding="utf-8")
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    pooled = api.error_breakdown(
        cfg, ["none+dummy", "combo+kick"], results_dir=tmp_path / "results", **kw
    )
    by = {(r["pipeline"], r["class"]): r for r in pooled}
    assert by[("none+dummy", "SD")]["tp"] == 1 and by[("none+dummy", "SD")]["missed"] == 0
    assert by[("combo+kick", "SD")]["missed"] == 1 and by[("combo+kick", "KD")]["tp"] == 1
    rows = (tmp_path / "results" / "errors.csv").read_text().splitlines()
    assert rows[0].startswith("dataset,track,pipeline,class,tp,missed")
    assert len(rows) == 1 + 2 * 5  # one row per pipeline and class of the 5-class scheme


def test_error_breakdown_needs_computed_results(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)  # nothing run, nothing cached
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    with pytest.raises(RuntimeError, match="stickler run"):
        api.error_breakdown(_bench(tmp_path), ["none+dummy"], results_dir=tmp_path, **kw)


def test_error_breakdown_rejects_an_unknown_pipeline(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    with pytest.raises(ValueError, match="none\\+nix"):
        api.error_breakdown(_bench(tmp_path), ["none+nix"], results_dir=tmp_path, **kw)


def test_evaluate_scores_combos(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    cfg.write_text(
        cfg.read_text() + "combos:\n  quality:\n    none+dummy: [KD, SD]\n", encoding="utf-8"
    )
    assert api.load_benchmark_config(cfg).combos == {"quality": {"none+dummy": ["KD", "SD"]}}
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    summary = api.evaluate_benchmark(cfg, results_dir=tmp_path / "results", **kw)
    combo = [r for r in summary if r["separator"] == "combo"]
    assert [r["transcriber"] for r in combo] == ["quality"] and combo[0]["micro_f1"] == 1.0


def test_fusions_are_scored_and_tuned_from_cached_activations(monkeypatch, tmp_path):
    import numpy as np

    from stickler import adapters, fusion
    from stickler.runner import Record

    fixtures = _fake_mdb(monkeypatch, tmp_path)  # reference: KD at 0.5 s, SD at 1.0 s
    act = np.zeros((200, 5), dtype=np.float32)
    act[50, 0] = act[100, 1] = 0.9
    entry = tmp_path / "adtof-entry"
    entry.mkdir()
    np.savez(entry / "activations.npz", activations=act, fps=100, labels=[35, 38, 47, 42, 49])
    import mido

    mido.MidiFile().save(str(entry / "drums.mid"))
    rec = Record("mdb", "t", "none", "adtof", None, entry / "drums.mid", {}, {}, None)
    monkeypatch.setattr(api, "run_benchmark", lambda *a, **kw: [rec])
    monkeypatch.setattr(adapters, "discover", lambda root: {})
    classes = {c: {"weights": [1], "threshold": 0.3} for c in ("KD", "SD", "TT", "HH", "CY")}
    cfg = _bench(tmp_path)
    cfg.write_text(
        cfg.read_text() + "fusions:\n  f:\n    inputs: [none]\n    classes: " + str(classes) + "\n",
        encoding="utf-8",
    )
    summary = api.evaluate_benchmark(
        cfg,
        results_dir=tmp_path / "r",
        data_dir=tmp_path,
        cache_dir=tmp_path,
        adapters_root=fixtures,
    )
    (row,) = [r for r in summary if r["separator"] == "fusion"]
    assert row["transcriber"] == "f" and row["micro_f1"] == 1.0
    report = api.tune_fusion([cfg], ["none"], data_dir=tmp_path, step=1.0, thresholds=[0.3, 0.95])
    assert report.tuned["KD"].f1 == 1.0 and report.tuned["KD"].threshold == 0.3
    assert report.default["KD"].threshold == fusion.ADTOF_THRESHOLDS["KD"]
    assert "fusions:" in report.yaml(
        "tuned"
    ) and "KD: {weights: [1.0], threshold: 0.3}" in report.yaml("tuned")


def test_grid_pipelines_get_beats_and_are_scored(monkeypatch, tmp_path):
    from stickler import grid

    fixtures = _fake_mdb(monkeypatch, tmp_path)  # reference KD 0.5, SD 1.0; dummy echoes it
    cfg = _bench(tmp_path)
    cfg.write_text(
        cfg.read_text()
        + "grid: [none+dummy]\nconsensus: {similarity: 0.7, add: 0.6, remove: 0.1}\n"
        + "simplify: true\n",
        encoding="utf-8",
    )
    loaded = api.load_benchmark_config(cfg)
    assert loaded.grid == ["none+dummy"]
    assert loaded.consensus == grid.Consensus(0.7, 0.6, 0.1) and loaded.simplify
    asked = []

    def fake_beats(tracks, registry, cache_dir, device, execute):
        asked.append(execute)
        return {("mdb", "t"): grid.BeatGrid([0.0, 0.5, 1.0, 1.5], [0.0])}

    monkeypatch.setattr(api, "_track_beats", fake_beats)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    summary = api.evaluate_benchmark(cfg, results_dir=tmp_path / "results", **kw)
    (row,) = [r for r in summary if r["transcriber"] == "dummy@grid"]
    assert row["micro_f1"] == 1.0 and asked == [True, False]
    assert [r["transcriber"] for r in summary if r["transcriber"] == "dummy@rep"]
    assert [r["transcriber"] for r in summary if r["transcriber"] == "dummy@simple"]


def test_votes_are_scored_and_usable_in_combos(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    cfg.write_text(
        cfg.read_text()
        + "votes:\n  v:\n    pipelines: [none+dummy, none+dummy]\n    min_agree: 2\n"
        + "combos:\n  c:\n    vote+v: [KD, SD]\n",
        encoding="utf-8",
    )
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    summary = api.evaluate_benchmark(cfg, results_dir=tmp_path / "results", **kw)
    by = {(r["separator"], r["transcriber"]): r["micro_f1"] for r in summary}
    assert by[("vote", "v")] == 1.0 and by[("combo", "c")] == 1.0


def test_cache_entries_are_the_results_a_config_uses(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    (rec,) = api.run_benchmark(cfg, **kw)
    (tmp_path / "cache" / "other" / "unrelated").mkdir(parents=True)
    entries = api.cache_entries(cfg, **kw)
    assert entries == [str(rec.midi.parent.relative_to(tmp_path / "cache"))]


def test_only_restricts_run_and_eval_to_the_given_tracks(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)  # one track "t"
    cfg = _bench(tmp_path)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    assert api.run_benchmark(cfg, only={"other"}, **kw) == []
    assert [r.track for r in api.run_benchmark(cfg, only={"t"}, **kw)] == ["t"]
    assert api.evaluate_benchmark(cfg, only={"other"}, results_dir=tmp_path / "r", **kw) == []


def test_missing_tracks_are_those_with_uncomputed_jobs(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    assert api.missing_tracks(cfg, **kw) == ["t"]
    api.run_benchmark(cfg, **kw)
    assert api.missing_tracks(cfg, **kw) == []


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


def test_write_report_shows_corrected_scores_when_there_are_any(tmp_path):
    _write_summary(tmp_path / "own")
    (tmp_path / "own" / "corrected.csv").write_text(
        "pipeline,class,measured,corrected,low,high,bound_low,bound_high,n_ref,n_est,unclear,"
        "r_ref,r_est\nnone+adtof,macro,0.77,0.82,0.79,0.85,0.8,0.84,50,40,6,,\n",
        encoding="utf-8",
    )
    html = api.write_report(results_dir=tmp_path).read_text(encoding="utf-8")
    assert "judged by ear" in html and "0.820" in html


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

    def fake(spec, audio_in, cache, device, execute, timeout=None, cancel=None):
        calls.append((spec.id, audio_in))
        out = {"separators": stem, "transcribers": midi_path, "beats": beats}[spec.stage]
        return ad.AdapterResult(True, out, {}, None)

    registry = {
        "demucs": ad.AdapterSpec("demucs", "separators", tmp_path),
        "adtof": ad.AdapterSpec("adtof", "transcribers", tmp_path),
        "muscriptor_m": ad.AdapterSpec("muscriptor_m", "transcribers", tmp_path),
        "beat_this": ad.AdapterSpec("beat_this", "beats", tmp_path),
    }
    monkeypatch.setattr(runner, "cached_or_run", fake)
    monkeypatch.setattr(api.adapters, "discover", lambda root: registry)
    monkeypatch.setattr(api.adapters, "missing_setup", lambda spec, device="auto": [])
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
    assert calls[0] == ("adtof", audio) and t.stem is None  # no drum track without separation


def test_fast_mode_is_adtof_on_the_mix(tmp_path, monkeypatch):
    audio, _, calls = _fake_pipeline(tmp_path, monkeypatch)
    t = api.transcribe_song(audio, cache_dir=tmp_path)
    assert calls == [("adtof", audio), ("beat_this", audio)]
    assert t.pipeline == "fast" and len(t.hits) == 8


def test_quality_mode_takes_each_class_from_its_model(tmp_path, monkeypatch):
    audio, stem, calls = _fake_pipeline(tmp_path, monkeypatch)
    t = api.transcribe_song(audio, mode="quality", cache_dir=tmp_path)
    assert calls == [
        ("demucs", audio),
        ("muscriptor_m", stem),
        ("adtof", audio),
        ("beat_this", audio),
    ]
    # the fake MIDI has only kick and snare: they come from MuScriptor, ADTOF adds no hi-hat
    assert t.pipeline == "quality" and len(t.hits) == 8 and t.stem == stem


def test_drum_track_in_fast_mode_runs_a_separator(tmp_path, monkeypatch):
    audio, stem, calls = _fake_pipeline(tmp_path, monkeypatch)
    t = api.transcribe_song(audio, cache_dir=tmp_path, drums=True)
    assert ("demucs", audio) in calls and t.stem == stem


def _trace(steps):
    return [(s.id, s.adapter, s.state, s.index, s.total) for s in steps]


def test_fast_mode_reports_its_steps_in_order(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    steps = []
    api.transcribe_song(audio, cache_dir=tmp_path, progress=steps.append)
    assert _trace(steps) == [
        ("transcribe", "adtof", "started", 1, 2),
        ("transcribe", "adtof", "done", 1, 2),
        ("beats", "beat_this", "started", 2, 2),
        ("beats", "beat_this", "done", 2, 2),
    ]
    assert not any(s.cached for s in steps)


def test_notate_announces_every_step_before_the_first_starts(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(api.musescore, "find", lambda: ["mscore"])
    monkeypatch.setattr(api.musescore, "export_pdf", lambda xml, pdf, cmd: pdf)
    steps = []
    api.notate(
        audio,
        tmp_path / "o.musicxml",
        pipeline="demucs+adtof",
        cache_dir=tmp_path,
        progress=steps.append,
    )
    done = [(s.id, s.adapter, s.index) for s in steps if s.state == "done"]
    assert done == [
        ("separate", "demucs", 1),
        ("transcribe", "adtof", 2),
        ("beats", "beat_this", 3),
        ("engrave", None, 4),
        ("pdf", None, 5),
    ]
    assert {s.total for s in steps} == {5}
    assert [s.state for s in steps] == ["started", "done"] * 5


def test_quality_mode_and_drum_track_steps(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    steps = []
    api.transcribe_song(audio, mode="quality", cache_dir=tmp_path, progress=steps.append)
    assert [(s.id, s.adapter) for s in steps if s.state == "done"] == [
        ("separate", "demucs"),
        ("transcribe", "muscriptor_m"),
        ("transcribe", "adtof"),
        ("beats", "beat_this"),
    ]
    steps.clear()
    api.transcribe_song(audio, cache_dir=tmp_path, drums=True, progress=steps.append)
    assert [(s.id, s.adapter) for s in steps if s.state == "done"] == [
        ("transcribe", "adtof"),
        ("separate", "demucs"),
        ("beats", "beat_this"),
    ]


def test_cached_steps_are_marked_and_no_pdf_step_without_pdf(tmp_path, monkeypatch):
    from stickler import adapters as ad

    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    computed = runner.cached_or_run

    def cached(*a, **kw):
        r = computed(*a, **kw)
        return ad.AdapterResult(r.ok, r.output, r.meta, r.error, cached=True)

    monkeypatch.setattr(runner, "cached_or_run", cached)
    steps = []
    api.notate(audio, tmp_path / "o.musicxml", pdf=False, cache_dir=tmp_path, progress=steps.append)
    done = [(s.id, s.cached) for s in steps if s.state == "done"]
    assert done == [("transcribe", True), ("beats", True), ("engrave", False)]


def test_notate_returns_the_bar_map(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)  # two equal bars of 2 s
    result = api.notate(audio, tmp_path / "o.musicxml", pdf=False, cache_dir=tmp_path)
    assert result.bars == [api.BarTime(0.0, 2.0, 1), api.BarTime(2.0, 4.0, 1)]
    plain = api.notate(audio, tmp_path / "p.musicxml", pdf=False, repeats=False, cache_dir=tmp_path)
    assert [b.written for b in plain.bars] == [1, 2]


def test_corrections_change_the_bars_but_never_the_hits(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)  # 8 beats of 0.5 s, 4/4
    target = tmp_path / "o.musicxml"
    plain = api.notate(audio, target, pdf=False, cache_dir=tmp_path)
    fixed = api.Corrections(beats_per_bar=2, repeats=False)
    corrected = api.notate(audio, target, pdf=False, cache_dir=tmp_path, corrections=fixed)
    assert [(b.start, b.end, b.written) for b in corrected.bars] == [
        (0.0, 1.0, 1),
        (1.0, 2.0, 2),
        (2.0, 3.0, 3),
        (3.0, 4.0, 4),
    ]
    assert "<beats>2</beats>" in target.read_text()
    assert corrected.transcription == plain.transcription


def test_corrections_take_over_simplify_and_repeats(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    target = tmp_path / "o.musicxml"
    by_parameter = api.notate(audio, target, pdf=False, repeats=False, cache_dir=tmp_path)
    folded = api.notate(
        audio, target, pdf=False, repeats=False, cache_dir=tmp_path, corrections=api.Corrections()
    )
    assert [b.written for b in by_parameter.bars] == [1, 2]
    assert [b.written for b in folded.bars] == [1, 1]


def test_a_correction_on_a_cached_song_starts_no_adapter(tmp_path, monkeypatch):
    """Fast mode with both results in the cache: every correction re-engraves only."""
    import json

    import mido

    from stickler import adapters as ad

    root = tmp_path / "adapters"
    specs = [
        _plain_adapter(root, "transcribers", "adtof"),
        _plain_adapter(root, "beats", "beat_this"),
    ]
    for spec in specs:
        ad.setup_adapter(spec)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    adtof_dir = runner.cache_dir_for(tmp_path / "cache", specs[0], audio)
    beats_dir = runner.cache_dir_for(tmp_path / "cache", specs[1], audio)
    for folder in (adtof_dir, beats_dir):
        folder.mkdir(parents=True)
        (folder / "meta.json").write_text("{}")
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.extend(
        mido.Message("note_on", channel=9, note=36, velocity=90, time=480) for _ in range(8)
    )
    mid.save(adtof_dir / "drums.mid")
    beats = [k * 0.5 for k in range(17)]
    (beats_dir / "beats.json").write_text(json.dumps({"beats": beats, "downbeats": beats[:-1:4]}))
    monkeypatch.setattr(ad, "run_adapter", lambda *a, **kw: pytest.fail("an adapter was started"))
    kw = {"pdf": False, "cache_dir": tmp_path / "cache", "adapters_root": root}
    for c in (
        api.Corrections(tempo="half"),
        api.Corrections(tempo="double"),
        api.Corrections(beats_per_bar=3),
        api.Corrections(first_downbeat=2),
        api.Corrections(simplify=False, repeats=False),
    ):
        result = api.notate(audio, tmp_path / "o.musicxml", corrections=c, **kw)
        assert len(result.transcription.hits) == 8


def test_runner_says_when_a_result_comes_from_the_cache(tmp_path):
    from stickler import adapters as ad

    fixtures = Path(__file__).parent / "fixtures" / "adapters"
    spec = ad.discover(fixtures)["dummy"]
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"x")
    first = runner.cached_or_run(spec, audio, tmp_path / "cache", "cpu", True)
    again = runner.cached_or_run(spec, audio, tmp_path / "cache", "cpu", True)
    assert first.ok and not first.cached
    assert again.ok and again.cached


def test_a_token_set_beforehand_starts_nothing(tmp_path, monkeypatch):
    audio, _, calls = _fake_pipeline(tmp_path, monkeypatch)
    token, steps = api.CancelToken(), []
    token.cancel()
    with pytest.raises(api.Cancelled):
        api.notate(audio, tmp_path / "o.musicxml", cache_dir=tmp_path, cancel=token)
    with pytest.raises(api.Cancelled):
        api.transcribe_song(audio, cache_dir=tmp_path, progress=steps.append, cancel=token)
    assert calls == [] and steps == []
    assert not (tmp_path / "o.musicxml").exists()


def test_cancel_between_steps_stops_before_the_next_one(tmp_path, monkeypatch):
    audio, _, calls = _fake_pipeline(tmp_path, monkeypatch)
    token, steps = api.CancelToken(), []

    def on_step(step):
        steps.append(step)
        if step.id == "transcribe" and step.state == "done":
            token.cancel()

    target = tmp_path / "o.musicxml"
    with pytest.raises(api.Cancelled):
        api.notate(audio, target, cache_dir=tmp_path, progress=on_step, cancel=token)
    assert [s.id for s in steps] == ["transcribe", "transcribe"]
    assert [c[0] for c in calls] == ["adtof"]
    assert not target.exists()


def test_cancelling_a_running_model_leaves_no_cache_entry(tmp_path):
    """Sleepy hangs; the token is set once its process runs. The call raises within a second,
    the step is never `done`, nothing is cached, and the next run starts the model again."""
    import time

    from stickler import adapters as ad

    fixtures = Path(__file__).parent / "fixtures" / "adapters"
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    spec = ad.discover(fixtures)["sleepy"]
    ad.setup_adapter(spec)  # an analysis needs its models set up
    pid_file = runner.cache_dir_for(tmp_path / "cache", spec, audio) / "pid"
    kw = {"cache_dir": tmp_path / "cache", "adapters_root": fixtures}

    def cancelled_run() -> tuple[int, float, list]:
        token, seen, steps = api.CancelToken(), {}, []
        _cancel_when_running(pid_file, token, seen)
        with pytest.raises(api.Cancelled):
            api.transcribe_song(audio, "none+sleepy", progress=steps.append, cancel=token, **kw)
        return seen["pid"], time.monotonic() - seen["at"], steps

    first, took, steps = cancelled_run()
    assert took < 1
    assert [(s.id, s.state) for s in steps] == [("transcribe", "started")]
    assert not runner.cached_or_run(spec, audio, tmp_path / "cache", "cpu", False).ok
    second, _, _ = cancelled_run()
    assert second != first  # the model ran again instead of a half result being taken


def _cancel_when_running(pid_file, token, seen):
    import threading
    import time

    def watch():
        while not (pid_file.exists() and pid_file.read_text()):
            time.sleep(0.01)
        seen["pid"] = int(pid_file.read_text())
        seen["at"] = time.monotonic()
        token.cancel()

    threading.Thread(target=watch, daemon=True).start()


def _plain_adapter(root, stage, name, weights=False):
    """An adapter without dependencies (set up offline in milliseconds)."""
    from stickler import adapters as ad

    d = root / stage / name
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0"\nrequires-python = ">=3.12,<3.13"\n',
        encoding="utf-8",
    )
    if weights:
        (d / "setup.py").write_text("", encoding="utf-8")
    return ad.AdapterSpec(id=name, stage=stage, path=d)


def test_mode_ready_lists_the_adapters_not_set_up(tmp_path):
    from stickler import adapters as ad

    root = tmp_path / "adapters"
    adtof = _plain_adapter(root, "transcribers", "adtof")
    beat_this = _plain_adapter(root, "beats", "beat_this", weights=True)
    assert api.mode_ready("fast", adapters_root=root) == ["adtof", "beat_this"]
    ad.setup_adapter(adtof)
    assert api.mode_ready("fast", adapters_root=root) == ["beat_this"]
    ad.setup_adapter(beat_this)
    assert api.mode_ready("fast", adapters_root=root) == []


def test_setup_adapters_reports_environment_and_weights_steps(tmp_path):
    root = tmp_path / "adapters"
    _plain_adapter(root, "transcribers", "adtof")
    _plain_adapter(root, "beats", "beat_this", weights=True)
    steps = []
    assert api.setup_adapters(None, adapters_root=root, progress=steps.append) == [
        "adtof",
        "beat_this",
    ]
    assert _trace(steps) == [
        ("environment:adtof", "adtof", "started", 1, 3),
        ("environment:adtof", "adtof", "done", 1, 3),
        ("environment:beat_this", "beat_this", "started", 2, 3),
        ("environment:beat_this", "beat_this", "done", 2, 3),
        ("weights:beat_this", "beat_this", "started", 3, 3),
        ("weights:beat_this", "beat_this", "done", 3, 3),
    ]
    assert api.mode_ready("fast", adapters_root=root) == []


def test_cancelled_setup_stops_before_the_next_step(tmp_path):
    root = tmp_path / "adapters"
    _plain_adapter(root, "transcribers", "adtof")
    _plain_adapter(root, "beats", "beat_this", weights=True)
    token, steps = api.CancelToken(), []

    def on_step(step):
        steps.append(step)
        if step.state == "done":
            token.cancel()

    with pytest.raises(api.Cancelled):
        api.setup_adapters(None, adapters_root=root, progress=on_step, cancel=token)
    assert [s.id for s in steps] == ["environment:adtof", "environment:adtof"]
    assert api.mode_ready("fast", adapters_root=root) == ["beat_this"]


def test_setup_adapters_rejects_an_unknown_device_before_any_step(tmp_path):
    root = tmp_path / "adapters"
    _plain_adapter(root, "transcribers", "adtof")
    steps = []
    with pytest.raises(ValueError, match="tpu"):
        api.setup_adapters("adtof", device="tpu", adapters_root=root, progress=steps.append)
    assert steps == []


def test_an_analysis_names_the_models_not_set_up_before_starting_any(tmp_path, monkeypatch):
    audio, _, calls = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(
        api.adapters,
        "missing_setup",
        lambda spec, device="auto": ["weights"] if spec.id == "beat_this" else [],
    )
    steps = []
    with pytest.raises(api.SetupMissing) as err:
        api.transcribe_song(audio, cache_dir=tmp_path, progress=steps.append)
    assert err.value.adapters == ["beat_this"]
    assert "stickler setup --adapter beat_this" in str(err.value)
    with pytest.raises(api.SetupMissing):
        api.notate(audio, tmp_path / "o.musicxml", cache_dir=tmp_path)
    assert calls == [] and steps == []


def test_unknown_mode_raises(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="mode"):
        api.transcribe_song(audio, mode="turbo", cache_dir=tmp_path)


@pytest.mark.parametrize("pipeline", ["adtof", "demucs+nix", "nix+adtof", "adtof+demucs"])
def test_transcribe_song_rejects_bad_pipelines(tmp_path, monkeypatch, pipeline):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="pipeline"):
        api.transcribe_song(audio, pipeline, cache_dir=tmp_path)


def test_notate_writes_musicxml_and_reports_missing_musescore(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(api.musescore, "find", lambda: None)
    result = api.notate(audio, cache_dir=tmp_path)
    assert result.musicxml == audio.with_suffix(".musicxml")  # next to the song
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


def test_notate_takes_title_and_artist_from_tags(tmp_path, monkeypatch):
    audio_path, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(api.musescore, "find", lambda: None)
    monkeypatch.setattr(api.audio, "tags", lambda p: {"title": "Tagged", "artist": "Band"})
    xml = api.notate(audio_path, tmp_path / "o.musicxml", cache_dir=tmp_path).musicxml.read_text()
    assert "<work-title>Tagged</work-title>" in xml and ">Band</creator>" in xml
    xml = api.notate(
        audio_path, tmp_path / "o.musicxml", cache_dir=tmp_path, title="T", artist="A"
    ).musicxml.read_text()
    assert "<work-title>T</work-title>" in xml and ">A</creator>" in xml


def test_notate_folds_repeated_bars_by_default(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)  # two equal bars
    monkeypatch.setattr(api.musescore, "find", lambda: None)
    xml = api.notate(audio, cache_dir=tmp_path).musicxml.read_text()
    assert xml.count("<measure ") == 1 and 'times="2"' in xml
    exact = api.notate(audio, cache_dir=tmp_path, simplify=False, repeats=False)
    xml = exact.musicxml.read_text()
    assert xml.count("<measure ") == 2 and "<repeat" not in xml


def test_config_skip_combinations(tmp_path):
    cfg = _bench(tmp_path)
    cfg.write_text(cfg.read_text() + 'skip: ["none+muscriptor_m"]\n', encoding="utf-8")
    assert api.load_benchmark_config(cfg).skip == {("none", "muscriptor_m")}
    cfg.write_text(cfg.read_text() + 'skip: ["kaputt"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="skip"):
        api.load_benchmark_config(cfg)


def test_run_remote_reads_secrets_and_stops_the_pod(tmp_path, monkeypatch):
    from stickler import remote

    token_file = tmp_path / "token"
    token_file.write_text("tok\n", encoding="utf-8")
    monkeypatch.setattr(api.doctor, "HF_TOKEN_FILE", token_file)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("RUNPOD_API_KEY", "key")
    monkeypatch.setattr(remote, "sync_plan", lambda cfg, **kw: remote.SyncPlan(code=[]))
    seen = {}

    def fake_run_remote(host, config, adapter_ids, plan, *, project_root, hf_token, stop, wipe):
        seen.update(
            host=host,
            config=config,
            ids=adapter_ids,
            token=hf_token,
            wipe=wipe,
            cache=plan.cache,
            only=plan.only,
        )
        stop()

    monkeypatch.setattr(remote, "run_remote", fake_run_remote)
    monkeypatch.setattr(remote, "stop_pod", lambda pod, key: seen.update(stopped=(pod, key)))
    monkeypatch.setattr(api, "cache_entries", lambda config, only=None: ["adtof/abc"])
    monkeypatch.setattr(api, "missing_tracks", lambda config: ["song_a"])
    api.run_remote(
        "root@203.0.113.7",
        22077,
        api.PROJECT_ROOT / "config" / "own.yaml",
        pod_id="pod1",
        wipe=True,
    )
    assert seen["wipe"] is True and seen["cache"] == ["adtof/abc"] and seen["only"] == ["song_a"]
    assert seen["host"] == remote.Host("root@203.0.113.7", 22077)
    assert seen["config"] == "config/own.yaml" and seen["token"] == "tok"
    assert seen["stopped"] == ("pod1", "key") and "demucs" in seen["ids"]


def test_run_remote_with_nothing_missing_only_stops_the_pod(tmp_path, monkeypatch):
    from stickler import remote

    monkeypatch.setenv("RUNPOD_API_KEY", "key")
    monkeypatch.setattr(api, "missing_tracks", lambda config: [])
    monkeypatch.setattr(remote, "run_remote", lambda *a, **k: pytest.fail("nothing to upload"))
    stopped = []
    monkeypatch.setattr(remote, "stop_pod", lambda pod, key: stopped.append(pod))
    done = api.run_remote("root@h", 22, api.PROJECT_ROOT / "config" / "own.yaml", pod_id="p1")
    assert done == [] and stopped == ["p1"]


def test_plan_is_restricted_to_the_missing_tracks():
    from stickler import remote

    plan = remote.SyncPlan(
        code=["x"],
        data_files=["data/own/a/aligned.json", "data/own/b/aligned.json"],
        audio=[("/m/a.flac", "data/own/a"), ("/m/b.flac", "data/own/b")],
    )
    small = api.restrict_plan(plan, ["b"])
    assert small.data_files == ["data/own/b/aligned.json"]
    assert small.audio == [("/m/b.flac", "data/own/b")] and small.only == ["b"]


def test_run_remote_with_pod_id_needs_an_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.setattr(api, "RUNPOD_KEY_FILE", tmp_path / "missing")
    with pytest.raises(ValueError, match="RUNPOD_API_KEY"):
        api.run_remote("root@h", 22, api.CONFIG, pod_id="pod1")


@pytest.mark.parametrize(
    "content", ["abc123\n", "export RUNPOD_API_KEY=abc123\n", "RUNPOD_API_KEY='abc123'"]
)
def test_runpod_key_file_is_parsed_without_a_shell(tmp_path, monkeypatch, content):
    key_file = tmp_path / "runpod.env"
    key_file.write_text(content, encoding="utf-8")
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.setattr(api, "RUNPOD_KEY_FILE", key_file)
    assert api.runpod_api_key() == "abc123"


def test_runpod_key_from_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "from-env")
    monkeypatch.setattr(api, "RUNPOD_KEY_FILE", tmp_path / "missing")
    assert api.runpod_api_key() == "from-env"


def test_migrate_cache_collects_inputs(tmp_path, monkeypatch):
    from stickler import cachemigration
    from stickler.datasets import mdb as mdb_mod
    from stickler.datasets import own as own_mod

    mix, stem, song = tmp_path / "m.wav", tmp_path / "d.wav", tmp_path / "s.mp3"
    monkeypatch.setattr(mdb_mod, "tracks", lambda d: [mdb_mod.Track("t", mix, stem, tmp_path)])
    monkeypatch.setattr(
        own_mod, "songs", lambda r, d: [own_mod.Song("s", "S", song, tmp_path / "own" / "s")]
    )
    from stickler.datasets import enst as enst_mod

    e_mix, e_wet = tmp_path / "e.wav", tmp_path / "w.wav"
    monkeypatch.setattr(
        enst_mod, "tracks", lambda target: [enst_mod.Track("d1", e_mix, e_wet, tmp_path / "a.txt")]
    )
    seen = {}

    def fake_migrate(cache, registry, inputs, *, dry_run, previous_digests=None):
        seen.update(inputs=inputs, dry_run=dry_run, previous=previous_digests)
        return cachemigration.Report(moved=2)

    monkeypatch.setattr(cachemigration, "migrate", fake_migrate)
    report = api.migrate_cache(dry_run=True, cache_dir=tmp_path, data_dir=tmp_path)
    assert report.moved == 2
    assert seen == {
        "inputs": [mix, stem, e_mix, e_wet, song],  # ENST was missing until 2026-11-13
        "dry_run": True,
        "previous": None,
    }
    snapshot = tmp_path / "digests.json"
    snapshot.write_text('{"adtof": "abc"}', encoding="utf-8")
    api.migrate_cache(cache_dir=tmp_path, data_dir=tmp_path, rekey_from=snapshot)
    assert seen["previous"] == {"adtof": "abc"}


def test_save_digests_writes_every_adapter(tmp_path):
    out = tmp_path / "d.json"
    api.save_digests(out)
    import json

    assert {"adtof", "demucs"} <= json.loads(out.read_text()).keys()


def _own_song(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from test_audio import write_wav

    mix = write_wav(tmp_path / "song.wav", 6.0)
    song = SimpleNamespace(id="song", mix=mix)
    monkeypatch.setattr(api, "load_tracks", lambda name, data_dir: [song])
    return song


def test_listening_snippet_from_the_cached_drum_stem(monkeypatch, tmp_path):
    from test_audio import write_wav

    from stickler import adapters as ad

    song = _own_song(monkeypatch, tmp_path)
    stem = write_wav(tmp_path / "drums.wav", 6.0)
    asked = []

    def cached(spec, audio_in, cache, device, execute, timeout=None):
        asked.append((spec.id, audio_in, execute))
        return ad.AdapterResult(True, stem, {}, None)

    monkeypatch.setattr(api.runner, "cached_or_run", cached)
    out = api.listening_snippet("song", 3.0, tmp_path / "spot.wav", cache_dir=tmp_path)
    assert out.exists() and asked == [("demucs", song.mix, False)]
    loop = api.listening_snippet("song", 3.0, tmp_path / "l.wav", cache_dir=tmp_path, loop=True)
    seconds = api.listen.LOOP_BEFORE + api.listen.LOOP_AFTER
    assert api.audio.duration(loop) == pytest.approx(seconds, abs=0.01)


def test_listening_snippet_never_runs_a_model(monkeypatch, tmp_path):
    from stickler import adapters as ad

    _own_song(monkeypatch, tmp_path)
    monkeypatch.setattr(
        api.runner, "cached_or_run", lambda *a, **k: ad.AdapterResult(False, None, {}, "missing")
    )
    with pytest.raises(RuntimeError, match="stickler run"):
        api.listening_snippet("song", 3.0, tmp_path / "spot.wav", cache_dir=tmp_path)
    with pytest.raises(ValueError, match="nope"):
        api.listening_snippet("nope", 3.0, tmp_path / "spot.wav", cache_dir=tmp_path)


def test_listening_sample_is_drawn_once_and_kept(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)  # reference KD 0.5, SD 1.0
    cfg = _bench(tmp_path)
    cfg.write_text(cfg.read_text() + "combos:\n  kick:\n    none+dummy: [KD]\n", encoding="utf-8")
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    where = tmp_path / "listening"
    sample = api.draw_listening_sample(cfg, ["combo+kick"], listening_dir=where, **kw)
    assert [(s.song, s.time, s.cls, s.side) for s in sample] == [("t", 1.0, "SD", "ref")]
    assert api.load_listening_sample(where) == sample
    with pytest.raises(RuntimeError, match="already drawn"):
        api.draw_listening_sample(cfg, ["combo+kick"], listening_dir=where, **kw)


def _listening_setup(monkeypatch, tmp_path, n_spots=2):
    from test_audio import write_wav

    from stickler import adapters as ad

    _own_song(monkeypatch, tmp_path)
    stem = write_wav(tmp_path / "drums.wav", 6.0)
    monkeypatch.setattr(
        api.runner, "cached_or_run", lambda *a, **k: ad.AdapterResult(True, stem, {}, None)
    )
    where = tmp_path / "listening"
    where.mkdir()
    lines = ["n,song,time,class,side,pipelines"] + [
        f"{k},song,{k}.0,HH,ref,none+adtof" for k in range(1, n_spots + 1)
    ]
    (where / "sample.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"listening_dir": where, "cache_dir": tmp_path}


def test_listening_goes_spot_by_spot_and_resumes(monkeypatch, tmp_path):
    kw = _listening_setup(monkeypatch, tmp_path)
    first = api.next_listening_spot(**kw)
    assert (first.n, first.total) == (1, 2) and first.spot.time == 1.0
    assert first.snippet.exists() and first.loop.exists()
    assert "hi-hat" in first.question and "ref" not in first.question  # blind
    api.record_verdict(1, "yes", listening_dir=kw["listening_dir"])
    assert api.next_listening_spot(**kw).n == 2  # also after a restart: read from the file
    api.record_verdict(2, "unclear", listening_dir=kw["listening_dir"])
    assert api.next_listening_spot(**kw) is None
    assert api.load_verdicts(kw["listening_dir"]) == {1: "yes", 2: "unclear"}


def test_listening_draws_the_sample_on_the_first_start(monkeypatch, tmp_path):
    kw = _listening_setup(monkeypatch, tmp_path)
    (kw["listening_dir"] / "sample.csv").unlink()
    drawn = []

    def draw(**k):
        drawn.append(k["listening_dir"])
        return []

    monkeypatch.setattr(api, "draw_listening_sample", draw)
    assert api.next_listening_spot(**kw) is None and drawn == [kw["listening_dir"]]


def test_a_verdict_must_be_yes_no_or_unclear(tmp_path):
    with pytest.raises(ValueError, match="unclear"):
        api.record_verdict(1, "maybe", listening_dir=tmp_path)


@pytest.mark.parametrize(
    ("loop", "half_speed", "extra"),
    [(False, False, []), (True, False, ["-loop", "0"]), (True, True, ["-loop", "0", "-af"])],
)
def test_play_uses_ffplay_without_a_window(monkeypatch, tmp_path, loop, half_speed, extra):
    started = []
    monkeypatch.setattr(api.subprocess, "Popen", lambda cmd, **kw: started.append(cmd) or "proc")
    assert api.play(tmp_path / "x.wav", loop=loop, half_speed=half_speed) == "proc"
    (cmd,) = started
    assert cmd[0] == "ffplay" and "-nodisp" in cmd and cmd[-1] == str(tmp_path / "x.wav")
    assert all(x in cmd for x in extra) and ("atempo=0.5" in cmd) == half_speed


def test_judging_records_an_event_without_the_answer_and_awards_badges(tmp_path):
    from datetime import datetime

    now = datetime(2026, 11, 14, 20, 0)
    yes, no = tmp_path / "yes", tmp_path / "no"
    banners = api.record_verdict(1, "yes", listening_dir=yes, now=now)
    api.record_verdict(1, "no", listening_dir=no, now=now)
    assert len(banners) == 1 and "first hit" in banners[0]
    events = (yes / "events.csv").read_text(encoding="utf-8")
    assert events == (no / "events.csv").read_text(encoding="utf-8")  # the answer is not in it
    assert "yes" not in events
    assert api.record_verdict(2, "yes", listening_dir=yes, now=now) == []  # nothing new


def test_loops_and_sessions_are_events_too(tmp_path):
    from datetime import datetime, timedelta

    day = datetime(2026, 11, 14, 20, 0)
    (banner,) = api.record_listening_event("replay", listening_dir=tmp_path, now=day)
    assert "second opinion" in banner
    assert api.record_listening_event("session", listening_dir=tmp_path, now=day) == []
    later = day + timedelta(days=1)
    (banner,) = api.record_listening_event("session", listening_dir=tmp_path, now=later)
    assert "comeback tour" in banner
    assert "2 of 11" in api.badge_collection(listening_dir=tmp_path)


def test_encore_counts_the_spots_of_the_drawn_sample(monkeypatch, tmp_path):
    kw = _listening_setup(monkeypatch, tmp_path, n_spots=2)
    where = kw["listening_dir"]
    api.record_verdict(1, "yes", listening_dir=where)
    banners = api.record_verdict(2, "no", listening_dir=where)
    assert any("encore" in b for b in banners)


def test_unknown_listening_event(tmp_path):
    with pytest.raises(ValueError, match="dance"):
        api.record_listening_event("dance", listening_dir=tmp_path)


def test_corrected_scores_only_once_every_spot_is_judged(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)  # reference KD 0.5, SD 1.0
    cfg = _bench(tmp_path)
    cfg.write_text(cfg.read_text() + "combos:\n  kick:\n    none+dummy: [KD]\n", encoding="utf-8")
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    where, out = tmp_path / "listening", tmp_path / "results"
    pipes = ["combo+kick"]
    api.draw_listening_sample(cfg, pipes, listening_dir=where, **kw)  # one spot: the snare
    args = {"listening_dir": where, "results_dir": out, **kw}
    assert api.corrected_scores(cfg, pipes, **args) is None  # no interim results
    api.record_verdict(1, "yes", listening_dir=where)
    rows = api.corrected_scores(cfg, pipes, **args)
    by = {r["class"]: r for r in rows}
    assert by["SD"]["measured"] == by["SD"]["corrected"] == 0.0 and by["SD"]["n_ref"] == 1
    assert by["KD"]["corrected"] == 1.0 and "macro" in by
    assert (out / "corrected.csv").read_text().startswith("pipeline,class,measured,corrected")


def test_eval_of_the_own_songs_adds_the_corrected_scores(monkeypatch, tmp_path):
    cfg = api.BenchmarkConfig(["own"], ["none"], ["adtof"], "cpu", ["5"])
    monkeypatch.setattr(api, "_all_records", lambda *a, **k: (cfg, {}, []))
    called = []
    monkeypatch.setattr(api, "corrected_scores", lambda *a, **k: called.append(k["results_dir"]))
    api.evaluate_benchmark(tmp_path / "own.yaml", results_dir=tmp_path)
    assert called == [tmp_path]


def test_finale_after_the_last_spot(monkeypatch, tmp_path):
    fixtures = _fake_mdb(monkeypatch, tmp_path)
    cfg = _bench(tmp_path)
    cfg.write_text(cfg.read_text() + "combos:\n  kick:\n    none+dummy: [KD]\n", encoding="utf-8")
    kw = {"data_dir": tmp_path, "cache_dir": tmp_path / "cache", "adapters_root": fixtures}
    api.run_benchmark(cfg, **kw)
    where = tmp_path / "listening"
    pipes = ["combo+kick", "none+dummy"]
    api.draw_listening_sample(cfg, pipes, listening_dir=where, **kw)
    args = {"config_path": cfg, "pipelines": pipes, "listening_dir": where}
    args |= {"results_dir": tmp_path / "results", **kw}
    assert api.finale(**args) is None
    api.record_verdict(1, "yes", listening_dir=where)
    text = api.finale(**args)
    assert "SHOWDOWN" in text and "Badges:" in text


@pytest.mark.parametrize("kw", [{"tempo": "triple"}, {"beats_per_bar": 0}, {"first_downbeat": -1}])
def test_impossible_corrections_fail_before_any_model_runs(kw):
    with pytest.raises(ValueError):
        api.Corrections(**kw)


def test_render_hits_writes_one_click_per_hit_as_long_as_the_song(tmp_path):
    import wave

    import numpy as np

    from stickler import audio as audio_mod

    song = audio_mod.write_wav(tmp_path / "song.wav", np.zeros(3 * 44100), 44100)
    hits = [(0.5, 36, 100), (1.0, 38, 90), (1.5, 45, 90), (2.0, 49, 80)]
    t = api.SongTranscription(song, "fast", None, [0.0, 0.5], [0.0], hits)
    dest = api.render_hits(t, tmp_path / "out" / "hits.wav")
    with wave.open(str(dest)) as w:
        assert w.getnchannels() == 1
        assert w.getnframes() / w.getframerate() == pytest.approx(3.0, abs=1e-3)
    clicks = audio_mod.load_mono(dest, sr=api.CLICK_SR)
    groups = [(0.5, 0), (1.0, 1), (1.5, 1), (2.0, 2)]  # kick, snare and tom, cymbal
    expected = np.tanh(audio_mod.clicks(groups, len(clicks), api.CLICK_SR, **api.PLAYBACK_CLICK))
    assert np.allclose(clicks, expected, atol=1e-3)


def test_the_apps_clicks_are_louder_than_the_listening_clicks_and_never_clip(tmp_path):
    """The owner found the first clicks too quiet under a song (2026-11-15): measured, about
    3 dB under Eye of the Tiger where they sounded. Longer and fuller, they stand out."""
    import numpy as np

    from stickler import audio as audio_mod

    song = audio_mod.write_wav(tmp_path / "song.wav", np.zeros(2 * 44100), 44100)
    hits = [(0.5, 38, 100)] + [(1.0 + k * 0.01, 38, 100) for k in range(4)]  # one, then a pile
    t = api.SongTranscription(song, "fast", None, [], [], hits)
    clicks = audio_mod.load_mono(api.render_hits(t, tmp_path / "hits.wav"), sr=api.CLICK_SR)
    plain = audio_mod.clicks([(0.5, 1)], len(clicks), api.CLICK_SR)
    one = slice(int(0.5 * api.CLICK_SR), int(0.6 * api.CLICK_SR))
    energy = np.sqrt((clicks[one] ** 2).sum() / (plain[one] ** 2).sum())
    assert 20 * np.log10(energy) > 6  # at least 6 dB more
    assert np.abs(clicks).max() < 1.0  # piled-up clicks are limited, not clipped


def test_notation_carries_tempo_and_meter_for_the_window(tmp_path, monkeypatch):
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)  # beats every 0.5 s, 4/4
    kw = {"pdf": False, "cache_dir": tmp_path}
    result = api.notate(audio, tmp_path / "o.musicxml", **kw)
    assert (result.tempo, result.meter) == (120, (4, 4))
    fixed = api.Corrections(beats_per_bar=2)
    result = api.notate(audio, tmp_path / "o.musicxml", corrections=fixed, **kw)
    assert result.meter == (2, 4)


def test_notation_says_which_beat_is_the_first_one(tmp_path, monkeypatch):
    """The corrections sidebar shows it as "Beat n" (SPEC.md, module `corrections`)."""
    audio, _, _ = _fake_pipeline(tmp_path, monkeypatch)
    kw = {"pdf": False, "cache_dir": tmp_path}
    assert api.notate(audio, tmp_path / "o.musicxml", **kw).first_downbeat == 1
    moved = api.Corrections(first_downbeat=3)
    assert api.notate(audio, tmp_path / "o.musicxml", corrections=moved, **kw).first_downbeat == 3


def test_song_info_reads_title_artist_and_length(tmp_path):
    import subprocess

    import numpy as np

    from stickler import audio as audio_mod

    plain = audio_mod.write_wav(tmp_path / "Plain Song.wav", np.zeros(44100 * 2), 44100)
    info = api.song_info(plain)
    assert (info.title, info.artist) == ("Plain Song", "")
    assert info.seconds == pytest.approx(2.0, abs=0.05)
    tagged = tmp_path / "tagged.flac"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(plain), "-metadata", "title=Eye of the Tiger"]
        + ["-metadata", "artist=Survivor", str(tagged)],
        check=True,
    )
    info = api.song_info(tagged)
    assert (info.title, info.artist) == ("Eye of the Tiger", "Survivor")


def test_mode_ready_can_include_the_drum_track_separator(tmp_path):
    from stickler import adapters as ad

    root = tmp_path / "adapters"
    for stage, name in (("transcribers", "adtof"), ("beats", "beat_this")):
        ad.setup_adapter(_plain_adapter(root, stage, name))
    _plain_adapter(root, "separators", api.DRUM_TRACK_SEPARATOR)
    assert api.mode_ready("fast", adapters_root=root) == []
    assert api.mode_ready("fast", drums=True, adapters_root=root) == [api.DRUM_TRACK_SEPARATOR]
