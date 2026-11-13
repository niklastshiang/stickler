"""ENST-Drums (Gillet & Richard, ISMIR 2006): the 64 "minus-one" tracks with accompaniment.

The licence only allows personal, scientific use and forbids passing the data on
(docs/enst-request.md): it lives in `data/enst/` (gitignored) and is unpacked there by hand from
the archive the owner received (`drummer_<n>/annotation`, `audio/wet_mix`,
`audio/accompaniment`). `prepare` builds the evaluation mixes next to it.

Mix: 2/3 drums (wet mix) + 1/3 accompaniment, a ratio used throughout the drum transcription
literature for ENST. The wet mix serves as the oracle drum stem. Track ids carry the drummer
(`d1_107_minus-one_salsa_sticks`), because the numbers repeat across drummers.

Cite when publishing ENST numbers: O. Gillet & G. Richard, "ENST-Drums: an extensive
audio-visual database for drum signals processing", Proc. ISMIR 2006.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

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
        raise RuntimeError(
            f"no ENST-Drums minus-one tracks in {target}: request and unpack the data first "
            "(docs/enst-request.md)"
        )
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
