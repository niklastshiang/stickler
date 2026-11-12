"""Stickler adapter: MuScriptor transcribes all instruments; only the drum track is kept.

Official API `TranscriptionModel.transcribe` (greedy, all instruments allowed), raw events
without `transcribe_and_postprocess`: its timing correction along the beat grid moved the notes
on MDB Punk 15–40 ms too early (macro-F1 mix 0.47 instead of 0.79, Demucs stem 0.32 instead of
0.73), while the raw events are already on time (+10/0 ms). Drum events carry GM pitches.
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
