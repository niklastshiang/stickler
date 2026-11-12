"""Tests für die Benchmark-Matrix: Ausführung, Cache, Fehler, Bewertung."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from stickler import adapters, runner
from stickler.classes import load_schemes

FIXTURES = Path(__file__).parent / "fixtures" / "adapters"
SCHEMES = load_schemes(Path(__file__).resolve().parents[1] / "config" / "classes.yaml")


@dataclass(frozen=True)
class FakeTrack:
    id: str
    mix: Path
    drums: Path | None
    notes: tuple = ((0.5, 36), (1.0, 38), (1.5, 42))

    def reference_notes(self):
        return list(self.notes)


@pytest.fixture
def setup(tmp_path):
    mix = tmp_path / "song_mix.wav"
    mix.write_bytes(b"mix")
    stem = tmp_path / "song_drums.wav"
    stem.write_bytes(b"stem")
    return {
        "tracks": {"fake": [FakeTrack("song", mix, stem)]},
        "registry": adapters.discover(FIXTURES),
        "cache": tmp_path / "cache",
    }


def run(setup, separators=("none",), transcribers=("dummy",), execute=True, **kw):
    return runner.run_matrix(
        setup["tracks"],
        list(separators),
        list(transcribers),
        setup["registry"],
        setup["cache"],
        device="cpu",
        execute=execute,
        **kw,
    )


def test_none_separator_uses_mix(setup):
    (rec,) = run(setup)
    assert rec.ok
    assert rec.stem == setup["tracks"]["fake"][0].mix
    assert rec.midi is not None and rec.midi.exists()


def test_oracle_separator_uses_dataset_stem(setup):
    (rec,) = run(setup, separators=["oracle"])
    assert rec.stem == setup["tracks"]["fake"][0].drums


def test_oracle_without_stem_is_an_error(setup, tmp_path):
    setup["tracks"] = {"fake": [FakeTrack("nostem", tmp_path / "song_mix.wav", None)]}
    (rec,) = run(setup, separators=["oracle"])
    assert not rec.ok
    assert "oracle" in rec.error


def test_adapter_separator_then_transcriber(setup):
    (rec,) = run(setup, separators=["copysep"])
    assert rec.ok, rec.error
    assert rec.stem.read_bytes() == b"mix"
    assert rec.separator_meta["adapter"] == "copysep"
    assert rec.transcriber_meta["adapter"] == "dummy"


def test_second_run_hits_cache(setup, monkeypatch):
    run(setup, separators=["copysep"])
    monkeypatch.setattr(
        adapters, "run_adapter", lambda *a, **k: pytest.fail("Cache-Treffer erwartet")
    )
    (rec,) = run(setup, separators=["copysep"])
    assert rec.ok


def test_changed_input_invalidates_cache(setup):
    first = run(setup)[0].midi
    setup["tracks"]["fake"][0].mix.write_bytes(b"neuer mix")
    assert run(setup)[0].midi != first


def test_execute_false_reports_missing(setup):
    (rec,) = run(setup, execute=False)
    assert not rec.ok
    assert "nicht berechnet" in rec.error


def test_failing_transcriber_is_recorded_and_retried(setup):
    (rec,) = run(setup, transcribers=["broken"])
    assert not rec.ok
    assert "Modell explodiert" in rec.error


def test_unknown_adapter_raises(setup):
    with pytest.raises(ValueError, match="gibtsnicht"):
        run(setup, transcribers=["gibtsnicht"])


def test_progress_and_cancel(setup):
    import threading

    seen = []
    cancel = threading.Event()

    def progress(done, total, label):
        seen.append((done, total, label))
        cancel.set()

    recs = run(setup, separators=["none", "oracle"], progress=progress, cancel=cancel)
    assert len(recs) == 1  # nach dem ersten Job abgebrochen
    assert seen == [(1, 2, "fake/song: none → dummy")]


def test_score_records_rows(setup):
    recs = run(setup, transcribers=["dummy", "broken"])
    rows = runner.score_records(recs, setup["tracks"], SCHEMES)
    ok = [r for r in rows if r["transcriber"] == "dummy" and r["scheme"] == "5"]
    by_class = {r["class"]: r for r in ok}
    assert by_class["KD"]["tp"] == 1 and by_class["SD"]["tp"] == 1
    assert by_class["HH"]["fn"] == 1
    assert by_class["micro"]["f1"] == pytest.approx(0.8)
    assert by_class["macro"]["f1"] == pytest.approx(2 / 3)
    broken = [r for r in rows if r["transcriber"] == "broken"]
    assert broken and all(r["error"] for r in broken)


def test_rocm_env_changes_cache_key(setup):
    spec = setup["registry"]["dummy"]
    audio = setup["tracks"]["fake"][0].mix
    without_env = runner.cache_dir_for(setup["cache"], spec, audio, "gpu")
    py = spec.path / adapters.ROCM_ENV / "bin" / "python"
    py.parent.mkdir(parents=True)
    try:
        py.write_text("", encoding="utf-8")
        assert runner.cache_dir_for(setup["cache"], spec, audio, "gpu") != without_env
        assert runner.cache_dir_for(setup["cache"], spec, audio, "cpu") == runner.cache_dir_for(
            setup["cache"], spec, audio, "cpu"
        )
    finally:
        import shutil

        shutil.rmtree(spec.path / adapters.ROCM_ENV)


def test_stem_only_transcriber_skips_mix(setup):
    recs = run(setup, separators=["none", "oracle"], transcribers=["stemonly", "dummy"])
    combos = {(r.separator, r.transcriber) for r in recs}
    assert combos == {("none", "dummy"), ("oracle", "dummy"), ("oracle", "stemonly")}


def test_timeout_is_passed_to_adapter(setup, monkeypatch):
    seen = {}

    def fake_run_adapter(spec, audio, out_dir, device="auto", timeout=None):
        seen["timeout"] = timeout
        return adapters.AdapterResult(False, None, None, "x")

    monkeypatch.setattr(adapters, "run_adapter", fake_run_adapter)
    run(setup, timeout=42.0)
    assert seen["timeout"] == 42.0


def test_timeout_per_stage(setup, monkeypatch):
    seen = {}

    def fake_run_adapter(spec, audio, out_dir, device="auto", timeout=None):
        seen[spec.stage] = timeout
        if spec.stage == "separators":
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "drums.wav").write_bytes(b"x")
            return adapters.AdapterResult(True, out_dir / "drums.wav", {}, None)
        return adapters.AdapterResult(False, None, None, "x")

    monkeypatch.setattr(adapters, "run_adapter", fake_run_adapter)
    run(setup, separators=["copysep"], timeout={"separators": 1800.0, "transcribers": 300.0})
    assert seen == {"separators": 1800.0, "transcribers": 300.0}
