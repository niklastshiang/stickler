"""Deliberately broken adapter: the harness must log the error and carry on."""

from pathlib import Path

from stickler_adapter import run


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    raise RuntimeError("Model exploded")


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="broken", version="0.0")
