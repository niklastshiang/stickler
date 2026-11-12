"""Test transcriber that only accepts drum stems (input = "stem")."""

from pathlib import Path

from stickler_adapter import run, write_drum_midi


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    write_drum_midi(out_dir / "drums.mid", [(0.5, 36, 100), (1.0, 38, 90)])


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="stemonly", version="1.0")
