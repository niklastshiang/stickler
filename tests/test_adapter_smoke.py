"""Smoke-Tests mit echten Modell-Adaptern (langsam): `uv run pytest -m adapters`.

Voraussetzung: `uv run stickler setup --adapter <id>`. Das Testaudio wird synthetisch erzeugt,
damit kein Audio im Repository liegt.
"""

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from stickler import adapters
from stickler.midi import read_drum_notes

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.adapters


def synth_drums(path: Path, seconds: float = 10.0, sr: int = 44100) -> None:
    """Viertel-Kicks (abfallender Sinus) und Snares (Rauschen) auf 2 und 4 bei 120 BPM."""
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
    assert notes, "keine Noten erkannt"
    assert all(35 <= pitch <= 81 for _, pitch in notes), "Pitches außerhalb des GM-Drum-Bereichs"
    assert json.loads((tmp_path / adapter_id / "meta.json").read_text())["device"] == "cpu"


@pytest.mark.parametrize("adapter_id", ["demucs", "roformer"])
def test_separator_produces_drum_stem(adapter_id, drum_clip, tmp_path):
    spec = adapters.discover(ROOT / "adapters")[adapter_id]
    result = adapters.run_adapter(spec, drum_clip, tmp_path / adapter_id, device="cpu")
    assert result.ok, result.error
    with wave.open(str(result.output)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds == pytest.approx(10.0, abs=0.1)
