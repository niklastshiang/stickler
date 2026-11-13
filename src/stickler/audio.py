"""Audio helpers for the harness (no audio library, via ffprobe/ffmpeg)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

# Formats every model adapter reads itself (libsndfile, checked on 2026-11-13 with all models).
# Anything else ffmpeg can decode (M4A/AAC, WMA, …) is converted to FLAC first.
MODEL_READABLE = {".wav", ".flac", ".mp3", ".ogg", ".oga", ".opus", ".aiff", ".aif"}
DECODED_DIR = "_decoded"


def readable(path: Path, cache: Path) -> Path:
    """`path` itself if every model reads its format, else a FLAC copy in cache/_decoded/
    (named by the input's content, decoded once). RuntimeError if ffmpeg cannot decode it."""
    if path.suffix.lower() in MODEL_READABLE:
        return path
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha1").hexdigest()
    out = cache / DECODED_DIR / f"{digest}.flac"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.flac")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", "0:a:0", "-c:a", "flac"]
    proc = subprocess.run([*cmd, str(tmp)], capture_output=True, text=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg cannot decode {path.name}: {proc.stderr.strip()[-200:]}")
    tmp.rename(out)
    return out


def duration(path: Path) -> float:
    """Duration in seconds; RuntimeError if ffprobe cannot read the file."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    proc = subprocess.run([*cmd, str(path)], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        detail = proc.stderr.strip() or "no duration"
        raise RuntimeError(f"ffprobe: {path.name}: {detail}") from None


def load_mono(path: Path, sr: int = 22050) -> np.ndarray:
    """Decodes any audio via ffmpeg to float32 at sample rate `sr` and averages the
    channels (ffmpeg's own downmixing preserves power, so it is louder than the mean)."""
    probe = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries"]
    info = subprocess.run(
        [*probe, "stream=channels", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
    )
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    # first integer only: with csv output, some MP3s (side data) yield "2," instead of "2"
    found = re.match(r"\s*(\d+)", info.stdout or "")
    if info.returncode != 0 or proc.returncode != 0 or not proc.stdout or not found:
        detail = proc.stderr.decode(errors="replace").strip() or "no audio"
        raise RuntimeError(f"ffmpeg: {path.name}: {detail}")
    channels = int(found.group(1))
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    return data.reshape(-1, channels).mean(axis=1).astype(np.float32)


def write_wav(path: Path, signal: np.ndarray, sr: int) -> Path:
    """16-bit WAV; `signal` is (samples,) or (samples, channels), values are clipped to ±1."""
    data = signal if signal.ndim == 2 else signal[:, None]
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def tags(path: Path) -> dict[str, str]:
    """Title and artist from the file's tags (case-insensitive keys); {} if there are none."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        raw = json.loads(proc.stdout).get("format", {}).get("tags", {})
    except json.JSONDecodeError:
        return {}
    lower = {k.lower(): v.strip() for k, v in raw.items() if isinstance(v, str)}
    return {k: lower[k] for k in ("title", "artist") if lower.get(k)}
