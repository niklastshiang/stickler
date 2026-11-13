"""Scoring with mir_eval: precision/recall/F1 per class, micro and macro."""

from __future__ import annotations

from dataclasses import dataclass

import mir_eval
import numpy as np

from stickler.classes import Onsets

# Tolerance window ±50 ms, standard in the ADT literature (MDB, ENST, ADTOF).
WINDOW = 0.05
_EMPTY = np.empty(0)


@dataclass(frozen=True)
class PRF:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass(frozen=True)
class Scores:
    per_class: dict[str, PRF]
    micro: PRF
    # Mean of the F1 values over classes with reference events; None if there are none.
    macro_f1: float | None


def match(ref: np.ndarray, est: np.ndarray, window: float = WINDOW) -> PRF:
    """Counts for one class; each estimate hits at most one reference within `window`."""
    tp = len(mir_eval.util.match_events(ref, est, window)) if ref.size and est.size else 0
    return PRF(tp=tp, fp=int(est.size) - tp, fn=int(ref.size) - tp)


def score(ref: Onsets, est: Onsets, window: float = WINDOW) -> Scores:
    """Compares estimated with reference onsets; each estimate hits at most one reference."""
    classes = list(ref.by_class) + [c for c in est.by_class if c not in ref.by_class]
    per_class = {
        c: match(ref.by_class.get(c, _EMPTY), est.by_class.get(c, _EMPTY), window) for c in classes
    }
    micro = PRF(
        tp=sum(p.tp for p in per_class.values()),
        fp=sum(p.fp for p in per_class.values()),
        fn=sum(p.fn for p in per_class.values()),
    )
    present = [per_class[c].f1 for c in classes if ref.by_class.get(c, _EMPTY).size]
    macro = float(np.mean(present)) if present else None
    return Scores(per_class=per_class, micro=micro, macro_f1=macro)
