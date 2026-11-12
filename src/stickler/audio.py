"""Audio-Hilfen für den Harness (ohne Audio-Bibliothek, über ffprobe/ffmpeg)."""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np


def duration(path: Path) -> float:
    """Dauer in Sekunden; RuntimeError, wenn ffprobe die Datei nicht lesen kann."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    proc = subprocess.run([*cmd, str(path)], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        detail = proc.stderr.strip() or "keine Dauer"
        raise RuntimeError(f"ffprobe: {path.name}: {detail}") from None


def load_mono(path: Path, sr: int = 22050) -> np.ndarray:
    """Dekodiert beliebiges Audio per ffmpeg zu float32 mit Abtastrate `sr` und mittelt die
    Kanäle (ffmpegs eigenes Downmixing ist leistungserhaltend, also lauter als der Mittelwert)."""
    probe = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries"]
    info = subprocess.run(
        [*probe, "stream=channels", "-of", "csv=p=0", str(path)], capture_output=True, text=True
    )
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if info.returncode != 0 or proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode(errors="replace").strip() or "kein Audio"
        raise RuntimeError(f"ffmpeg: {path.name}: {detail}")
    channels = int(info.stdout.strip().splitlines()[0])
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    return data.reshape(-1, channels).mean(axis=1).astype(np.float32)


def write_wav(path: Path, signal: np.ndarray, sr: int) -> Path:
    """16-Bit-WAV; `signal` ist (Samples,) oder (Samples, Kanäle), Werte werden auf ±1 begrenzt."""
    data = signal if signal.ndim == 2 else signal[:, None]
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path
