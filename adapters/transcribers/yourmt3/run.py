"""Stickler-Adapter: YourMT3+ (YPTF.MoE+Multi, PS) transkribiert alle Instrumente,
übernommen wird nur die Drum-Spur.

Nachbau von `transcribe()` aus model_helper.py des Space (Revision in common.py):
Mono, Resampling auf 16 kHz, Segmente à `input_frames`, Batch-Inferenz, Detokenisierung je
Decoder-Kanal. Abweichung: Audio wird per soundfile geladen (torchaudio.load braucht in
neueren Versionen torchcodec) und das MIDI schreibt der gemeinsame Helfer statt des
Space-Writers. Die Drum-Pitches sind bereits GM.
"""

import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio
from common import ARGS, SRC, WEIGHTS
from stickler_adapter import run, torch_device, write_drum_midi

VERSION = "YourMT3-space@5e66c1e/YPTF.MoE+Multi-PS/fp32"
BATCH = 8


def _load_model(device: str):
    sys.path[:0] = [str(SRC), str(WEIGHTS)]
    os.chdir(WEIGHTS)  # Checkpoint-Pfad im Space-Code ist relativ (amt/logs/...)
    from model_helper import load_model_checkpoint

    return load_model_checkpoint(args=ARGS, device=device)


def _drum_notes(model, audio_segments: torch.Tensor) -> list[tuple[float, int]]:
    from utils.event2note import merge_zipped_note_events_and_ties_to_notes
    from utils.note2event import mix_notes

    pred_token_arr, _ = model.inference_file(bsz=BATCH, audio_segments=audio_segments)
    frames, rate = model.audio_cfg["input_frames"], model.audio_cfg["sample_rate"]
    starts = [frames * i / rate for i in range(audio_segments.shape[0])]
    per_channel = []
    for ch in range(model.task_manager.num_decoding_channels):
        tokens = [arr[:, ch, :] for arr in pred_token_arr]
        detok = model.task_manager.detokenize_list_batches
        zipped, _, _ = detok(tokens, starts, return_events=True)
        notes, _ = merge_zipped_note_events_and_ties_to_notes(zipped)
        per_channel.append(notes)
    return [(n.onset, n.pitch) for n in mix_notes(per_channel) if n.is_drum]


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    audio, out_dir = audio.resolve(), out_dir.resolve()
    dev = torch_device(device)
    model = _load_model(dev)
    from utils.audio import slice_padded_array

    data, sr = sf.read(audio, dtype="float32", always_2d=True)
    mono = torch.from_numpy(data.mean(axis=1)).unsqueeze(0)
    mono = torchaudio.functional.resample(mono, sr, model.audio_cfg["sample_rate"])
    frames = model.audio_cfg["input_frames"]
    segments = slice_padded_array(mono.numpy(), frames, frames)
    segments = torch.from_numpy(segments.astype(np.float32)).to(dev).unsqueeze(1)
    with torch.inference_mode():
        notes = _drum_notes(model, segments)
    write_drum_midi(out_dir / "drums.mid", [(t, p, 100) for t, p in notes])


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="yourmt3", version=VERSION)
