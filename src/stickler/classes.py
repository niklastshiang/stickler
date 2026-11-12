"""Instrument classes: GM drum pitches → class schemes (5/3 classes) and onset container."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

# Several pitches of one class within this distance count as one hit
# (e.g. crash + ride at the same time). Smaller than any realistic flam (~20–40 ms).
MERGE_WINDOW = 0.010


@dataclass(frozen=True)
class Onsets:
    """Onset times in seconds per instrument class, sorted ascending."""

    by_class: dict[str, np.ndarray]

    def count(self) -> int:
        return sum(int(a.size) for a in self.by_class.values())


@dataclass(frozen=True)
class Scheme:
    """A class scheme, e.g. "5" = KD/SD/TT/HH/CY."""

    name: str
    classes: dict[str, frozenset[int]]

    def class_of(self, pitch: int) -> str | None:
        for cls, pitches in self.classes.items():
            if pitch in pitches:
                return cls
        return None


def load_schemes(path: Path) -> dict[str, Scheme]:
    """Reads `config/classes.yaml`; a pitch may belong to only one class per scheme."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    schemes: dict[str, Scheme] = {}
    for name, classes in raw["schemes"].items():
        seen: dict[int, str] = {}
        for cls, pitches in classes.items():
            for p in pitches:
                if p in seen:
                    raise ValueError(f"Scheme {name}: pitch {p} in {seen[p]} and {cls}")
                seen[p] = cls
        schemes[str(name)] = Scheme(str(name), {cls: frozenset(ps) for cls, ps in classes.items()})
    return schemes


def _merge_close(times: np.ndarray, window: float) -> np.ndarray:
    if times.size == 0:
        return times
    keep = np.concatenate(([True], np.diff(times) > window))
    return times[keep]


def onsets_from_notes(notes: Iterable[tuple[float, int]], scheme: Scheme) -> Onsets:
    """(time, GM pitch) pairs → onsets per class; unknown pitches are ignored."""
    grouped: dict[str, list[float]] = {cls: [] for cls in scheme.classes}
    for time, pitch in notes:
        cls = scheme.class_of(pitch)
        if cls is not None:
            grouped[cls].append(time)
    return Onsets(
        {
            cls: _merge_close(np.sort(np.asarray(ts, dtype=float)), MERGE_WINDOW)
            for cls, ts in grouped.items()
        }
    )
