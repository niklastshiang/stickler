"""Stickler adapter: ADTOF (Frame_RNN) transcribes kick, snare, toms, hi-hat and cymbals.

Official API `adtof_pytorch.transcribe_to_midi` with the model's default thresholds
(FRAME_RNN_THRESHOLDS). The output already uses GM pitches 35/38/47/42/49.
ADTOF is trained on real songs (mixes), so it also handles the original mix.

The model runs once (`return_activations=True`); peak picking and the MIDI export then follow
`transcribe_to_midi` step by step, so drums.mid is unchanged. The frame activations are also
saved (activations.npz: float32 [frames, 5] at FPS frames per second, in LABELS_5 order), so
the harness can fuse several inputs and tune thresholds without running the model again.
"""

import tempfile
from pathlib import Path

import numpy as np
from adtof_pytorch import (
    FRAME_RNN_THRESHOLDS,
    LABELS_5,
    PeakPicker,
    activations_to_pretty_midi,
    transcribe_to_midi,
)
from stickler_adapter import run, torch_device, write_drum_midi

VERSION = "adtof-pytorch@85c192e/Frame_RNN"
FPS = 100  # transcribe_to_midi's default


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pred = transcribe_to_midi(
            audio, Path(tmp) / "unused.mid", device=torch_device(device), return_activations=True
        )
    picked = PeakPicker(thresholds=FRAME_RNN_THRESHOLDS, fps=FPS).pick(pred, labels=LABELS_5)
    midi = activations_to_pretty_midi(picked[0], velocity=100, note_duration=0.1, is_drum=True)
    notes = [
        (n.start, n.pitch, n.velocity)
        for inst in midi.instruments
        if inst.is_drum
        for n in inst.notes
    ]
    write_drum_midi(out_dir / "drums.mid", notes)
    np.savez_compressed(
        out_dir / "activations.npz",
        activations=pred[0].astype(np.float32),
        fps=FPS,
        labels=np.asarray(LABELS_5),
    )


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="adtof", version=VERSION)
