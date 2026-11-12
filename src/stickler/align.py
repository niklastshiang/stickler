"""Zeitabgleich: Noten eines eigenen Songs (MIDI, Partiturzeit) auf die Aufnahme legen.

Ablauf:
1. Partitur-Beats aus der Tempokarte des MIDI, Audio-Beats von Beat This!.
2. Je Beat ein Rhythmusmuster (3 Gruppen × 4 Sechzehntel): aus den Noten bzw. aus dem
   spektralen Fluss des Drum-Stems (Kick tief, Snare/Toms mittel, Becken hoch).
3. DTW über die Beat-Folgen: diagonal = gepaart, sonst fehlt der Beat auf einer Seite.
4. Gepaarte Beats je zusammenhängendem Abschnitt glätten (Beat This! rastert auf 20 ms),
   Noten zwischen den Beats linear abbilden, systematischen Versatz zu den Onsets abziehen.
5. Ausklammern, was nicht vergleichbar ist: Audio ohne Gegenstück in den Noten und Takte,
   in denen die Noten pausieren, im Audio aber deutlich gespielt wird ("Drum Loop").
6. Qualitätsprüfung ohne Transkriptionsmodell (Schwellen siehe SPEC.md, kalibriert an MDB).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido
import numpy as np
from mir_eval.util import match_events

from stickler import onsets

SUB = 4  # Slots je Beat (Sechzehntel bei Viertel-Beats)
KICKS = frozenset({35, 36})
METALS = frozenset({42, 44, 46, 49, 51, 52, 53, 55, 57, 59})  # Hi-Hat und Becken
# DTW mit affinen Lückenkosten: eine Lücke zu öffnen ist teuer, sie zu verlängern billig.
# Sonst verteilt der Pfad eine fehlende Passage bei sich wiederholenden Grooves auf mehrere
# Stellen und paart dazwischen falsche Beats.
GAP_OPEN = 1.5
GAP_EXTEND = 0.3
EDGE_SKIP = 0.5  # je Beat vor dem ersten/nach dem letzten Paar; teurer als eine Verlängerung
SMOOTH = 4.0  # s links und rechts (Partiturzeit) für die lokale Geradenanpassung
ACTIVE = 0.3  # Audio-Beat gilt als gespielt, wenn ein Slot diesen Anteil erreicht
# Leerer Noten-Beat gegen gespieltes Audio: billiger als zwei Lücken, damit Notenlücken
# ("Drum Loop") diagonal gepaart bleiben und als Lücke ausgeklammert werden.
EMPTY_SCORE_COST = 0.6
GAP_BEATS = 4  # so viele leere Noten-Beats mit Spiel im Audio ergeben eine Lücke
BEAT_TOL = 0.07  # s
ONSET_TOL = 0.05  # s
STRONG_SHARE = 0.2  # die stärksten 20 % der Onsets gelten als deutlich
MIN_SHIFT_SAMPLES = 10

# Mindest- bzw. Höchstwerte; kalibriert an MDB (korrekte Referenzen), siehe SPEC.md
THRESHOLDS = {"beat_fit": 0.95, "coverage": 0.85, "explained": 0.90, "excluded_strong": 0.20}


@dataclass(frozen=True)
class Score:
    beats: np.ndarray  # Viertel-Beats in Partitursekunden, einer über die letzte Note hinaus
    notes: list[tuple[float, int]]  # (Partitursekunde, GM-Pitch)


@dataclass(frozen=True)
class Quality:
    beat_fit: float  # Anteil gespielter Noten-Beats, die gepaart und ±70 ms genau sitzen
    coverage: float  # Anteil der Notenschläge mit Onset im Stem (±50 ms)
    explained: float  # Anteil der deutlichen Onsets mit Notenschlag (±50 ms)
    excluded_strong: float  # Anteil der deutlichen Onsets in ausgeklammerten Bereichen
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Alignment:
    mapped_times: np.ndarray  # Audiozeit je Note aus Score.notes, NaN = nicht abbildbar
    excluded: list[tuple[float, float]]  # Audiozeit-Intervalle ohne Bewertung
    quality: Quality
    shift: float  # abgezogener systematischer Versatz (s)
    beat_factor: int  # Partitur-Beat = Viertel × 2**beat_factor


def read_score(path: Path) -> Score:
    """Drum-Noten (Kanal 10) und Viertel-Beats aus einem MIDI mit Tempokarte."""
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


def _beat_grid(score: Score, audio_beats: np.ndarray) -> tuple[np.ndarray, int]:
    """Partitur-Beats auf die Ebene bringen, die Beat This! hört (halbes/doppeltes Tempo)."""
    ratio = np.median(np.diff(audio_beats)) / np.median(np.diff(score.beats))
    k = int(np.clip(np.round(np.log2(ratio)), -1, 1))
    if k == 1:
        return score.beats[::2], k
    if k == -1:
        mids = (score.beats[:-1] + score.beats[1:]) / 2
        return np.sort(np.concatenate([score.beats, mids])), k
    return score.beats, k


def _score_features(notes: list[tuple[float, int]], beats: np.ndarray) -> np.ndarray:
    """Slots sind auf die Rasterpunkte zentriert: ein Schlag knapp vor dem Beat zählt zum Beat."""
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
    """Je Band auf das 99,5. Perzentil normiert (seltene Schläge wie Kick auf 1 und 3 liegen
    über dem 95. Perzentil); Slot-Fenster zentriert auf die Rasterpunkte wie bei den Noten."""
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
    """Gepaarte Beats (i Noten, j Audio) entlang des günstigsten Pfads.

    Drei Zustände: M = beide Seiten gehen einen Beat weiter (Kosten aus dem Muster),
    X = nur die Noten (Beat fehlt im Audio), Y = nur das Audio (Beat fehlt in den Noten).
    Ränder: Beats vor dem ersten bzw. nach dem letzten Paar kosten EDGE_SKIP je Beat."""
    n, m = cost.shape
    inf = np.inf
    big_m, big_x, big_y = (np.full((n + 1, m + 1), inf) for _ in range(3))
    big_m[0, 0] = 0.0
    big_x[1:, 0] = np.arange(1, n + 1) * EDGE_SKIP
    big_y[0, 1:] = np.arange(1, m + 1) * EDGE_SKIP
    ptr_m = np.zeros((n + 1, m + 1), dtype=np.int8)  # Vorgänger-Zustand 0=M, 1=X, 2=Y
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
        for j in range(1, m + 1):  # Y hängt von Y[i, j-1] ab: sequentiell
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
    """Gepaarte Beat-Grenzen je Abschnitt (beide Seiten lückenlos) lokal linear glätten.
    Ergebnis: Partitur-Beat-Index → (Audiozeit, Abschnitts-Nr.)."""
    runs: list[list[tuple[int, int]]] = []
    for i, j in pairs:
        if runs and runs[-1][-1] == (i - 1, j - 1):
            runs[-1].append((i, j))
        else:
            runs.append([(i, j)])
    mapping = {}
    for r, run in enumerate(runs):
        pts = [*run, (run[-1][0] + 1, run[-1][1] + 1)]  # Intervall i deckt Grenzen i und i+1
        xs, ys = np.array([sb[i] for i, _ in pts]), np.array([ab[j] for _, j in pts])
        for k, (i, _) in enumerate(pts):
            near = np.abs(xs - xs[k]) <= SMOOTH
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
    """Legt die Noten auf die Aufnahme und prüft die Güte (siehe Moduldoku).
    `exclude`: zusätzliche, von Hand ausgeklammerte Audiozeit-Intervalle."""
    sb, factor = _beat_grid(score, np.asarray(audio_beats))
    ab = np.asarray(audio_beats)
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
    # Grenzen um die Onset-Toleranz nach innen: Noten auf dem ersten/letzten gepaarten Beat
    # gehören zum bewerteten Teil, auch wenn der Versatzabzug sie ein paar ms verschiebt.
    excluded = [
        (a + ONSET_TOL if a > 0 else a, b - ONSET_TOL)
        for a, b in _merge(excluded)
        if b - a > 2 * ONSET_TOL
    ]
    excluded = _merge([*excluded, *exclude])

    playing = [i for i in range(len(fs)) if fs[i].any()]
    pair_of = dict(pairs)
    fit = sum(
        1
        for i in playing
        if i in pair_of and i in mapping and abs(mapping[i][0] - ab[pair_of[i]]) <= BEAT_TOL
    )

    ref = np.unique(np.round(mapped[~np.isnan(mapped)], 3))
    ref = ref[~_inside(ref, excluded)]
    if len(ref):
        ref = ref[np.concatenate([[True], np.diff(ref) > onsets.MIN_GAP])]
    strong_in = _inside(strong_t, excluded)
    strong_out = strong_t[~strong_in]
    quality_vals = {
        "beat_fit": _fraction(fit, len(playing)),
        "coverage": _fraction(len(match_events(ref, onset_t, ONSET_TOL)), len(ref)),
        "explained": _fraction(len(match_events(ref, strong_out, ONSET_TOL)), len(strong_out)),
        "excluded_strong": _fraction(int(strong_in.sum()), len(strong_t)),
    }
    reasons = [
        f"{name} = {value:.3f} (Grenze {'≤' if name == 'excluded_strong' else '≥'} "
        f"{THRESHOLDS[name]})"
        for name, value in quality_vals.items()
        if (value > THRESHOLDS[name] if name == "excluded_strong" else value < THRESHOLDS[name])
    ]
    return Alignment(
        mapped_times=mapped,
        excluded=excluded,
        quality=Quality(**quality_vals, reasons=reasons),
        shift=shift,
        beat_factor=factor,
    )
