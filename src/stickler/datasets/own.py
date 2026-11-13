"""Own songs: description in references/own/<id>.yaml, score and alignment in
data/own/<id>/ (not in the repo, because notes and recordings belong to third parties).

YAML: `title`, `audio`, optional `exclude: [[from, to], ...]` in audio seconds.
`audio` is a file name, searched first in data/own/<id>/ and then anywhere below the music
folder (STICKLER_MUSIC_DIR, else the XDG music folder, else ~/Music), so the references
reveal nothing about how a music collection is organised. A path (absolute or with `~`) is
used as given. Score: data/own/<id>/score.mid. Result of `stickler align`:
data/own/<id>/aligned.json (notes in audio time, excluded regions, quality).
Only songs whose alignment passes the quality check become benchmark tracks.
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

Interval = tuple[float, float]

log = logging.getLogger(__name__)
MUSIC_DIR_ENV = "STICKLER_MUSIC_DIR"


def _xdg_music() -> Path | None:
    try:
        out = subprocess.run(["xdg-user-dir", "MUSIC"], capture_output=True, text=True).stdout
    except OSError:
        return None
    path = Path(out.strip()) if out.strip() else None
    return path if path and path != Path.home() else None


def music_dir() -> Path:
    if os.environ.get(MUSIC_DIR_ENV):
        return Path(os.environ[MUSIC_DIR_ENV]).expanduser()
    return _xdg_music() or Path.home() / "Music"


@cache
def _index(root: Path) -> dict[str, list[Path]]:
    """File name → paths below `root`, sorted (built once per run)."""
    found: dict[str, list[Path]] = {}
    for folder, _, files in os.walk(root):
        for name in files:
            found.setdefault(name, []).append(Path(folder) / name)
    return {name: sorted(paths) for name, paths in found.items()}


def _find_audio(audio: str, song_dir: Path) -> Path:
    if "/" in audio or audio.startswith("~"):
        return Path(audio).expanduser()
    if (song_dir / audio).exists():
        return song_dir / audio
    matches = _index(music_dir()).get(audio, [])
    if len(matches) > 1:
        log.warning(
            "%s found %d times below %s, using %s", audio, len(matches), music_dir(), matches[0]
        )
    return matches[0] if matches else song_dir / audio


@dataclass(frozen=True)
class Song:
    id: str
    title: str
    audio: Path
    dir: Path  # data/own/<id>
    exclude: tuple[Interval, ...] = ()
    # Owner listened to click.wav and approves despite failed automatic checks (reason text)
    approved_by_ear: str | None = None

    @property
    def score(self) -> Path:
        return self.dir / "score.mid"

    @property
    def aligned(self) -> Path:
        return self.dir / "aligned.json"


@dataclass(frozen=True)
class Track:
    id: str
    mix: Path
    drums: None
    excluded: tuple[Interval, ...]
    notes: tuple[tuple[float, int], ...]

    def reference_notes(self) -> list[tuple[float, int]]:
        return list(self.notes)


def songs(references_dir: Path, data_dir: Path) -> list[Song]:
    out = []
    for path in sorted(references_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out.append(
            Song(
                id=path.stem,
                title=str(raw.get("title", path.stem)),
                audio=_find_audio(str(raw["audio"]), data_dir / "own" / path.stem),
                dir=data_dir / "own" / path.stem,
                exclude=tuple((float(a), float(b)) for a, b in raw.get("exclude") or []),
                approved_by_ear=raw.get("approved_by_ear"),
            )
        )
    return out


def save_alignment(
    song: Song,
    *,
    notes: list[tuple[float, int]],
    excluded: list[Interval],
    quality: dict,
    reasons: list[str],
    shift: float,
    approved_by_ear: str | None = None,
) -> Path:
    song.dir.mkdir(parents=True, exist_ok=True)
    data = {
        "song": song.id,
        "audio": str(song.audio),
        "passed": not reasons or bool(approved_by_ear),
        "reasons": reasons,
        "approved_by_ear": approved_by_ear,
        "quality": quality,
        "shift": shift,
        "excluded": [[a, None if math.isinf(b) else b] for a, b in excluded],
        "notes": [[round(t, 4), p] for t, p in notes],
    }
    song.aligned.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return song.aligned


def load_alignment(song: Song) -> dict | None:
    if not song.aligned.exists():
        return None
    data = json.loads(song.aligned.read_text(encoding="utf-8"))
    data["excluded"] = [(a, math.inf if b is None else b) for a, b in data["excluded"]]
    return data


def tracks(references_dir: Path, data_dir: Path) -> list[Track]:
    """Benchmark tracks: only songs with a passed alignment."""
    out = []
    for song in songs(references_dir, data_dir):
        data = load_alignment(song)
        if data and data["passed"]:
            out.append(
                Track(
                    id=song.id,
                    mix=song.audio,
                    drums=None,
                    excluded=tuple(data["excluded"]),
                    notes=tuple((t, p) for t, p in data["notes"]),
                )
            )
    return out
