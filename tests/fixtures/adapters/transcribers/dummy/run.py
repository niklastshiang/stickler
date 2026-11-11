"""Dummy-Transkriber für Tests: MIDI mit Kick (36) bei 0,5 s und Snare (38) bei 1,0 s."""

from pathlib import Path

from stickler_adapter import run, write_drum_midi


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    write_drum_midi(out_dir / "drums.mid", [(0.5, 36, 100), (1.0, 38, 90)])


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="dummy", version="1.0")
