"""ENST-Drums (Gillet & Richard, ISMIR 2006): the 64 "minus-one" tracks with accompaniment.

Since July 2026 the authors publish ENST-Drums openly on Zenodo (record 21506051, v2) under
CC BY-NC-ND 4.0: research only, no commercial use, no redistribution of adapted material.
`fetch` downloads the archive (9.6 GB incl. videos), checks its MD5, unpacks only the
annotations and the minus-one audio into `data/enst/` (gitignored) and deletes the archive;
`prepare` builds the evaluation mixes next to it.

Mix: 2/3 drums (wet mix) + 1/3 accompaniment, a ratio used throughout the drum transcription
literature for ENST. The wet mix serves as the oracle drum stem. Track ids carry the drummer
(`d1_107_minus-one_salsa_sticks`), because the numbers repeat across drummers.

Cite when publishing ENST numbers: O. Gillet & G. Richard, "ENST-Drums: an extensive
audio-visual database for drum signals processing", Proc. ISMIR 2006.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

URL = "https://zenodo.org/records/21506051/files/enst_drums_v1_1.tar.zst?download=1"
MD5 = "a134f0a34d12eb5317ff3ddd7d07b6db"  # as published on Zenodo
ARCHIVE = "enst_drums_v1_1.tar.zst"
USER_AGENT = "stickler (+https://github.com/niklastshiang/stickler)"
NEEDED = ("*/annotation/*", "*/audio/wet_mix/*minus-one*", "*/audio/accompaniment/*minus-one*")

DRUM_GAIN = 2 / 3
ACCOMPANIMENT_GAIN = 1 / 3
MIX_DIR = "mix"

# ENST label (without the instrument number, e.g. rc3 → rc) → GM drum pitch; None = not a hit
LABEL_TO_GM: dict[str, int | None] = {
    "bd": 36,  # bass drum
    "sd": 38,  # snare drum
    "sd-": 38,  # snare drum with the snares off
    "rs": 40,  # rim shot
    "cs": 37,  # cross stick
    "chh": 42,  # closed hi-hat
    "ohh": 46,  # open hi-hat
    "lft": 41,  # low floor tom
    "lt": 45,  # low tom
    "ltr": 45,  # low tom, rim
    "lmt": 47,  # low-mid tom
    "mt": 48,  # mid tom
    "mtr": 48,  # mid tom, rim
    "rc": 51,  # ride cymbal
    "cr": 49,  # crash cymbal
    "ch": 52,  # Chinese cymbal
    "spl": 55,  # splash cymbal
    "c": 57,  # other cymbal
    "cb": 56,  # cowbell (in no class scheme, ignored when scoring)
    "sweep": None,  # brush sweep, no onset
}


@dataclass(frozen=True)
class Track:
    id: str
    mix: Path
    drums: Path
    annotation: Path
    excluded: tuple[tuple[float, float], ...] = ()  # fully annotated

    def reference_notes(self) -> list[tuple[float, int]]:
        return read_annotation(self.annotation)


def read_annotation(path: Path) -> list[tuple[float, int]]:
    """Reads `<time> <label>` lines; labels are mapped to GM pitches (unknown labels raise)."""
    notes: list[tuple[float, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        time, label = line.split()
        key = label if label in LABEL_TO_GM else re.sub(r"\d+$", "", label)
        if key not in LABEL_TO_GM:
            raise ValueError(f"{path.name}: unknown ENST label {label!r}")
        pitch = LABEL_TO_GM[key]
        if pitch is not None:
            notes.append((float(time), pitch))
    return notes


def _sources(target: Path) -> list[tuple[str, Path, Path, Path]]:
    """(track id, annotation, wet mix, accompaniment) for every complete minus-one track."""
    found = []
    for drummer in sorted(target.glob("drummer_*")):
        number = drummer.name.removeprefix("drummer_")
        for ann in sorted((drummer / "annotation").glob("*minus-one*.txt")):
            wet = drummer / "audio" / "wet_mix" / f"{ann.stem}.wav"
            acc = drummer / "audio" / "accompaniment" / f"{ann.stem}.wav"
            if wet.is_file() and acc.is_file():
                found.append((f"d{number}_{ann.stem}", ann, wet, acc))
    return found


def tracks(target: Path) -> list[Track]:
    """Minus-one tracks whose mix has been prepared, sorted by id; empty if none."""
    return [
        Track(track_id, target / MIX_DIR / f"{track_id}.wav", wet, ann)
        for track_id, ann, wet, _ in _sources(target)
        if (target / MIX_DIR / f"{track_id}.wav").is_file()
    ]


def prepare(target: Path) -> int:
    """Builds the missing evaluation mixes (idempotent); returns the number of tracks."""
    sources = _sources(target)
    if not sources:
        raise RuntimeError(f"no ENST-Drums minus-one tracks in {target}: run `stickler fetch enst`")
    (target / MIX_DIR).mkdir(exist_ok=True)
    for track_id, _, wet, acc in sources:
        out = target / MIX_DIR / f"{track_id}.wav"
        if out.is_file():
            continue
        tmp = out.with_suffix(".part.wav")
        mix = (
            f"[0:a]volume={DRUM_GAIN}[d];[1:a]volume={ACCOMPANIMENT_GAIN}[a];"
            "[d][a]amix=inputs=2:normalize=0:duration=longest"
        )
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(wet), "-i", str(acc)]
        subprocess.run(
            [*cmd, "-filter_complex", mix, "-c:a", "pcm_s16le", str(tmp)],
            check=True,
            capture_output=True,
        )
        tmp.rename(out)
    return len(sources)


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    done, step = 0, 1 << 30
    with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if done % step < len(chunk):
                log.info("ENST download: %d GB", done // step)


def fetch(target: Path) -> int:
    """Downloads ENST-Drums from Zenodo unless it is already there; returns the track count."""
    if _sources(target):
        return prepare(target)
    target.mkdir(parents=True, exist_ok=True)
    archive = target / ARCHIVE
    part = archive.with_name(ARCHIVE + ".part")
    _download(URL, part)
    with part.open("rb") as f:
        digest = hashlib.file_digest(f, "md5").hexdigest()
    if digest != MD5:
        part.unlink()
        raise RuntimeError(f"ENST download damaged: checksum {digest}, expected {MD5}")
    part.rename(archive)
    subprocess.run(
        [
            "tar",
            "--zstd",
            "-xf",
            str(archive),
            "-C",
            str(target),
            "--strip-components=1",
            "--wildcards",
            *NEEDED,
        ],
        check=True,
        capture_output=True,
    )
    archive.unlink()
    return prepare(target)
