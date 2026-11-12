"""Audio-Hilfen für den Harness (ohne Audio-Bibliothek, über ffprobe)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def duration(path: Path) -> float:
    """Dauer in Sekunden; RuntimeError, wenn ffprobe die Datei nicht lesen kann."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    proc = subprocess.run([*cmd, str(path)], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        detail = proc.stderr.strip() or "keine Dauer"
        raise RuntimeError(f"ffprobe: {path.name}: {detail}") from None
