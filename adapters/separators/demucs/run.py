"""Stickler-Adapter: Demucs v4 (htdemucs_ft) trennt den Drum-Stem aus dem Mix.

Nutzt die offizielle Python-API `demucs.api.Separator` mit den Standardwerten der Kommandozeile
(split, overlap 0.25, shifts 1). htdemucs_ft ist ein Verbund aus vier feinjustierten Modellen.
"""

from pathlib import Path

import demucs
import demucs.api
import soundfile
from common import MODEL
from stickler_adapter import run, torch_device


def separate(audio: Path, out_dir: Path, device: str) -> None:
    separator = demucs.api.Separator(model=MODEL, device=torch_device(device), progress=False)
    _, stems = separator.separate_audio_file(audio)
    drums = stems["drums"].cpu().numpy().T  # (Samples, Kanäle)
    soundfile.write(out_dir / "drums.wav", drums, separator.samplerate, subtype="PCM_24")


if __name__ == "__main__":
    run(separate, stage="separators", adapter="demucs", version=f"{demucs.__version__}/{MODEL}")
