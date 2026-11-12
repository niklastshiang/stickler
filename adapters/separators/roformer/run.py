"""Stickler-Adapter: BS-RoFormer (Band-Split RoFormer, Checkpoint „SW“) trennt den Drum-Stem.

Nutzt die offizielle Python-API von python-audio-separator mit deren Standardparametern.
Die Stem-Namen dieses Checkpoints sind kleingeschrieben („drums“); gewählt wird die Ausgabedatei
mit „(drums)“ im Namen, unabhängig von der Schreibweise.
"""

import tempfile
from importlib.metadata import version
from pathlib import Path

import soundfile
from audio_separator.separator import Separator
from common import MODEL, WEIGHTS
from stickler_adapter import run


def separate(audio: Path, out_dir: Path, device: str) -> None:
    # Gerät: audio-separator nimmt selbst die GPU, wenn torch eine sieht (ROCm-Umgebung);
    # in der CPU-Umgebung gibt es keine. Der Harness wählt die Umgebung passend zu `device`.
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
            raise RuntimeError(f"Drum-Stem nicht eindeutig in {outputs}")
        samples, sample_rate = soundfile.read(Path(tmp) / Path(drums[0]).name, always_2d=True)
    soundfile.write(out_dir / "drums.wav", samples, sample_rate, subtype="PCM_24")


if __name__ == "__main__":
    run(
        separate,
        stage="separators",
        adapter="roformer",
        version=f"audio-separator {version('audio-separator')}/{MODEL}",
    )
