"""Drum notation: quantize hits to the beat grid and write MusicXML.

- Grid per beat: sixteenths by default, eighth-note triplets only when they fit clearly better.
  A hit just before a beat belongs to that beat.
- Staff positions follow common drum notation (as used by MuseScore's drumset): hands in
  voice 1 (stems up), feet in voice 2 (stems down), cymbals with x noteheads.
- MusicXML is written with the standard library, durations in twelfths of a quarter so that
  sixteenths (3) and triplet eighths (4) are both exact.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape

import numpy as np

DIVISIONS = 12  # per quarter note: 16th = 3, triplet 8th = 4
GRIDS = (4, 3)  # sixteenths, eighth-note triplets
TRIPLET_ADVANTAGE = 0.5  # triplets must halve the timing error to be chosen


@dataclass(frozen=True)
class Staff:
    step: str
    octave: int
    notehead: str  # MusicXML notehead value
    voice: int  # 1 = hands (stems up), 2 = feet (stems down)


_KICK = Staff("F", 4, "normal", 2)
_SNARE = Staff("C", 5, "normal", 1)
_FLOOR_TOM = Staff("A", 4, "normal", 1)
_MID_TOM = Staff("D", 5, "normal", 1)
_HIGH_TOM = Staff("E", 5, "normal", 1)
_CRASH = Staff("A", 5, "x", 1)
_RIDE = Staff("F", 5, "x", 1)
STAFF: dict[int, Staff] = {
    35: _KICK,
    36: _KICK,
    37: Staff("C", 5, "x", 1),  # side stick
    38: _SNARE,
    40: _SNARE,
    41: _FLOOR_TOM,
    43: _FLOOR_TOM,
    45: _MID_TOM,
    47: _MID_TOM,
    48: _HIGH_TOM,
    50: _HIGH_TOM,
    42: Staff("G", 5, "x", 1),  # closed hi-hat
    44: Staff("D", 4, "x", 2),  # pedal hi-hat
    46: Staff("G", 5, "circle-x", 1),  # open hi-hat
    49: _CRASH,
    57: _CRASH,
    51: _RIDE,
    59: _RIDE,
    53: Staff("F", 5, "diamond", 1),  # ride bell
    52: Staff("C", 6, "x", 1),  # china
    55: Staff("B", 5, "x", 1),  # splash
}
OTHER = Staff("B", 4, "triangle", 1)  # percussion without a standard drum-kit position


@dataclass(frozen=True, order=True)
class QNote:
    beat: int  # index of the beat interval
    position: tuple[int, int]  # (slot, slots per beat), e.g. (2, 4) = the "and"
    pitch: int
    velocity: int


def _grid(fracs: list[float]) -> int:
    def error(g: int) -> float:
        return float(np.mean([abs(f - round(f * g) / g) for f in fracs]))

    return 3 if error(3) < TRIPLET_ADVANTAGE * error(4) else 4


def quantize(
    notes: list[tuple[float, int, int]], beats: list[float], min_velocity: int = 0
) -> list[QNote]:
    """(time, pitch, velocity) → hits on the beat grid. Hits outside the grid or quieter than
    `min_velocity` are dropped; the same drum twice on one slot keeps the louder hit."""
    b = np.asarray(beats, dtype=float)
    n_beats = len(b) - 1
    per_beat: dict[int, list[tuple[float, int, int]]] = {}
    for t, pitch, velocity in notes:
        i = int(np.searchsorted(b, t, side="right")) - 1
        if i == -1 and n_beats and b[0] - t <= (b[1] - b[0]) / (2 * GRIDS[0]):
            i = 0  # a hair before the first beat (beat tracker set it slightly late)
        if velocity < min_velocity or not 0 <= i < n_beats:
            continue
        per_beat.setdefault(i, []).append(((t - b[i]) / (b[i + 1] - b[i]), pitch, velocity))
    grid = {i: _grid([f for f, _, _ in hits]) for i, hits in per_beat.items()}
    best: dict[tuple[int, tuple[int, int], int], int] = {}
    for i, hits in per_beat.items():
        g = grid[i]
        for frac, pitch, velocity in hits:
            slot, beat = round(frac * g), i
            if slot == g:  # just before the next beat
                beat, slot = i + 1, 0
                if beat >= n_beats:
                    continue
            key = (beat, (slot, grid.get(beat, g) if slot == 0 else g), pitch)
            best[key] = max(velocity, best.get(key, 0))
    return sorted(QNote(beat, pos, pitch, vel) for (beat, pos, pitch), vel in best.items())


def _nearest_index(beats: np.ndarray, t: float) -> int:
    return int(np.argmin(np.abs(beats - t)))


def time_signature(beats: list[float], downbeats: list[float]) -> tuple[int, int]:
    """Beats per bar (most common distance between downbeats) over a quarter note."""
    b = np.asarray(beats, dtype=float)
    idx = [_nearest_index(b, d) for d in downbeats]
    gaps = [j - i for i, j in zip(idx, idx[1:], strict=False) if j > i]
    return (Counter(gaps).most_common(1)[0][0] if gaps else 4), 4


_TYPES = {
    3: ("16th", 0),
    6: ("eighth", 0),
    9: ("eighth", 1),
    12: ("quarter", 0),
    24: ("half", 0),
    36: ("half", 1),
    48: ("whole", 0),
}
_TRIPLET_TYPES = {4: "eighth", 8: "quarter"}


def _note_xml(
    staff: Staff | None,
    duration: int,
    triplet: bool,
    *,
    chord: bool = False,
    ghost: bool = False,
    tuplet: str | None = None,
    voice: int = 1,
    instrument: str | None = None,
) -> str:
    parts = ["<note>"]
    if chord:
        parts.append("<chord/>")
    if staff is None:
        parts.append("<rest/>")
    else:
        parts.append(
            f"<unpitched><display-step>{staff.step}</display-step>"
            f"<display-octave>{staff.octave}</display-octave></unpitched>"
        )
    parts.append(f"<duration>{duration}</duration>")
    if instrument:
        parts.append(f'<instrument id="{instrument}"/>')
    parts.append(f"<voice>{voice}</voice>")
    if triplet and duration in _TRIPLET_TYPES:
        parts.append(f"<type>{_TRIPLET_TYPES[duration]}</type>")
        parts.append(
            "<time-modification><actual-notes>3</actual-notes>"
            "<normal-notes>2</normal-notes></time-modification>"
        )
    else:
        kind, dots = _TYPES[duration]
        parts.append(f"<type>{kind}</type>" + "<dot/>" * dots)
    if staff is not None:
        parts.append(f"<stem>{'up' if voice == 1 else 'down'}</stem>")
        paren = ' parentheses="yes"' if ghost else ""
        parts.append(f"<notehead{paren}>{staff.notehead}</notehead>")
    if tuplet:
        parts.append(f'<notations><tuplet type="{tuplet}"/></notations>')
    parts.append("</note>")
    return "".join(parts)


def _measure_rest_xml(beats: int, voice: int = 1) -> str:
    return (
        f'<note><rest measure="yes"/><duration>{beats * DIVISIONS}</duration>'
        f"<voice>{voice}</voice></note>"
    )


def _voice_xml(
    bar: list[int], hits: dict[int, list[QNote]], voice: int, ghost: int, merge_halves: bool
) -> list[str]:
    """One voice of one bar. Two empty beats that form half of a bar (beats 1-2 or 3-4 of an
    even meter) become one half rest instead of two quarter rests."""
    out: list[str] = []
    k = 0
    while k < len(bar):
        pair = merge_halves and k % 2 == 0 and k + 1 < len(bar)
        if pair and not hits.get(bar[k]) and not hits.get(bar[k + 1]):
            out.append(_note_xml(None, 2 * DIVISIONS, False, voice=voice))
            k += 2
            continue
        out.extend(_beat_xml(hits.get(bar[k], []), voice, ghost))
        k += 1
    return out


def _beat_xml(hits: list[QNote], voice: int, ghost_velocity: int) -> list[str]:
    """One beat of one voice: rests and chords that add up to a quarter note."""
    if not hits:
        return [_note_xml(None, DIVISIONS, False, voice=voice)]
    g = hits[0].position[1]
    unit = DIVISIONS // g
    slots = sorted({h.position[0] for h in hits})
    items: list[tuple[int, list[QNote]]] = []
    if slots[0] > 0:
        items.append((slots[0] * unit, []))
    for k, slot in enumerate(slots):
        end = slots[k + 1] if k + 1 < len(slots) else g
        items.append(((end - slot) * unit, [h for h in hits if h.position[0] == slot]))
    triplet = g == 3 and len(items) > 1
    out = []
    for n, (duration, chord) in enumerate(items):
        tuplet = None
        if triplet and n == 0:
            tuplet = "start"
        elif triplet and n == len(items) - 1:
            tuplet = "stop"
        if not chord:
            out.append(_note_xml(None, duration, triplet, voice=voice, tuplet=tuplet))
            continue
        for c, h in enumerate(sorted(chord, key=lambda h: h.pitch)):
            out.append(
                _note_xml(
                    STAFF.get(h.pitch, OTHER),
                    duration,
                    triplet,
                    chord=c > 0,
                    ghost=h.velocity < ghost_velocity,
                    tuplet=tuplet if c == 0 else None,
                    voice=voice,
                    instrument=f"P1-I{h.pitch}",
                )
            )
    return out


@dataclass(frozen=True)
class _Measure:
    implicit: bool  # pickup bar
    empty: bool  # no hits at all
    meta: str  # attributes and tempo (first bar, multi-measure rests)
    content: str  # the voices' notes and rests


MAX_PHRASE = 8  # longest phrase (in bars) that repeat signs enclose


def _repeat_blocks(measures: list[_Measure]) -> list[tuple[int, int, int]]:
    """(first bar, phrase length, times) covering all bars in order: at every bar, the phrase
    that saves the most bars when written once between repeat signs (none for empty bars,
    the pickup bar, or bars with attributes other than the first one)."""
    blocks, k = [], 0
    usable = [not m.implicit and not m.empty for m in measures]
    while k < len(measures):
        best = (1, 1, 0)  # length, times, bars saved
        for length in range(1, MAX_PHRASE + 1):
            phrase = measures[k : k + length]
            if len(phrase) < length or not all(usable[k : k + length]):
                break
            if any(m.meta for m in phrase[1:]):
                break
            times = 1
            while True:
                nxt = measures[k + times * length : k + (times + 1) * length]
                ok = len(nxt) == length and all(
                    usable[k + times * length : k + (times + 1) * length]
                )
                if not ok or [m.content for m in nxt] != [m.content for m in phrase]:
                    break
                if any(m.meta for m in nxt):
                    break
                times += 1
            saved = length * (times - 1)
            if saved > best[2]:
                best = (length, times, saved)
        length, times, _ = best
        blocks.append((k, length, times))
        k += length * times
    return blocks


@dataclass(frozen=True)
class BarLayout:
    bars: list[list[int]]  # beat indices per bar, in order
    pickup: int  # beats of the pickup bar before the first downbeat (0: none)
    num: int  # time signature
    den: int


def bar_layout(beats: list[float], downbeats: list[float]) -> BarLayout:
    """Bars start at the downbeats; beats before the first downbeat form a pickup bar (and full
    bars before it, if there are enough)."""
    b = np.asarray(beats, dtype=float)
    num, den = time_signature(beats, downbeats)
    first = _nearest_index(b, downbeats[0]) if len(downbeats) else 0
    n_beats = len(b) - 1
    pickup = first % num
    bars = ([list(range(first - pickup, first))] if pickup else []) + [
        list(range(s, s + num)) for s in range(first, n_beats, num)
    ]
    if first - pickup > 0:  # full bars before the first downbeat
        bars = [list(range(s, s + num)) for s in range(0, first - pickup, num)] + bars
    return BarLayout(bars, pickup, num, den)


# Simplification for readability: bars that differ in only a few hits get the pattern most of
# them share (a missed hi-hat or a stray ghost note is mostly noise); bars that fit no group
# (fills, crashes at section starts) stay as they are. Measured as "@simple" (stickler.grid) on
# 2026-11-13, macro-F1 against the plain grid, and written bars of the 25 own songs (Fast mode,
# with repeat signs; 3354 written out, 3042 with repeat signs alone):
#   similarity 0.6: own -0.012, ENST -0.022, 2023 bars
#   similarity 0.8: own +-0.000, ENST -0.003, 2594 bars (chosen by the owner)
#   similarity 0.9: own +-0.000, ENST -0.001, 2889 bars
SIMILARITY = 0.8  # Jaccard index of the hit patterns
MIN_GROUP = 3


def _key(n: QNote, start: int) -> tuple[int, int, int]:
    slot, per_beat = n.position
    return (n.beat - start, slot * DIVISIONS // per_beat, n.pitch)


def _beat_grid(slots: set[int]) -> int | None:
    """Slots per beat for positions given in DIVISIONS: 3 if the beat has triplet eighths,
    4 for sixteenths, None if it mixes both."""
    if all(s % (DIVISIONS // 3) == 0 for s in slots) and any(s for s in slots):
        return 3
    if all(s % (DIVISIONS // 4) == 0 for s in slots):
        return 4
    return None


def _similarity(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def simplify(
    notes: list[QNote],
    bars: list[list[int]],
    *,
    similarity: float = SIMILARITY,
    min_group: int = MIN_GROUP,
    n_beats: int | None = None,
) -> list[QNote]:
    """Groups similar bars of equal length and gives every bar of a group with at least
    `min_group` bars the group's majority pattern (hits at least half of its bars have).
    `n_beats`: number of beat intervals; nothing is added at or beyond it (the last bar may
    reach past the tracked beats)."""
    in_bar: dict[int, list[QNote]] = {k: [] for k in range(len(bars))}
    bar_of = {beat: k for k, bar in enumerate(bars) for beat in bar}
    outside = []
    for n in notes:
        (in_bar[bar_of[n.beat]] if n.beat in bar_of else outside).append(n)
    keys = [frozenset(_key(n, bars[k][0]) for n in in_bar[k]) for k in range(len(bars))]

    groups: list[list[int]] = []
    reps: list[frozenset] = []

    def majority(members: list[int]) -> frozenset:
        counts: dict = {}
        for k in members:
            for key in keys[k]:
                counts[key] = counts.get(key, 0) + 1
        return frozenset(key for key, c in counts.items() if 2 * c >= len(members))

    for _ in range(2):  # assign, then reassign against the settled patterns
        assigned: list[list[int]] = [[] for _ in reps]
        for k in range(len(bars)):
            if not keys[k]:
                continue
            best, score = None, similarity
            for g, rep in enumerate(reps):
                same_length = len(bars[groups[g][0]]) == len(bars[k]) if groups[g] else True
                s = _similarity(keys[k], rep)
                if same_length and s >= score:
                    best, score = g, s
            if best is None:
                reps.append(keys[k])
                groups.append([k])
                assigned.append([k])
            else:
                assigned[best].append(k)
        groups = [g for g in assigned if g]
        reps = [majority(g) for g in groups]

    out = list(outside)
    for g, rep in zip(groups, reps, strict=True):
        velocity: dict[tuple[int, int, int], list[int]] = {}
        for other in g:
            for n in in_bar[other]:
                velocity.setdefault(_key(n, bars[other][0]), []).append(n.velocity)
        slots_of: dict[int, set[int]] = {}
        for beat, slot, _ in rep:
            slots_of.setdefault(beat, set()).add(slot)
        grids = {beat: _beat_grid(slots) for beat, slots in slots_of.items()}
        for k in g:
            if len(g) < min_group:
                out.extend(in_bar[k])
                continue
            start = bars[k][0]
            # a beat whose majority mixes sixteenths and triplets keeps the bar's own hits
            out.extend(n for n in in_bar[k] if grids.get(n.beat - start, 4) is None)
            for beat, slot, pitch in sorted(rep):
                if (grid := grids[beat]) is None or (
                    n_beats is not None and start + beat >= n_beats
                ):
                    continue
                vels = sorted(velocity[(beat, slot, pitch)])
                unit = DIVISIONS // grid
                out.append(QNote(start + beat, (slot // unit, grid), pitch, vels[len(vels) // 2]))
    out.extend(n for k in range(len(bars)) if not keys[k] for n in in_bar[k])
    return sorted(out)


def to_musicxml(
    notes: list[tuple[float, int, int]],
    beats: list[float],
    downbeats: list[float],
    *,
    title: str = "",
    artist: str = "",
    min_velocity: int = 0,
    ghost_velocity: int = 0,
    simplify_bars: bool = False,
    repeats: bool = False,
) -> str:
    """MusicXML (partwise 4.0) with one percussion staff. Bars start at the downbeats;
    beats before the first downbeat form a pickup bar. For readability, `simplify_bars` gives
    similar bars their common pattern (see simplify) and `repeats` writes runs of equal bars or
    phrases once, between repeat signs."""
    q = quantize(notes, beats, min_velocity)
    b = np.asarray(beats, dtype=float)
    layout = bar_layout(beats, downbeats)
    bars, pickup, num, den = layout.bars, layout.pickup, layout.num, layout.den
    if simplify_bars:
        q = simplify(q, bars, n_beats=len(beats) - 1)
    by_voice: dict[tuple[int, int], list[QNote]] = {}
    for n in q:
        by_voice.setdefault((STAFF.get(n.pitch, OTHER).voice, n.beat), []).append(n)
    # average beat over the song: Beat This! rounds single beats to its 20 ms frame grid
    tempo = round(60.0 * (len(b) - 1) / float(b[-1] - b[0])) if len(b) > 1 else 120
    used = sorted({n.pitch for n in q})

    # Readability: an empty bar is one whole-bar rest, a run of them one multi-measure rest
    implicit_first = pickup > 0
    empty = [
        not (m == 0 and implicit_first) and not any((v, i) in by_voice for v in (1, 2) for i in bar)
        for m, bar in enumerate(bars)
    ]
    multi_rest: dict[int, int] = {}
    m = 0
    while m < len(bars):
        run = 0
        while m + run < len(bars) and empty[m + run]:
            run += 1
        if run >= 2:
            multi_rest[m] = run
        m += max(run, 1)

    measures = []
    for m, bar in enumerate(bars):
        implicit = m == 0 and pickup > 0
        body = []
        attributes = ""
        if m == 0:
            attributes += (
                f"<divisions>{DIVISIONS}</divisions><key><fifths>0</fifths></key>"
                f"<time><beats>{num}</beats><beat-type>{den}</beat-type></time>"
                "<clef><sign>percussion</sign><line>2</line></clef>"
            )
        if m in multi_rest:
            attributes += (
                f"<measure-style><multiple-rest>{multi_rest[m]}</multiple-rest></measure-style>"
            )
        if attributes:
            body.append(f"<attributes>{attributes}</attributes>")
        if m == 0:
            body.append(
                '<direction placement="above"><direction-type><metronome>'
                f"<beat-unit>quarter</beat-unit><per-minute>{tempo}</per-minute>"
                f'</metronome></direction-type><sound tempo="{tempo}"/></direction>'
            )
        merge = den == 4 and num % 2 == 0 and not implicit
        meta = "".join(body)
        body = []
        for voice in (1, 2):
            hits = {i: by_voice[(voice, i)] for i in bar if (voice, i) in by_voice}
            if voice == 2:
                if not hits:
                    continue
                body.append(f"<backup><duration>{len(bar) * DIVISIONS}</duration></backup>")
            if not hits and not implicit:
                body.append(_measure_rest_xml(len(bar), voice))
                continue
            body.extend(_voice_xml(bar, hits, voice, ghost_velocity, merge))
        measures.append(_Measure(implicit, empty[m], meta, "".join(body)))
    blocks = _repeat_blocks(measures) if repeats else [(k, 1, 1) for k in range(len(measures))]
    out = []
    number = 0 if pickup else 1
    for start, length, times in blocks:
        for k in range(start, start + length):
            ms = measures[k]
            left = right = words = ""
            if times > 1 and k == start:
                left = '<barline location="left"><repeat direction="forward"/></barline>'
            if times > 1 and k == start + length - 1:
                right = (
                    '<barline location="right"><bar-style>light-heavy</bar-style>'
                    f'<repeat direction="backward" times="{times}"/></barline>'
                )
                if times > 2:
                    words = (
                        '<direction placement="above"><direction-type>'
                        f"<words>{times}×</words></direction-type></direction>"
                    )
            flag = ' implicit="yes"' if ms.implicit else ""
            out.append(
                f'<measure number="{number}"{flag}>{left}{ms.meta}{words}{ms.content}{right}'
                "</measure>"
            )
            number += 1

    instruments = "".join(
        f'<score-instrument id="P1-I{p}"><instrument-name>GM {p}</instrument-name>'
        "</score-instrument>"
        for p in used
    ) + "".join(
        f'<midi-instrument id="P1-I{p}"><midi-channel>10</midi-channel>'
        f"<midi-unpitched>{p + 1}</midi-unpitched></midi-instrument>"
        for p in used
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">\n'
        '<score-partwise version="4.0">'
        f"<work><work-title>{escape(title)}</work-title></work>"
        + (
            f'<identification><creator type="composer">{escape(artist)}</creator></identification>'
            if artist
            else ""
        )
        + '<part-list><score-part id="P1"><part-name>Drumset</part-name>'
        f"{instruments}</score-part></part-list>"
        f'<part id="P1">{"".join(out)}</part></score-partwise>\n'
    )
