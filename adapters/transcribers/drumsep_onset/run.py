"""Stickler adapter: DrumSep splits a drum stem into six drums; an onset detector per drum
turns them into hits.

DrumSep (MDX23C, aufr33 and jarredou) runs through python-audio-separator's official API with
its default parameters. Each stem's onset-strength envelope comes from librosa at 100 frames per
second; the peaks are picked in onsets.py on a scale shared by all six stems. The envelopes are
also saved (activations.npz, as ADTOF's), so thresholds can be tuned without running the model
again. DrumSep expects drums only, so a separator comes first ([tool.stickler] input = "stem").
"""

import tempfile
from importlib.metadata import version
from pathlib import Path

import librosa
import numpy as np
import soundfile
from audio_separator.separator import Separator
from common import MODEL, WEIGHTS
from onsets import STEM_PITCHES, activations, transcribe
from stickler_adapter import run, write_drum_midi

FPS = 100


def _envelope(path: Path) -> np.ndarray:
    samples, sr = soundfile.read(path, always_2d=True)
    mono = samples.mean(axis=1).astype(np.float32)
    return librosa.onset.onset_strength(y=mono, sr=sr, hop_length=round(sr / FPS))


def _stem_files(outputs: list[str], folder: Path) -> dict[str, Path]:
    found = {}
    for stem in STEM_PITCHES:
        names = [f for f in outputs if f"({stem})" in Path(f).name.lower()]
        if len(names) != 1:
            raise RuntimeError(f"Stem {stem} is missing or ambiguous in {outputs}")
        found[stem] = folder / Path(names[0]).name
    return found


def transcribe_stem(audio: Path, out_dir: Path, device: str) -> None:
    # Device: audio-separator uses the GPU by itself if torch sees one (ROCm/CUDA environment);
    # the CPU environment has none. The harness picks the environment matching `device`.
    with tempfile.TemporaryDirectory() as tmp:
        separator = Separator(model_file_dir=str(WEIGHTS), output_dir=tmp, output_format="WAV")
        separator.load_model(model_filename=MODEL)
        files = _stem_files(separator.separate(str(audio)), Path(tmp))
        envelopes = {stem: _envelope(path) for stem, path in files.items()}
    length = max(len(e) for e in envelopes.values())
    envelopes = {s: np.pad(e, (0, length - len(e))) for s, e in envelopes.items()}
    write_drum_midi(out_dir / "drums.mid", transcribe(envelopes, FPS))
    act, labels = activations(envelopes)
    np.savez_compressed(out_dir / "activations.npz", activations=act, fps=FPS, labels=labels)


if __name__ == "__main__":
    run(
        transcribe_stem,
        stage="transcribers",
        adapter="drumsep_onset",
        version=f"audio-separator {version('audio-separator')}/{MODEL}+onsets",
    )
