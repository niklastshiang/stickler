"""Time alignment: lay the notes of an own song (MIDI, score time) onto the recording.

Procedure:
1. Score beats (quarters) from the tempo map of the MIDI, audio beats from Beat This!,
   brought to quarter level section by section (Beat This! sometimes switches to eighths or
   halves).
2. One rhythm pattern per beat (3 groups × 4 sixteenths): from the notes and from the
   spectral flux of the drum stem respectively (kick low, snare/toms mid, cymbals high).
3. DTW over the beat sequences: diagonal = paired, otherwise the beat is missing on one side.
4. Smooth paired beats per contiguous section (Beat This! quantises to 20 ms), map notes
   between the beats linearly, subtract the systematic offset to the onsets.
5. Exclude what is not comparable: audio without a counterpart in the notes and bars in which
   the notes rest but the audio clearly plays ("drum loop").
6. Quality check without a transcription model (thresholds see SPEC.md, calibrated on MDB).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido
import numpy as np
from mir_eval.util import match_events

from stickler import onsets

SUB = 4  # slots per beat (sixteenths for quarter beats)
KICKS = frozenset({35, 36})
METALS = frozenset({42, 44, 46, 49, 51, 52, 53, 55, 57, 59})  # hi-hat and cymbals
# DTW with affine gap costs: opening a gap is expensive, extending it is cheap.
# Otherwise the path spreads a missing passage over several places in repeating grooves
# and pairs wrong beats in between.
GAP_OPEN = 1.5
GAP_EXTEND = 0.3
EDGE_SKIP = 0.5  # per beat before the first/after the last pair; more expensive than an extension
SMOOTH = 4.0  # s left and right (score time) for the local line fit
STEP_JUMP = 0.25  # beat spacing deviates this much from the section → split the smoothing
ACTIVE = 0.3  # audio beat counts as played if a slot reaches this share
# Empty note beat against played audio: cheaper than two gaps, so that note gaps
# ("drum loop") stay diagonally paired and are excluded as a gap.
EMPTY_SCORE_COST = 0.6
GAP_BEATS = 4  # this many empty note beats with playing in the audio make a gap
BEAT_TOL = 0.07  # s
ONSET_TOL = 0.05  # s
STRONG_SHARE = 0.2  # the strongest 20 % of the onsets count as clear
MIN_SHIFT_SAMPLES = 10

# Minimum and maximum values; calibrated on MDB (correct references), see SPEC.md
THRESHOLDS = {"beat_fit": 0.95, "coverage": 0.85, "explained": 0.90, "excluded_strong": 0.20}


@dataclass(frozen=True)
class Score:
    beats: np.ndarray  # quarter beats in score seconds, one beyond the last note
    notes: list[tuple[float, int]]  # (score second, GM pitch)


@dataclass(frozen=True)
class Quality:
    beat_fit: float  # share of paired, played note beats that sit within ±70 ms
    coverage: float  # share of note hits with an onset in the stem (±50 ms)
    explained: float  # share of clear onsets with a note hit (±50 ms)
    excluded_strong: float  # share of clear onsets in excluded regions
    # Info only, no limit (owner's rule): share of played note beats without a counterpart in
    # the recording, e.g. repeats the transcriber added. They are dropped from the reference.
    score_unmatched: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Alignment:
    mapped_times: np.ndarray  # audio time per note from Score.notes, NaN = cannot be mapped
    excluded: list[tuple[float, float]]  # audio-time intervals without scoring
    quality: Quality
    shift: float  # subtracted systematic offset (s)


def read_score(path: Path) -> Score:
    """Drum notes (channel 10) and quarter beats from a MIDI with a tempo map."""
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat
    tick, sec, tempo = 0, 0.0, 500000
    changes = [(0, 0.0, tempo)]
    notes = []
    for msg in mido.merge_tracks(mid.tracks):
        sec += mido.tick2second(msg.time, tpb, tempo)
        tick += msg.time
        if msg.type == "set_tempo":
            tempo = msg.tempo
            changes.append((tick, sec, tempo))
        elif msg.type == "note_on" and msg.velocity > 0 and msg.channel == 9:
            notes.append((round(sec, 6), msg.note))

    def to_sec(t: int) -> float:
        c_tick, c_sec, c_tempo = next(c for c in reversed(changes) if c[0] <= t)
        return c_sec + mido.tick2second(t - c_tick, tpb, c_tempo)

    beats = np.array([to_sec(k * tpb) for k in range(tick // tpb + 2)])
    return Score(beats=beats, notes=sorted(notes))


def _group(pitch: int) -> int:
    return 0 if pitch in KICKS else 2 if pitch in METALS else 1


QUARTER_WINDOW = (0.7, 1.4)  # next quarter beat: this many quarters after the last one
TEMPO_MEMORY = 8  # beats for the running tempo estimate


def _normalize_beats(
    beats: np.ndarray, quarter: float, times: np.ndarray, flux: np.ndarray
) -> np.ndarray:
    """Track audio beats to score quarters. Beat This! switches level depending on the section
    (Bat Country: eighths in the fast parts, otherwise quarters). From each kept beat, the next
    one is searched about a quarter later; if none lies in the window, one is inserted. This
    keeps the phase stable across section boundaries. Only at the start does the kick/snare
    energy decide whether the first or second beat lies on the quarter."""
    if len(beats) < 3:
        return beats
    env = flux[:, :2].sum(axis=1)

    def energy(at: np.ndarray) -> float:
        idx = np.clip(np.searchsorted(times, at), 0, len(env) - 1)
        return float(np.mean([env[max(0, i - 3) : i + 4].max() for i in idx])) if len(idx) else 0.0

    start = 0
    if (beats[1] - beats[0]) / quarter < QUARTER_WINDOW[0]:
        head = beats[:16]
        start = int(np.argmax([energy(head[p::2]) for p in (0, 1)]))
    kept = [float(beats[start])]
    lo, hi = QUARTER_WINDOW
    for b in beats[start + 1 :]:
        q = float(np.median(np.diff(kept[-TEMPO_MEMORY:]))) if len(kept) > 2 else quarter
        gap = b - kept[-1]
        if gap < lo * q:
            continue  # in-between beat (eighth level)
        while gap > hi * q:  # beat missing (half level or dropout): fill in
            kept.append(kept[-1] + gap / max(2, round(gap / q)))
            gap = b - kept[-1]
        kept.append(float(b))
    return np.array(kept)


def _score_features(notes: list[tuple[float, int]], beats: np.ndarray) -> np.ndarray:
    """Slots are centred on the grid points: a hit just before the beat counts for the beat."""
    feats = np.zeros((len(beats) - 1, 3 * SUB))
    for t, pitch in notes:
        i = int(np.searchsorted(beats, t, side="right")) - 1
        if 0 <= i < len(feats):
            pos = int(round((t - beats[i]) / (beats[i + 1] - beats[i]) * SUB))
            i, slot = (i + 1, 0) if pos == SUB else (i, pos)
            if i < len(feats):
                feats[i, _group(pitch) * SUB + slot] = 1.0
    return feats


def _audio_features(beats: np.ndarray, times: np.ndarray, flux: np.ndarray) -> np.ndarray:
    """Each band normalised to the 99.5th percentile (rare hits such as kick on 1 and 3 lie
    above the 95th percentile); slot windows centred on the grid points as for the notes."""
    scale = np.percentile(flux, 99.5, axis=0)
    norm = np.clip(flux / np.where(scale > 0, scale, 1.0), 0.0, 1.0)
    feats = np.zeros((len(beats) - 1, 3 * SUB))
    for j in range(len(beats) - 1):
        step = (beats[j + 1] - beats[j]) / SUB
        edges = np.searchsorted(times, beats[j] + (np.arange(SUB + 1) - 0.5) * step)
        for s in range(SUB):
            lo, hi = edges[s], max(edges[s] + 1, edges[s + 1])
            if lo < len(norm):
                feats[j, s::SUB] = norm[lo:hi].max(axis=0)
    return feats


def _cost(fs: np.ndarray, fa: np.ndarray) -> np.ndarray:
    ns, na = np.linalg.norm(fs, axis=1), np.linalg.norm(fa, axis=1)
    cos = (fs @ fa.T) / np.maximum(ns[:, None] * na[None, :], 1e-9)
    cost = 1.0 - cos
    s_empty, a_empty = ns == 0, fa.max(axis=1) < ACTIVE
    cost[s_empty, :] = EMPTY_SCORE_COST
    cost[np.ix_(s_empty, a_empty)] = 0.0
    return cost


def _dtw(cost: np.ndarray) -> list[tuple[int, int]]:
    """Paired beats (i notes, j audio) along the cheapest path.

    Three states: M = both sides advance one beat (cost from the pattern),
    X = only the notes (beat missing in the audio), Y = only the audio (beat missing in the notes).
    Edges: beats before the first and after the last pair cost EDGE_SKIP per beat."""
    n, m = cost.shape
    inf = np.inf
    big_m, big_x, big_y = (np.full((n + 1, m + 1), inf) for _ in range(3))
    big_m[0, 0] = 0.0
    big_x[1:, 0] = np.arange(1, n + 1) * EDGE_SKIP
    big_y[0, 1:] = np.arange(1, m + 1) * EDGE_SKIP
    ptr_m = np.zeros((n + 1, m + 1), dtype=np.int8)  # predecessor state 0=M, 1=X, 2=Y
    ptr_x = np.zeros((n + 1, m + 1), dtype=np.int8)
    ptr_y = np.zeros((n + 1, m + 1), dtype=np.int8)
    opened = GAP_OPEN + GAP_EXTEND
    for i in range(1, n + 1):
        prev = np.stack([big_m[i - 1, :-1], big_x[i - 1, :-1], big_y[i - 1, :-1]])
        ptr_m[i, 1:] = prev.argmin(axis=0)
        big_m[i, 1:] = prev.min(axis=0) + cost[i - 1]
        up = np.stack(
            [big_m[i - 1, 1:] + opened, big_x[i - 1, 1:] + GAP_EXTEND, big_y[i - 1, 1:] + opened]
        )
        ptr_x[i, 1:] = up.argmin(axis=0)
        big_x[i, 1:] = up.min(axis=0)
        row_m, row_x, row_y = big_m[i], big_x[i], big_y[i]
        for j in range(1, m + 1):  # Y depends on Y[i, j-1]: sequential
            options = (row_m[j - 1] + opened, row_x[j - 1] + opened, row_y[j - 1] + GAP_EXTEND)
            best = int(np.argmin(options))
            row_y[j], ptr_y[i, j] = options[best], (0, 1, 2)[best]
    ends = []
    for state, mat in enumerate((big_m, big_x, big_y)):
        ends += [(mat[n, j] + (m - j) * EDGE_SKIP, n, j, state) for j in range(m + 1)]
        ends += [(mat[i, m] + (n - i) * EDGE_SKIP, i, m, state) for i in range(n)]
    _, i, j, state = min(ends)
    pairs = []
    while i > 0 and j > 0:
        if state == 0:
            pairs.append((i - 1, j - 1))
            state, i, j = int(ptr_m[i, j]), i - 1, j - 1
        elif state == 1:
            state, i = int(ptr_x[i, j]), i - 1
        else:
            state, j = int(ptr_y[i, j]), j - 1
    return pairs[::-1]


def _smoothed_runs(pairs: list[tuple[int, int]], sb: np.ndarray, ab: np.ndarray) -> dict:
    """Smooth paired beat boundaries per section (both sides gapless) with a local linear fit.
    Result: score beat index → (audio time, section no.)."""
    runs: list[list[tuple[int, int]]] = []
    for i, j in pairs:
        if runs and runs[-1][-1] == (i - 1, j - 1):
            runs[-1].append((i, j))
        else:
            runs.append([(i, j)])
    mapping = {}
    for r, run in enumerate(runs):
        pts = [*run, (run[-1][0] + 1, run[-1][1] + 1)]  # interval i covers boundaries i and i+1
        xs, ys = np.array([sb[i] for i, _ in pts]), np.array([ab[j] for _, j in pts])
        # A jump in beat spacing (short pause, fermata) splits the smoothing, otherwise the
        # line bends both sides of the jump.
        ratio = np.diff(ys) / np.diff(xs)
        jump = np.abs(ratio / np.median(ratio) - 1.0) > STEP_JUMP
        segment = np.concatenate([[0], np.cumsum(jump)])
        for k, (i, _) in enumerate(pts):
            near = (np.abs(xs - xs[k]) <= SMOOTH) & (segment == segment[k])
            if near.sum() >= 2:
                slope, icpt = np.polyfit(xs[near], ys[near], 1)
                mapping[i] = (slope * xs[k] + icpt, r)
            else:
                mapping[i] = (ys[k], r)
    return mapping


def _merge(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _inside(times: np.ndarray, intervals: list[tuple[float, float]]) -> np.ndarray:
    mask = np.zeros(len(times), dtype=bool)
    for a, b in intervals:
        mask |= (times >= a) & (times < b)
    return mask


def _fraction(num: int, den: int) -> float:
    return num / den if den else 0.0


def align(
    score: Score,
    audio_beats: np.ndarray,
    flux_times: np.ndarray,
    flux: np.ndarray,
    exclude: tuple[tuple[float, float], ...] = (),
) -> Alignment:
    """Lays the notes onto the recording and checks the quality (see module docs).
    `exclude`: additional audio-time intervals excluded by hand."""
    quarter = float(np.median(np.diff(score.beats)))
    ab = _normalize_beats(np.asarray(audio_beats, dtype=float), quarter, flux_times, flux)
    sb = score.beats
    fs, fa = _score_features(score.notes, sb), _audio_features(ab, flux_times, flux)
    pairs = _dtw(_cost(fs, fa))
    mapping = _smoothed_runs(pairs, sb, ab)

    note_t = np.array([t for t, _ in score.notes])
    mapped = np.full(len(note_t), np.nan)
    for n, t in enumerate(note_t):
        i = int(np.searchsorted(sb, t, side="right")) - 1
        if i in mapping and i + 1 in mapping and mapping[i][1] == mapping[i + 1][1]:
            (a0, _), (a1, _) = mapping[i], mapping[i + 1]
            mapped[n] = a0 + (t - sb[i]) / (sb[i + 1] - sb[i]) * (a1 - a0)

    env = onsets.combined(flux)
    peaks = onsets.pick_peaks(env, 1.0 / onsets.HOP)
    onset_t, strength = flux_times[peaks], env[peaks]
    strong_t = (
        onset_t[strength >= np.quantile(strength, 1 - STRONG_SHARE)] if len(peaks) else onset_t
    )

    shift = 0.0
    valid = mapped[~np.isnan(mapped)]
    if len(onset_t) and len(valid):
        near = onset_t[np.clip(np.searchsorted(onset_t, valid), 0, len(onset_t) - 1)]
        prev = onset_t[np.clip(np.searchsorted(onset_t, valid) - 1, 0, len(onset_t) - 1)]
        nearest = np.where(abs(near - valid) < abs(prev - valid), near, prev)
        resid = (nearest - valid)[abs(nearest - valid) <= BEAT_TOL]
        if len(resid) >= MIN_SHIFT_SAMPLES:
            shift = float(np.median(resid))
            mapped = mapped + shift

    matched_audio = {j for _, j in pairs}
    excluded = [
        (float(ab[j]), float(ab[j + 1])) for j in range(len(ab) - 1) if j not in matched_audio
    ]
    if pairs:
        excluded += [(0.0, float(ab[pairs[0][1]])), (float(ab[pairs[-1][1] + 1]), float("inf"))]
    gap: list[tuple[int, int]] = []
    for i, j in pairs:
        if not fs[i].any() and fa[j].max() >= ACTIVE:
            gap.append((i, j))
            continue
        if len(gap) >= GAP_BEATS:
            excluded.append((float(ab[gap[0][1]]), float(ab[gap[-1][1] + 1])))
        gap = []
    if len(gap) >= GAP_BEATS:
        excluded.append((float(ab[gap[0][1]]), float(ab[gap[-1][1] + 1])))
    # Boundaries moved inward by the onset tolerance: notes on the first/last paired beat
    # belong to the scored part even if the offset subtraction shifts them by a few ms.
    excluded = [
        (a + ONSET_TOL if a > 0 else a, b - ONSET_TOL)
        for a, b in _merge(excluded)
        if b - a > 2 * ONSET_TOL
    ]
    excluded = _merge([*excluded, *exclude])

    playing = [i for i in range(len(fs)) if fs[i].any()]
    pair_of = dict(pairs)
    paired = [i for i in playing if i in pair_of and i in mapping]
    fit = sum(1 for i in paired if abs(mapping[i][0] - ab[pair_of[i]]) <= BEAT_TOL)

    ref = np.unique(np.round(mapped[~np.isnan(mapped)], 3))
    ref = ref[~_inside(ref, excluded)]
    if len(ref):
        ref = ref[np.concatenate([[True], np.diff(ref) > onsets.MIN_GAP])]
    strong_in = _inside(strong_t, excluded)
    strong_out = strong_t[~strong_in]
    quality_vals = {
        "beat_fit": _fraction(fit, len(paired)),
        "coverage": _fraction(len(match_events(ref, onset_t, ONSET_TOL)), len(ref)),
        "explained": _fraction(len(match_events(ref, strong_out, ONSET_TOL)), len(strong_out)),
        "excluded_strong": _fraction(int(strong_in.sum()), len(strong_t)),
    }
    reasons = [
        f"{name} = {value:.3f} (limit {'≤' if name == 'excluded_strong' else '≥'} "
        f"{THRESHOLDS[name]})"
        for name, value in quality_vals.items()
        if (value > THRESHOLDS[name] if name == "excluded_strong" else value < THRESHOLDS[name])
    ]
    return Alignment(
        mapped_times=mapped,
        excluded=excluded,
        quality=Quality(
            **quality_vals,
            score_unmatched=_fraction(len(playing) - len(paired), len(playing)),
            reasons=reasons,
        ),
        shift=shift,
    )
