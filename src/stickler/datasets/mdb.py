"""MDB Drums (Southall et al., ISMIR 2017): 23 tracks from MedleyDB, CC BY-NC-SA 4.0.

Source: https://github.com/CarlSouthall/MDBDrums
Only the subclass annotations, the mix and the drum stem are downloaded (not the multitracks).
The 21 subclass labels, mapped to GM pitches, serve as the reference. This way the same class
scheme applies to reference and models (e.g. the side stick, which MDB lists under "OT",
counts as SD).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

REPO_URL = "https://github.com/CarlSouthall/MDBDrums.git"
ROOT = "MDB Drums"
SPARSE_PATHS = [
    f"/{ROOT}/annotations/subclass/",
    f"/{ROOT}/audio/full_mix/",
    f"/{ROOT}/audio/drum_only/",
]

# MDB subclass → GM drum pitch (meanings according to the MDB Drums paper)
SUBCLASS_TO_GM: dict[str, int] = {
    "KD": 36,  # Kick
    "SD": 38,  # Snare
    "SDB": 38,  # Snare: Buzz
    "SDD": 38,  # Snare: Drag
    "SDF": 38,  # Snare: Flam
    "SDG": 38,  # Snare: Ghost Note
    "SDNS": 38,  # Snare without snares
    "SST": 37,  # Side Stick
    "CHH": 42,  # Hi-hat closed
    "PHH": 44,  # Hi-hat pedal
    "OHH": 46,  # Hi-hat open
    "LFT": 41,  # Low Floor Tom
    "HFT": 43,  # High Floor Tom
    "MHT": 45,  # Mid Tom
    "HIT": 48,  # High Tom
    "RDC": 51,  # Ride
    "RDB": 53,  # Ride Bell
    "CRC": 49,  # Crash
    "CHC": 52,  # China
    "SPC": 55,  # Splash
    "TMB": 54,  # Tambourine
}


@dataclass(frozen=True)
class Track:
    id: str
    mix: Path
    drums: Path
    annotation: Path
    excluded: tuple[tuple[float, float], ...] = ()  # MDB is fully annotated

    def reference_notes(self) -> list[tuple[float, int]]:
        return read_subclass_file(self.annotation)


def read_subclass_file(path: Path) -> list[tuple[float, int]]:
    """Reads `<time> \\t <label>` lines and maps the labels to GM pitches."""
    notes: list[tuple[float, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        time, label = line.split()
        if label not in SUBCLASS_TO_GM:
            raise ValueError(f"{path.name}: unknown MDB label {label!r}")
        notes.append((float(time), SUBCLASS_TO_GM[label]))
    return notes


def _annotation_dir(target: Path) -> Path:
    return target / ROOT / "annotations" / "subclass"


def tracks(target: Path) -> list[Track]:
    """All available tracks, sorted by ID; empty if the dataset is missing."""
    ann_dir = _annotation_dir(target)
    if not ann_dir.is_dir():
        return []
    audio = target / ROOT / "audio"
    result = []
    for ann in sorted(ann_dir.glob("*_subclass.txt")):
        track_id = ann.name.removesuffix("_subclass.txt")
        result.append(
            Track(
                id=track_id,
                mix=audio / "full_mix" / f"{track_id}_MIX.wav",
                drums=audio / "drum_only" / f"{track_id}_Drum.wav",
                annotation=ann,
            )
        )
    return result


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def fetch(target: Path, repo_url: str = REPO_URL) -> int:
    """Downloads MDB Drums via sparse checkout to `target` (idempotent); returns the track count."""
    existing = tracks(target)
    if existing:
        log.info("MDB Drums already present: %d tracks", len(existing))
        return len(existing)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git(
            "clone",
            "-q",
            "--depth",
            "1",
            "--filter=blob:none",
            "--no-checkout",
            repo_url,
            str(target),
        )
        _git("-C", str(target), "sparse-checkout", "set", "--no-cone", *SPARSE_PATHS)
        _git("-C", str(target), "checkout", "-q")
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(f"MDB download failed: {exc.stderr.strip()}") from exc
    return len(tracks(target))
