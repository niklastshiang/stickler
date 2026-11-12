"""Stickler-Adapter: ADTOF (Frame_RNN) transkribiert Kick, Snare, Toms, Hi-Hat und Becken.

Offizielle API `adtof_pytorch.transcribe_to_midi` mit den Standard-Schwellen des Modells
(FRAME_RNN_THRESHOLDS). Ausgabe sind bereits GM-Pitches 35/38/47/42/49.
ADTOF ist auf echten Songs (Mix) trainiert, verträgt also auch den Original-Mix.
"""

import tempfile
from pathlib import Path

import pretty_midi
from adtof_pytorch import transcribe_to_midi
from stickler_adapter import run, torch_device, write_drum_midi

VERSION = "adtof-pytorch@85c192e/Frame_RNN"


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        midi_path = transcribe_to_midi(audio, Path(tmp) / "out.mid", device=torch_device(device))
        midi = pretty_midi.PrettyMIDI(str(midi_path))
    notes = [
        (n.start, n.pitch, n.velocity)
        for inst in midi.instruments
        if inst.is_drum
        for n in inst.notes
    ]
    write_drum_midi(out_dir / "drums.mid", notes)


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="adtof", version=VERSION)
