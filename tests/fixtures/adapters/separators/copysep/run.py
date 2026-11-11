"""Dummy-Separator für Tests: kopiert die Eingabe als drums.wav."""

import shutil
from pathlib import Path

from stickler_adapter import run


def separate(audio: Path, out_dir: Path, device: str) -> None:
    shutil.copyfile(audio, out_dir / "drums.wav")


if __name__ == "__main__":
    run(separate, stage="separators", adapter="copysep", version="1.0")
