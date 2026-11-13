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


def to_musicxml(
    notes: list[tuple[float, int, int]],
    beats: list[float],
    downbeats: list[float],
    *,
    title: str = "",
    artist: str = "",
    min_velocity: int = 0,
    ghost_velocity: int = 0,
) -> str:
    """MusicXML (partwise 4.0) with one percussion staff. Bars start at the downbeats;
    beats before the first downbeat form a pickup bar."""
    q = quantize(notes, beats, min_velocity)
    b = np.asarray(beats, dtype=float)
    num, den = time_signature(beats, downbeats)
    first = _nearest_index(b, downbeats[0]) if len(downbeats) else 0
    n_beats = len(b) - 1
    starts = list(range(first, n_beats, num))
    pickup = first % num
    bars = ([list(range(first - pickup, first))] if pickup else []) + [
        list(range(s, s + num)) for s in starts
    ]
    if first - pickup > 0:  # full bars before the first downbeat
        bars = [list(range(s, s + num)) for s in range(0, first - pickup, num)] + bars
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
        number = 0 if implicit else (m if pickup else m + 1)
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
        flag = ' implicit="yes"' if implicit else ""
        measures.append(f'<measure number="{number}"{flag}>{"".join(body)}</measure>')

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
        f'<part id="P1">{"".join(measures)}</part></score-partwise>\n'
    )
