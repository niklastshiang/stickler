#!/usr/bin/env python3
"""Stand-in models for the bridge's process tests (Python: tests/app/test_bridge_process.py;
Swift: SticklerCore's client tests). They are called `adtof` and `beat_this` and run through the
real chain (their own uv environment and process group, the results cache), in a second each.

Usage: uv run python scripts/bridge_stand_ins.py <folder>
Writes <folder>/models (set up with uv, offline) and <folder>/Groove.wav (eight quiet seconds)
and prints {"models": ..., "song": ...} as one JSON line."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

from stickler import adapters

COMMON = Path(__file__).resolve().parents[1] / "adapters" / "_common"

PYPROJECT = """[project]
name = "stand-in-{name}"
version = "0"
requires-python = ">=3.12,<3.13"
dependencies = ["stickler-adapter"]

[tool.uv.sources]
stickler-adapter = {{ path = "{common}", editable = true }}
"""

TRANSCRIBER = '''"""Stand-in for ADTOF: a groove; with STICKLER_TEST_HOLD it writes its pid
there and waits like a long model."""

import os
import time
from pathlib import Path

from stickler_adapter import run, write_drum_midi


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    hold = os.environ.get("STICKLER_TEST_HOLD")
    if hold:
        Path(hold).write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(60)
    notes = [(k * 0.5, 36 if k % 2 == 0 else 38, 100) for k in range(16)]
    write_drum_midi(out_dir / "drums.mid", notes)


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="adtof", version="stand-in")
'''

BEATS = '''"""Stand-in for Beat This!: a beat every half second, a bar every two seconds."""

import json
from pathlib import Path

from stickler_adapter import run


def track_beats(audio: Path, out_dir: Path, device: str) -> None:
    beats = [k * 0.5 for k in range(17)]
    data = {"beats": beats, "downbeats": beats[::4]}
    (out_dir / "beats.json").write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    run(track_beats, stage="beats", adapter="beat_this", version="stand-in")
'''


def set_up(root: Path) -> Path:
    """The stand-ins under `root`, set up (uv sync; their only dependency is local)."""
    for stage, name, code in (
        ("transcribers", "adtof", TRANSCRIBER),
        ("beats", "beat_this", BEATS),
    ):
        folder = root / stage / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "run.py").write_text(code, encoding="utf-8")
        (folder / "pyproject.toml").write_text(
            PYPROJECT.format(name=name, common=COMMON.as_posix()), encoding="utf-8"
        )
    for spec in adapters.discover(root).values():
        adapters.setup_adapter(spec)
    return root


def quiet_song(path: Path) -> Path:
    """Eight seconds of quiet: enough for ffprobe and the stand-ins."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\0\0" * 8000 * 8)
    return path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    folder = Path(argv[0]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    models = set_up(folder / "models")
    song = quiet_song(folder / "Groove.wav")
    print(json.dumps({"models": str(models), "song": str(song)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
