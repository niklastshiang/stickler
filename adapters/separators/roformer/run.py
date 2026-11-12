"""Stickler adapter: BS-RoFormer (Band-Split RoFormer, checkpoint "SW") separates the drum stem.

Uses the official Python API of python-audio-separator with its default parameters.
This checkpoint's stem names are lower case ("drums"); the output file with "(drums)" in its
name is chosen, regardless of case.
"""

import tempfile
from importlib.metadata import version
from pathlib import Path

import soundfile
from audio_separator.separator import Separator
from common import MODEL, WEIGHTS
from stickler_adapter import run


def separate(audio: Path, out_dir: Path, device: str) -> None:
    # Device: audio-separator uses the GPU by itself if torch sees one (ROCm/CUDA environment);
    # the CPU environment has none. The harness picks the environment matching `device`.
    with tempfile.TemporaryDirectory() as tmp:
        separator = Separator(
            model_file_dir=str(WEIGHTS),
            output_dir=tmp,
            output_format="WAV",
            output_single_stem="drums",
        )
        separator.load_model(model_filename=MODEL)
        outputs = separator.separate(str(audio))
        drums = [f for f in outputs if "(drums)" in Path(f).name.lower()]
        if len(drums) != 1:
            raise RuntimeError(f"Drum stem is ambiguous in {outputs}")
        samples, sample_rate = soundfile.read(Path(tmp) / Path(drums[0]).name, always_2d=True)
    soundfile.write(out_dir / "drums.wav", samples, sample_rate, subtype="PCM_24")


if __name__ == "__main__":
    run(
        separate,
        stage="separators",
        adapter="roformer",
        version=f"audio-separator {version('audio-separator')}/{MODEL}",
    )
