"""Shared helpers for Stickler adapters.

Every adapter calls `run(fn, stage=..., adapter=..., version=...)`. This implements the contract:
    python run.py --in <audio> --out <dir> [--device auto|cpu|gpu]
`fn(audio, out_dir, device)` writes the stage output (drums.wav / drums.mid / beats.json),
`run` adds meta.json (adapter, version, device, runtime, peak RAM) or error.log.
Deliberately free of dependencies so that it fits into every adapter environment.
"""

from __future__ import annotations

import argparse
import json
import resource
import struct
import sys
import time
import traceback
from collections.abc import Callable, Iterable
from pathlib import Path

DEVICES = ("auto", "cpu", "gpu")


def _gpu_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    # ROCm builds of PyTorch also report AMD GPUs via torch.cuda.
    return bool(torch.cuda.is_available())


def choose_device(requested: str) -> str:
    """'auto' → GPU if available, otherwise CPU. 'gpu' without a GPU is an error."""
    if requested == "cpu":
        return "cpu"
    available = _gpu_available()
    if requested == "gpu" and not available:
        raise RuntimeError("GPU requested, but torch sees no GPU (ROCm environment built?)")
    return "gpu" if available else "cpu"


def torch_device(device: str) -> str:
    """Stickler device → torch device name."""
    return "cuda" if device == "gpu" else "cpu"


def _vlq(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def write_drum_midi(path: Path, notes: Iterable[tuple[float, int, int]]) -> None:
    """Writes (time s, GM pitch, velocity) as SMF type 0 on channel 10, 120 BPM, 480 PPQ."""
    ticks_per_second = 960  # 480 PPQ at 120 BPM
    duration = 10  # ticks (~10 ms); drums need no real note length
    events: list[tuple[int, int, bytes]] = []  # (tick, order, bytes): note-off before note-on
    for t, pitch, velocity in notes:
        tick = round(t * ticks_per_second)
        vel = max(1, min(127, int(velocity)))
        events.append((tick, 1, bytes([0x99, pitch, vel])))
        events.append((tick + duration, 0, bytes([0x89, pitch, 0])))
    events.sort()
    track = bytearray(b"\x00\xff\x51\x03\x07\xa1\x20")  # tempo 500000 µs/beat = 120 BPM
    last = 0
    for tick, _, data in events:
        track += _vlq(tick - last) + data
        last = tick
    track += b"\x00\xff\x2f\x00"  # end of track
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480)
    path.write_bytes(header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track))


def _peak_rss_mb() -> float:
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return max(own, children) / 1024  # Linux: KiB


def run(fn: Callable[[Path, Path, str], None], *, stage: str, adapter: str, version: str) -> None:
    parser = argparse.ArgumentParser(description=f"Stickler adapter {adapter} ({stage})")
    parser.add_argument("--in", dest="audio", type=Path, required=True)
    parser.add_argument("--out", dest="out_dir", type=Path, required=True)
    parser.add_argument("--device", choices=DEVICES, default="auto")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        device = choose_device(args.device)
        start = time.perf_counter()
        fn(args.audio, args.out_dir, device)
        seconds = time.perf_counter() - start
    except Exception:
        (args.out_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
        sys.exit(1)
    meta = {
        "adapter": adapter,
        "stage": stage,
        "version": version,
        "device": device,
        "seconds": round(seconds, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
