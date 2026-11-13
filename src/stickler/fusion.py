"""Fusing ADTOF's frame activations from several inputs of one song (e.g. the mix and a drum
stem) and tuning the fusion weights and the peak-picking threshold per instrument class.

Fusion is a weighted mean of the activations over their common length; onsets are then picked
per class (stickler.peaks). Tuning maximises each class's F1 over the pooled counts of all
tuning tracks, the same counts the summary uses (results.summarize). Classes are independent,
so every class gets its own weights and threshold.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from stickler import peaks
from stickler.evaluate import PRF, WINDOW, match


@dataclass(frozen=True)
class Sample:
    activations: list[np.ndarray]  # one [frames, classes] array per input, same column order
    reference: dict[str, np.ndarray]  # reference onset times per class (exclusions removed)
    excluded: tuple[tuple[float, float], ...] = ()  # audio-time intervals without scoring


@dataclass(frozen=True)
class ClassParams:
    weights: tuple[float, ...]  # one per input, summing to 1
    threshold: float


@dataclass(frozen=True)
class Tuned:
    weights: tuple[float, ...]
    threshold: float
    f1: float
    counts: tuple[int, int, int]  # tp, fp, fn

    @property
    def params(self) -> ClassParams:
        return ClassParams(self.weights, self.threshold)


def fuse(activations: Sequence[np.ndarray], weights: Sequence[float]) -> np.ndarray:
    if len(weights) != len(activations):
        raise ValueError(f"{len(activations)} inputs need as many weights, got {len(weights)}")
    n = min(a.shape[0] for a in activations)
    out = np.zeros((n, activations[0].shape[1]), dtype=np.float32)
    for a, w in zip(activations, weights, strict=True):
        out += np.float32(w) * a[:n].astype(np.float32)
    return out


def weight_grid(n: int, step: float = 0.25) -> list[tuple[float, ...]]:
    """All weight vectors for n inputs on a grid with the given step that sum to 1."""
    k = round(1 / step)
    return [
        tuple(c / k for c in combo)
        for combo in itertools.product(range(k + 1), repeat=n)
        if sum(combo) == k
    ]


def _outside(times: np.ndarray, excluded: Sequence[tuple[float, float]]) -> np.ndarray:
    keep = np.ones(times.size, dtype=bool)
    for start, end in excluded:
        keep &= ~((times >= start) & (times <= end))
    return times[keep]


def _counts(samples, fused, col, cls, thr, fps) -> tuple[int, int, int]:
    tp = fp = fn = 0
    for s, f in zip(samples, fused, strict=True):
        est = _outside(peaks.pick(f[:, col], thr, fps), s.excluded)
        prf = match(s.reference.get(cls, np.zeros(0)), est, WINDOW)
        tp, fp, fn = tp + prf.tp, fp + prf.fp, fn + prf.fn
    return tp, fp, fn


def score_params(
    samples: Sequence[Sample],
    labels: Sequence[int],
    class_of: Mapping[int, str],
    params: Mapping[str, ClassParams],
    fps: int = peaks.FPS,
) -> dict[str, Tuned]:
    """Pooled counts and F1 per class for fixed settings (e.g. ADTOF's defaults)."""
    out = {}
    for col, label in enumerate(labels):
        cls = class_of[label]
        p = params[cls]
        fused = [fuse(s.activations, p.weights) for s in samples]
        counts = _counts(samples, fused, col, cls, p.threshold, fps)
        out[cls] = Tuned(p.weights, p.threshold, PRF(*counts).f1, counts)
    return out


def tune(
    samples: Sequence[Sample],
    labels: Sequence[int],
    class_of: Mapping[int, str],
    *,
    weights: Sequence[tuple[float, ...]],
    thresholds: Sequence[float],
    fps: int = peaks.FPS,
) -> dict[str, Tuned]:
    """Best weights and threshold per class (first of equal F1 values in grid order)."""
    best: dict[str, Tuned] = {}
    for w in weights:
        fused = [fuse(s.activations, w) for s in samples]
        for col, label in enumerate(labels):
            cls = class_of[label]
            for thr in thresholds:
                tp, fp, fn = _counts(samples, fused, col, cls, thr, fps)
                f1 = PRF(tp, fp, fn).f1
                if cls not in best or f1 > best[cls].f1:
                    best[cls] = Tuned(tuple(w), float(thr), f1, (tp, fp, fn))
    return best


def notes(
    activations: Sequence[np.ndarray],
    params: Mapping[str, ClassParams],
    labels: Sequence[int],
    class_of: Mapping[int, str],
    fps: int = peaks.FPS,
) -> list[tuple[float, int]]:
    """(time, pitch) notes with each class's own fusion weights and threshold."""
    out = []
    for col, label in enumerate(labels):
        p = params[class_of[label]]
        fused = fuse(activations, p.weights)
        out += [(float(t), int(label)) for t in peaks.pick(fused[:, col], p.threshold, fps)]
    return sorted(out)


# --- Fused pipelines in a benchmark config ------------------------------------------------
#
#   fusions:
#     adtof_fused:
#       inputs: [none, demucs]          # separators whose ADTOF activations are fused
#       classes:                        # every class of the 5-class scheme
#         KD: {weights: [0.5, 0.5], threshold: 0.24}
#
# Scored like any pipeline (separator "fusion", transcriber = the fusion's name) and usable in
# combos as "fusion+<name>". Built from the cached ADTOF runs; nothing is recomputed.

FUSION_SEPARATOR = "fusion"
# ADTOF's own thresholds (adtof_pytorch FRAME_RNN_THRESHOLDS, in LABELS_5 order 35/38/47/42/49)
ADTOF_THRESHOLDS = {"KD": 0.22, "SD": 0.24, "TT": 0.32, "HH": 0.22, "CY": 0.30}
TRANSCRIBER = "adtof"
ACTIVATIONS = "activations.npz"


@dataclass(frozen=True)
class Fusion:
    name: str
    inputs: tuple[str, ...]
    params: dict[str, ClassParams]


def parse_fusions(raw: Mapping | None, classes: Sequence[str]) -> list[Fusion]:
    out = []
    for name, spec in (raw or {}).items():
        inputs = tuple(str(i) for i in spec.get("inputs", []))
        given = spec.get("classes") or {}
        missing = [c for c in classes if c not in given]
        if not inputs or missing:
            raise ValueError(f"fusion {name}: needs inputs and every class ({', '.join(missing)})")
        params = {}
        for cls in classes:
            w = tuple(float(x) for x in given[cls]["weights"])
            if len(w) != len(inputs):
                raise ValueError(f"fusion {name}, {cls}: {len(inputs)} inputs need as many weights")
            params[cls] = ClassParams(w, float(given[cls]["threshold"]))
        out.append(Fusion(str(name), inputs, params))
    return out


def load_activations(record) -> tuple[np.ndarray, list[int], int]:
    with np.load(record.midi.parent / ACTIVATIONS) as z:
        return z["activations"], [int(x) for x in z["labels"]], int(z["fps"])


def _inputs(records, inputs: Sequence[str]) -> dict[tuple[str, str], dict[str, object]]:
    """(dataset, track) → {separator: ADTOF record} for the wanted inputs."""
    by_track: dict[tuple[str, str], dict[str, object]] = {}
    for r in records:
        if r.transcriber == TRANSCRIBER and r.separator in inputs:
            by_track.setdefault((r.dataset, r.track), {})[r.separator] = r
    return by_track


def fused_records(records, fusions: Sequence[Fusion], class_of: Mapping[int, str]) -> list:
    """One record per fusion and track that has at least one of the fusion's inputs."""
    from stickler.runner import Record

    out = []
    for f in fusions:
        for (dataset, track), found in _inputs(records, f.inputs).items():
            parts = [found.get(i) for i in f.inputs]
            bad = [i for i, r in zip(f.inputs, parts, strict=True) if r is None or not r.ok]
            notes_, error = None, None
            if bad:
                error = f"missing or failed input: {', '.join(bad)}"
            else:
                loaded = [load_activations(r) for r in parts]
                labels, fps = loaded[0][1], loaded[0][2]
                notes_ = tuple(notes([a for a, _, _ in loaded], f.params, labels, class_of, fps))
            present = [r for r in parts if r is not None]
            out.append(
                Record(
                    dataset,
                    track,
                    FUSION_SEPARATOR,
                    f.name,
                    None,
                    None,
                    {"seconds": sum((r.separator_meta or {}).get("seconds", 0.0) for r in present)},
                    {
                        "seconds": sum(
                            (r.transcriber_meta or {}).get("seconds", 0.0) for r in present
                        ),
                        "device": "+".join(
                            sorted({(r.transcriber_meta or {}).get("device", "") for r in present})
                        ),
                    },
                    error,
                    notes_,
                )
            )
    return out


def samples_from_records(records, tracks: Mapping[str, Sequence], inputs: Sequence[str], scheme):
    """Tuning samples: tracks where every input's ADTOF run succeeded."""
    from stickler.classes import onsets_from_notes

    by_id = {(ds, t.id): t for ds, ts in tracks.items() for t in ts}
    out = []
    for key, found in _inputs(records, inputs).items():
        parts = [found.get(i) for i in inputs]
        if key not in by_id or any(r is None or not r.ok for r in parts):
            continue
        track = by_id[key]
        ref = onsets_from_notes(track.reference_notes(), scheme).by_class
        excluded = tuple(track.excluded)
        reference = {c: _outside(t, excluded) for c, t in ref.items()}
        out.append(Sample([load_activations(r)[0] for r in parts], reference, excluded))
    return out
