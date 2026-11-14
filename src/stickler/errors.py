"""Error analysis: what kind of error every unmatched hit is (SPEC.md, "Release 3").

Hits are matched per class exactly as in `evaluate.score` (mir_eval, ±50 ms). Every remaining
reference hit (false negative) and estimated hit (false positive) gets one category, in order:

1. confused: a false negative of class A and a false positive of class B ≠ A within ±50 ms,
   paired one-to-one, as many pairs as possible;
2. off time: a false negative and a false positive of the same class 50–100 ms apart;
3. missed (remaining false negatives) and invented (remaining false positives).

So the categories add up exactly to the fn and fp of `evaluate.score`.
"""

from __future__ import annotations

import bisect
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import mir_eval
import numpy as np

from stickler.classes import Onsets
from stickler.evaluate import WINDOW

OFF_TIME = 0.1  # same drum up to 100 ms away: a timing error, not a missed hit
SEED = 20261114  # the listening sample is drawn once with this seed (SPEC.md, "Release 3")


@dataclass(frozen=True)
class Confusion:
    ref_cls: str  # the drum the reference has
    est_cls: str  # the drum the model wrote instead
    ref_time: float
    est_time: float


@dataclass(frozen=True)
class ClassErrors:
    tp: int
    missed: tuple[float, ...]  # reference hits the model did not find
    invented: tuple[float, ...]  # model hits the reference does not have
    off_time: tuple[tuple[float, float], ...]  # (reference time, model time), 50-100 ms apart


@dataclass(frozen=True)
class Breakdown:
    per_class: dict[str, ClassErrors]
    confused: tuple[Confusion, ...]

    def counts(self, cls: str) -> dict[str, int]:
        e = self.per_class.get(cls, ClassErrors(0, (), (), ()))
        return {
            "tp": e.tp,
            "missed": len(e.missed),
            "invented": len(e.invented),
            "off_time": len(e.off_time),
            "confused_ref": sum(c.ref_cls == cls for c in self.confused),
            "confused_est": sum(c.est_cls == cls for c in self.confused),
        }


def _unmatched(ref: np.ndarray, est: np.ndarray, window: float) -> tuple[list, list, list]:
    """Matched index pairs and the unmatched reference and estimate indices."""
    pairs = mir_eval.util.match_events(ref, est, window) if ref.size and est.size else []
    used_r, used_e = {i for i, _ in pairs}, {j for _, j in pairs}
    return (
        pairs,
        [i for i in range(ref.size) if i not in used_r],
        [j for j in range(est.size) if j not in used_e],
    )


