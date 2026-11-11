"""MDB Drums (Southall et al., ISMIR 2017): 23 Tracks aus MedleyDB, CC BY-NC-SA 4.0.

Quelle: https://github.com/CarlSouthall/MDBDrums
Geladen werden nur die Subclass-Annotationen, der Mix und der Drum-Stem (die Multitracks nicht).
Als Referenz dienen die 21 Subclass-Labels, abgebildet auf GM-Pitches. So gilt für Referenz und
Modelle dasselbe Klassen-Schema (z. B. zählt der Side Stick, den MDB unter "OT" führt, als SD).
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

# MDB-Subclass → GM-Drum-Pitch (Bedeutungen laut MDB-Drums-Paper)
SUBCLASS_TO_GM: dict[str, int] = {
    "KD": 36,  # Kick
    "SD": 38,  # Snare
    "SDB": 38,  # Snare: Buzz
    "SDD": 38,  # Snare: Drag
    "SDF": 38,  # Snare: Flam
    "SDG": 38,  # Snare: Ghost Note
    "SDNS": 38,  # Snare ohne Teppich
    "SST": 37,  # Side Stick
    "CHH": 42,  # Hi-Hat geschlossen
    "PHH": 44,  # Hi-Hat Pedal
    "OHH": 46,  # Hi-Hat offen
    "LFT": 41,  # Low Floor Tom
    "HFT": 43,  # High Floor Tom
    "MHT": 45,  # Mid Tom
    "HIT": 48,  # High Tom
    "RDC": 51,  # Ride
    "RDB": 53,  # Ride Bell
    "CRC": 49,  # Crash
    "CHC": 52,  # China
    "SPC": 55,  # Splash
    "TMB": 54,  # Tamburin
}


@dataclass(frozen=True)
class Track:
    id: str
    mix: Path
    drums: Path
    annotation: Path

    def reference_notes(self) -> list[tuple[float, int]]:
        return read_subclass_file(self.annotation)


def read_subclass_file(path: Path) -> list[tuple[float, int]]:
    """Liest `<zeit> \\t <label>`-Zeilen und bildet die Labels auf GM-Pitches ab."""
    notes: list[tuple[float, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        time, label = line.split()
        if label not in SUBCLASS_TO_GM:
            raise ValueError(f"{path.name}: unbekanntes MDB-Label {label!r}")
        notes.append((float(time), SUBCLASS_TO_GM[label]))
    return notes


def _annotation_dir(target: Path) -> Path:
    return target / ROOT / "annotations" / "subclass"


def tracks(target: Path) -> list[Track]:
    """Alle vorhandenen Tracks, sortiert nach ID; leer, wenn der Datensatz fehlt."""
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
    """Lädt MDB Drums per Sparse-Checkout nach `target` (idempotent); liefert die Track-Anzahl."""
    existing = tracks(target)
    if existing:
        log.info("MDB Drums schon vorhanden: %d Tracks", len(existing))
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
        raise RuntimeError(f"MDB-Download fehlgeschlagen: {exc.stderr.strip()}") from exc
    return len(tracks(target))
