"""Stickler adapter: Separate-and-Detect (Hsu et al., 2026) generates five drum stems from a drum
stem with a latent diffusion model (MSG-LD, OB+TB checkpoint); an onset detector per stem turns
them into hits.

Separation runs the paper's own inference path (`integrated_train.py --separate_only`: its data
module and `Trainer.validate`) with the inference config of the pinned commit, on the current
stack through compat.py. The song is cut into 10.24 s windows, each given to the data module as
a track of its own, so every second is covered (the data module drops a song's last partial
window and songs under 10 s or over 640 s); the windows' stems are joined again in order.

Onsets: not the paper's madmom detector but the onset step shared with drumsep_onset
(stickler_adapter.onsets: librosa envelopes, peaks on a scale shared by all stems), so the two
separations are compared with the same detector and both can be tuned with `stickler tune`.
The checkpoint is loaded with weights_only=True: no code in it is run.
"""

import math
import os
import sys
import tempfile
from pathlib import Path

import compat
import librosa
import numpy as np
import soundfile
import torch
import yaml
from common import CHECKPOINT, COMMIT, CONFIG, SAMPLE_RATE, SEGMENT, SOURCE, STEMS
from stickler_adapter import run, torch_device, write_drum_midi
from stickler_adapter.onsets import activations, transcribe

FPS = 100
STEM_PITCHES = {"kick": 36, "snare": 38, "toms": 47, "hi_hats": 42, "cymbals": 49}
COLUMNS = [["kick"], ["snare"], ["toms"], ["hi_hats"], ["cymbals"]]  # KD, SD, TT, HH, CY


def _windows(audio: Path, folder: Path) -> tuple[int, float]:
    """Writes the drum stem as one track per 10.24 s window (mono, 44.1 kHz, the last one
    padded with silence); returns the number of windows and the song's length in seconds."""
    samples, sr = soundfile.read(audio, always_2d=True, dtype="float32")
    mono = samples.mean(axis=1)
    if sr != SAMPLE_RATE:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=SAMPLE_RATE)
    seconds = len(mono) / SAMPLE_RATE
    size = round(SEGMENT * SAMPLE_RATE)
    count = max(1, math.ceil(len(mono) / size))
    mono = np.pad(mono, (0, count * size - len(mono)))
    for i in range(count):
        track = folder / f"w{i:05d}"
        track.mkdir(parents=True)
        soundfile.write(track / "drums.wav", mono[i * size : (i + 1) * size], SAMPLE_RATE)
    return count, seconds


def _separate(windows: Path, logs: Path, device: str) -> None:
    sys.path[:0] = [str(SOURCE / "src"), str(SOURCE)]
    compat.apply()
    from latent_diffusion.util import instantiate_from_config
    from pytorch_lightning import Trainer

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    params = cfg["model"]["params"]
    first_stage = params["first_stage_config"]["params"]
    first_stage["reload_from_ckpt"] = None  # the VAE's weights are in the checkpoint
    first_stage["ddconfig"]["hifigan_ckpt"] = None  # so are the vocoder's
    for key in ("onset_data_path", "timbre_data_path", "track_mapping_path"):
        params[key] = None  # training data only
    cfg["data"]["params"]["path"]["valid_data"] = str(windows)
    cfg["data"]["params"]["num_workers"] = 1
    os.chdir(SOURCE)  # the code finds its vocoder config relative to the repository
    model = instantiate_from_config(cfg["model"])
    state = torch.load(CHECKPOINT, map_location="cpu", weights_only=True, mmap=True)
    missing, _ = model.load_state_dict(state["state_dict"], strict=False)
    # The checkpoint leaves out the training loss's VGG network (LPIPS); inference never uses it.
    missing = [k for k in missing if not k.startswith("first_stage_model.loss.perceptual_loss.")]
    if missing:
        raise RuntimeError(f"checkpoint lacks {len(missing)} weights, e.g. {missing[:3]}")
    model.set_log_dir(str(logs), "sad", "run")
    data = instantiate_from_config(cfg["data"])
    data.prepare_data()
    data.setup()
    gpu = torch_device(device) == "cuda" and torch.cuda.is_available()
    trainer = Trainer(
        accelerator="gpu" if gpu else "cpu",
        devices=1,
        logger=False,
        limit_val_batches=1.0,
        enable_checkpointing=False,
        enable_progress_bar=False,
        num_sanity_val_steps=0,
    )
    trainer.validate(model, data)


def _envelopes(logs: Path, count: int, seconds: float) -> dict[str, np.ndarray]:
    """Each stem's windows joined in order, cut to the song's length → onset envelope."""
    out = {}
    for k, stem in enumerate(STEMS):
        files = [
            next(f for f in logs.rglob(f"stem_{k}/w{i:05d}_from_*.wav") if "val_" in str(f))
            for i in range(count)
        ]
        parts = [soundfile.read(f, always_2d=True, dtype="float32") for f in files]
        sr = parts[0][1]
        wave = np.concatenate([p.mean(axis=1) for p, _ in parts])[: math.ceil(seconds * sr)]
        out[stem] = librosa.onset.onset_strength(y=wave, sr=sr, hop_length=round(sr / FPS))
    length = max(len(e) for e in out.values())
    return {s: np.pad(e, (0, length - len(e))) for s, e in out.items()}


def transcribe_stem(audio: Path, out_dir: Path, device: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        windows, logs = Path(tmp) / "windows", Path(tmp) / "logs"
        count, seconds = _windows(audio, windows)
        _separate(windows, logs, device)
        envelopes = _envelopes(logs, count, seconds)
    write_drum_midi(out_dir / "drums.mid", transcribe(envelopes, STEM_PITCHES, FPS))
    act, labels = activations(envelopes, COLUMNS)
    np.savez_compressed(out_dir / "activations.npz", activations=act, fps=FPS, labels=labels)


if __name__ == "__main__":
    run(
        transcribe_stem,
        stage="transcribers",
        adapter="sad",
        version=f"separate-and-detect@{COMMIT[:7]}/msgld_obtb+onsets",
    )