def _pair_confusions(
    fns: list[tuple[float, str]], fps: list[tuple[float, str]], window: float
) -> dict[int, int]:
    """Maximum one-to-one pairing of false negatives and false positives of different classes
    within `window` (augmenting paths). Returns fn index → fp index."""
    fp_times = [t for t, _ in fps]
    candidates = []
    for t, cls in fns:
        lo = bisect.bisect_left(fp_times, t - window)
        hi = bisect.bisect_right(fp_times, t + window)
        candidates.append([j for j in range(lo, hi) if fps[j][1] != cls])
    fp_to_fn: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in candidates[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in fp_to_fn or augment(fp_to_fn[j], seen):
                fp_to_fn[j] = i
                return True
        return False

    for i in range(len(fns)):
        augment(i, set())
    return {i: j for j, i in fp_to_fn.items()}


def categorise(ref: Onsets, est: Onsets, window: float = WINDOW) -> Breakdown:
    """Categorises every error of `est` against `ref` (see the module docstring)."""
    empty = np.empty(0)
    classes = list(ref.by_class) + [c for c in est.by_class if c not in ref.by_class]
    times = {c: (ref.by_class.get(c, empty), est.by_class.get(c, empty)) for c in classes}
    tp: dict[str, int] = {}
    fns: list[tuple[float, str]] = []
    fps: list[tuple[float, str]] = []
    for c, (r, e) in times.items():
        pairs, free_r, free_e = _unmatched(r, e, window)
        tp[c] = len(pairs)
        fns += [(float(r[i]), c) for i in free_r]
        fps += [(float(e[j]), c) for j in free_e]
    fns.sort()
    fps.sort()

    paired = _pair_confusions(fns, fps, window)
    confused = tuple(
        Confusion(fns[i][1], fps[j][1], fns[i][0], fps[j][0]) for i, j in sorted(paired.items())
    )
    used_fp = set(paired.values())
    rest_fn = [x for i, x in enumerate(fns) if i not in paired]
    rest_fp = [x for j, x in enumerate(fps) if j not in used_fp]

    per_class = {}
    for c in classes:
        r = np.asarray([t for t, k in rest_fn if k == c])
        e = np.asarray([t for t, k in rest_fp if k == c])
        pairs, free_r, free_e = _unmatched(r, e, OFF_TIME)
        per_class[c] = ClassErrors(
            tp=tp[c],
            missed=tuple(float(r[i]) for i in free_r),
            invented=tuple(float(e[j]) for j in free_e),
            off_time=tuple(sorted((float(r[i]), float(e[j])) for i, j in pairs)),
        )
    return Breakdown(per_class, confused)


def count_rows(b: Breakdown, classes: list[str]) -> list[dict]:
    """One row per class: the counts, and per drum how many of this class's reference hits were
    written as that drum (`ref_as_<drum>`; always 0 for the class itself, so every row has the
    same columns)."""
    return [
        {
            "class": c,
            **b.counts(c),
            **{
                f"ref_as_{other}": sum(x.ref_cls == c and x.est_cls == other for x in b.confused)
                for other in classes
            },
        }
        for c in classes
    ]


def pool(rows: list[dict], keys: tuple[str, ...] = ("pipeline", "class")) -> list[dict]:
    """Sums the integer counts of rows with the same `keys` (e.g. over all songs)."""
    out: dict[tuple, dict] = {}
    for row in rows:
        group = out.setdefault(tuple(row[k] for k in keys), {k: row[k] for k in keys})
        for k, v in row.items():
            if k not in keys and isinstance(v, int):
                group[k] = group.get(k, 0) + v
    return list(out.values())


Side = Literal["ref", "est"]


@dataclass(frozen=True)
class Spot:
    """One error spot to judge by ear: does `cls` have a hit at `time` in `song`?"""

    song: str
    time: float
    cls: str
    side: Side  # who claims the hit: the reference or a pipeline
    pipelines: frozenset[str]  # pipelines whose error set contains this spot


def _claims(b: Breakdown) -> list[tuple[float, str, Side]]:
    out: list[tuple[float, str, Side]] = []
    for cls, e in b.per_class.items():
        out += [(t, cls, "ref") for t in e.missed]
        out += [(t, cls, "est") for t in e.invented]
        for r, x in e.off_time:
            out += [(r, cls, "ref"), (x, cls, "est")]
    for c in b.confused:
        out += [(c.ref_time, c.ref_cls, "ref"), (c.est_time, c.est_cls, "est")]
    return out


def spots(breakdowns: Mapping[tuple[str, str, str], Breakdown]) -> list[Spot]:
    """Every error of every (dataset, song, pipeline) as a spot; the same claim in several
    pipelines is one spot that lists them all."""
    found: dict[tuple[str, float, str, str], set[str]] = {}
    for (_, song, pipeline), b in breakdowns.items():
        for time, cls, side in _claims(b):
            found.setdefault((song, round(time, 4), cls, side), set()).add(pipeline)
    return [
        Spot(song, time, cls, side, frozenset(pipes))
        for (song, time, cls, side), pipes in sorted(found.items())
    ]


def _order(s: Spot) -> tuple:
    return (s.cls, s.side, s.song, s.time)


def draw_sample(all_spots: list[Spot], per_class_side: int, seed: int = SEED) -> list[Spot]:
    """`per_class_side` spots per class and side, uniformly at random (all of a smaller group),
    in random order. The same spots and seed give the same sample in any input order."""
    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[Spot]] = {}
    for s in sorted(all_spots, key=_order):
        groups.setdefault((s.cls, s.side), []).append(s)
    sample = [
        s
        for key in sorted(groups)
        for s in rng.sample(groups[key], min(per_class_side, len(groups[key])))
    ]
    rng.shuffle(sample)
    return sample
