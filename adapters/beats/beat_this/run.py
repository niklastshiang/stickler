"""Stickler adapter: Beat This! finds beats and downbeats (seconds) without DBN postprocessing.

Official API `beat_this.inference.Audio2Beats` with the default checkpoint `final0` and the
minimal postprocessor (the authors' recommendation; the DBN needs madmom and assumes a fixed
time signature). Audio is loaded with soundfile (MP3/FLAC/WAV) and mixed down to mono.
Output: beats.json = {"beats": [...], "downbeats": [...]}.
"""

import json
from pathlib import Path

import soundfile as sf
from beat_this.inference import Audio2Beats
from common import CHECKPOINT
from stickler_adapter import run, torch_device

VERSION = f"beat-this==1.1.0/{CHECKPOINT}/minimal"


def track_beats(audio: Path, out_dir: Path, device: str) -> None:
    signal, sr = sf.read(audio, dtype="float32", always_2d=True)
    beats, downbeats = Audio2Beats(CHECKPOINT, device=torch_device(device))(signal.mean(1), sr)
    data = {
        "beats": [round(float(t), 4) for t in beats],
        "downbeats": [round(float(t), 4) for t in downbeats],
    }
    (out_dir / "beats.json").write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    run(track_beats, stage="beats", adapter="beat_this", version=VERSION)
