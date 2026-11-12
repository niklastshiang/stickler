"""Stickler adapter: ADTOF (Frame_RNN) transcribes kick, snare, toms, hi-hat and cymbals.

Official API `adtof_pytorch.transcribe_to_midi` with the model's default thresholds
(FRAME_RNN_THRESHOLDS). The output already uses GM pitches 35/38/47/42/49.
ADTOF is trained on real songs (mixes), so it also handles the original mix.
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
