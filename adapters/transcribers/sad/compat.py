"""Lets the paper's code (written for Python 3.9, torch 1.13, pytorch-lightning 1.9) run on this
environment's current stack, without changing a file of it. Each shim restores one API the
code calls that newer versions removed; nothing changes what the model computes. Found in the
spike of 2026-11-16 (tasks/todo.md, Task 83). Import before any module of the paper's code.
"""

import sys
import types

import librosa.filters
import pytorch_lightning.utilities.types
import soundfile
import torch
import torchaudio
from pytorch_lightning.utilities.rank_zero import rank_zero_only


def _info(path, *args, **kwargs):
    i = soundfile.info(str(path))
    return types.SimpleNamespace(
        num_frames=i.frames, sample_rate=i.samplerate, num_channels=i.channels
    )


def _load(path, frame_offset=0, num_frames=-1, *args, **kwargs):
    x, sr = soundfile.read(
        str(path), start=frame_offset, frames=num_frames, dtype="float32", always_2d=True
    )
    return torch.from_numpy(x.T.copy()), sr


_mel = librosa.filters.mel


_MEL_ARGS = ("sr", "n_fft", "n_mels", "fmin", "fmax")


def _mel_positional(*args, **kwargs):
    return _mel(**dict(zip(_MEL_ARGS, args, strict=False)), **kwargs)


def apply() -> None:
    # torchaudio >= 2.9 dropped info() and load() (moved to torchcodec)
    torchaudio.info, torchaudio.load = _info, _load
    # librosa >= 0.10 takes keyword arguments only
    librosa.filters.mel = _mel_positional
    # pytorch-lightning 2 removed EPOCH_OUTPUT and utilities.distributed
    pytorch_lightning.utilities.types.EPOCH_OUTPUT = list
    distributed = types.ModuleType("pytorch_lightning.utilities.distributed")
    distributed.rank_zero_only = rank_zero_only
    sys.modules["pytorch_lightning.utilities.distributed"] = distributed
    # The autoencoder builds its training loss, which downloads LPIPS weights on construction;
    # inference never uses the loss, and the checkpoint holds its weights anyway.
    import taming.modules.losses.lpips as lpips
    import torchvision

    lpips.LPIPS.load_from_pretrained = lambda self, name="vgg_lpips": None
    lpips.vgg16 = lambda pretrained=True, **kw: torchvision.models.vgg16(weights=None)
