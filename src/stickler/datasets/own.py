"""Own songs: description in references/own/<id>.yaml, score and alignment in
data/own/<id>/ (not in the repo, because notes and recordings belong to third parties).

YAML: `title`, `audio` (path, `~` allowed), optional `exclude: [[from, to], ...]` in
audio seconds. Score: data/own/<id>/score.mid. Result of `stickler align`:
data/own/<id>/aligned.json (notes in audio time, excluded regions, quality).
Only songs whose alignment passes the quality check become benchmark tracks.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

Interval = tuple[float, float]


@dataclass(frozen=True)
class Song:
    id: str
    title: str
    audio: Path
    dir: Path  # data/own/<id>
    exclude: tuple[Interval, ...] = ()

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
                audio=Path(raw["audio"]).expanduser(),
                dir=data_dir / "own" / path.stem,
                exclude=tuple((float(a), float(b)) for a, b in raw.get("exclude") or []),
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
) -> Path:
    song.dir.mkdir(parents=True, exist_ok=True)
    data = {
        "song": song.id,
        "audio": str(song.audio),
        "passed": not reasons,
        "reasons": reasons,
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
