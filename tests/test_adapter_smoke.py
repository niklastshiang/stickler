"""Smoke tests with real model adapters (slow): `uv run pytest -m adapters`.

Prerequisite: `uv run stickler setup --adapter <id>`. The test audio is generated synthetically
so that no audio lives in the repository.
"""

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from stickler import adapters
from stickler.datasets import mdb
from stickler.midi import read_drum_notes

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.adapters


def synth_drums(path: Path, seconds: float = 10.0, sr: int = 44100) -> None:
    """Quarter-note kicks (falling sine) and snares (noise) on 2 and 4 at 120 BPM."""
    n = int(seconds * sr)
    samples = [0.0] * n
    seed = 1
    for beat in range(int(seconds * 2)):
        start = int(beat * 0.5 * sr)
        for i in range(int(0.15 * sr)):
            if start + i >= n:
                break
            t = i / sr
            env = math.exp(-t * 30)
            if beat % 2 == 0:
                samples[start + i] += 0.8 * env * math.sin(2 * math.pi * (60 + 80 * env) * t)
            else:
                seed = (seed * 1103515245 + 12345) % 2**31
                samples[start + i] += 0.5 * env * (seed / 2**30 - 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


@pytest.fixture(scope="module")
def drum_clip(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("audio") / "synth_drums.wav"
    synth_drums(path)
    return path


@pytest.mark.parametrize("adapter_id", ["adt_str", "adtof", "muscriptor_s", "muscriptor_m"])
def test_transcriber_produces_midi(adapter_id, drum_clip, tmp_path):
    spec = adapters.discover(ROOT / "adapters")[adapter_id]
    result = adapters.run_adapter(spec, drum_clip, tmp_path / adapter_id, device="cpu")
    assert result.ok, result.error
    notes = read_drum_notes(result.output)
    assert notes, "no notes detected"
    assert all(35 <= pitch <= 81 for _, pitch in notes), "pitches outside the GM drum range"
    assert json.loads((tmp_path / adapter_id / "meta.json").read_text())["device"] == "cpu"


@pytest.fixture(scope="module")
def mdb_clip(tmp_path_factory) -> Path:
    """The first 10 s of the MDB mix `MusicDelta_Punk` (for models that do not recognise
    synthetic drums as music). Needs `stickler fetch mdb`."""
    tracks = {t.id: t for t in mdb.tracks(ROOT / "data" / "mdb")}
    assert "MusicDelta_Punk" in tracks, "MDB missing → uv run stickler fetch mdb"
    path = tmp_path_factory.mktemp("audio") / "punk_10s.wav"
    with wave.open(str(tracks["MusicDelta_Punk"].mix)) as src, wave.open(str(path), "wb") as dst:
        dst.setparams(src.getparams())
        dst.writeframes(src.readframes(10 * src.getframerate()))
    return path


def test_fast_mode_model_finds_kick_and_snare_on_a_real_mix(mdb_clip, tmp_path):
    """Fast mode: ADTOF on the original mix of a real song (MDB Punk), no separation."""
    spec = adapters.discover(ROOT / "adapters")["adtof"]
    result = adapters.run_adapter(spec, mdb_clip, tmp_path / "adtof_mix", device="cpu")
    assert result.ok, result.error
    pitches = {pitch for _, pitch in read_drum_notes(result.output)}
    assert {35, 38} <= pitches, f"kick and snare missing: {sorted(pitches)}"
    assert all(35 <= p <= 81 for p in pitches), "pitches outside the GM drum range"


@pytest.mark.parametrize("adapter_id", ["demucs", "roformer"])
def test_separator_produces_drum_stem(adapter_id, drum_clip, tmp_path):
    spec = adapters.discover(ROOT / "adapters")[adapter_id]
    result = adapters.run_adapter(spec, drum_clip, tmp_path / adapter_id, device="cpu")
    assert result.ok, result.error
    with wave.open(str(result.output)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds == pytest.approx(10.0, abs=0.1)


def test_beat_tracker_finds_120_bpm(drum_clip, tmp_path):
    """The synthetic clip has quarter notes at 120 BPM: beat spacing 0.5 s."""
    spec = adapters.discover(ROOT / "adapters")["beat_this"]
    result = adapters.run_adapter(spec, drum_clip, tmp_path / "beat_this", device="cpu")
    assert result.ok, result.error
    data = json.loads(result.output.read_text())
    gaps = [b - a for a, b in zip(data["beats"], data["beats"][1:], strict=False)]
    assert len(data["beats"]) >= 15
    assert sorted(gaps)[len(gaps) // 2] == pytest.approx(0.5, abs=0.03)
    assert set(data["downbeats"]) <= set(data["beats"])
