"""Stickler-Adapter: MuScriptor transkribiert alle Instrumente; übernommen wird nur die Drum-Spur.

Offizielle API `TranscriptionModel.transcribe` (greedy, alle Instrumente erlaubt), rohe
Ereignisse ohne `transcribe_and_postprocess`: Dessen Zeitkorrektur über das Beat-Raster
verschob die Noten auf MDB Punk um 15–40 ms zu früh (Macro-F1 Mix 0,47 statt 0,79,
Demucs-Stem 0,32 statt 0,73), während die rohen Ereignisse schon pünktlich sind (+10/0 ms).
Drum-Ereignisse tragen GM-Pitches.
"""

from importlib.metadata import version
from pathlib import Path

from common import SIZE
from muscriptor.events import NoteStartEvent
from muscriptor.transcription_model import TranscriptionModel
from stickler_adapter import run, torch_device, write_drum_midi


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    model = TranscriptionModel.load_model(SIZE, device=torch_device(device))
    notes = [
        (ev.start_time, ev.pitch, 100)
        for ev in model.transcribe(str(audio))
        if isinstance(ev, NoteStartEvent) and ev.instrument == "drums"
    ]
    write_drum_midi(out_dir / "drums.mid", notes)


if __name__ == "__main__":
    run(
        transcribe,
        stage="transcribers",
        adapter=Path(__file__).parent.name,
        version=f"muscriptor {version('muscriptor')}/{SIZE}",
    )
