"""Absichtlich kaputter Adapter: der Harness muss den Fehler protokollieren und weitermachen."""

from pathlib import Path

from stickler_adapter import run


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    raise RuntimeError("Modell explodiert")


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="broken", version="0.0")
