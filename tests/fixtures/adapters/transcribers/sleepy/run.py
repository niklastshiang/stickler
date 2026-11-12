"""Test-Adapter, der hängt: Ein Zeitlimit muss auch den Modellprozess unter uv beenden."""

import time
from pathlib import Path

from stickler_adapter import run


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    (out_dir / "pid").write_text(str(__import__("os").getpid()), encoding="utf-8")
    time.sleep(60)


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="sleepy", version="0")
