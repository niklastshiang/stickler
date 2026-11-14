"""Badges for `stickler listen` (SPEC.md, "Gamification of `stickler listen`").

Rule above all: the game must not bias the verdicts. Badges are computed from events that say
only *when* something happened and *what* (a spot judged, a spot replayed on purpose, a
session started), never what was answered. So no badge can reward yes, no or unclear, and
none rewards speed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# replay: the owner chose to hear a spot again or differently (r, l, s); the slow loop every
# spot starts with is not an event
EventKind = Literal["judged", "replay", "session"]


@dataclass(frozen=True)
class Event:
    when: datetime
    kind: EventKind


@dataclass(frozen=True)
class Badge:
    name: str
    line: str


BADGES = (
    Badge("first hit", "One down. The metronome believes in you."),
    Badge("warmed up", "Sticks warm, wrists loose, coffee cold."),
    Badge("quarter note", "A quarter of the way. Count it in: one, two, three, four."),
    Badge("neighbours: annoyed", "Halfway there. Someone just knocked on the wall."),
    Badge("three-quarter time", "Seventy-five down. Waltz the rest of the way."),
    Badge("encore", "Every spot judged. The crowd is screaming for the showdown."),
    Badge("night shift", "Judging drums after midnight. The neighbours are thrilled."),
    Badge("early bird", "Up before seven to listen to hi-hats. Respect."),
    Badge("second opinion", "Listened again. Measure twice, judge once."),
    Badge("loop pedal", "Ten replays. Your ears are a loop station now."),
    Badge("comeback tour", "Back on another day. The band is back together."),
)
MILESTONES = {  # spots judged → badge
    1: "first hit",
    10: "warmed up",
    25: "quarter note",
    50: "neighbours: annoyed",
    75: "three-quarter time",
}
REPLAYS_FOR_PEDAL = 10


def earned(events: Sequence[Event], total: int) -> dict[str, datetime]:
    """Badge name → when it was earned (the event that triggered it). `total`: spots in the
    sample, for `encore`."""
    got: dict[str, datetime] = {}

    def award(name: str, when: datetime) -> None:
        got.setdefault(name, when)

    judged = replays = 0
    session_days: list = []
    for e in sorted(events, key=lambda e: e.when):
        if e.kind == "judged":
            judged += 1
            if judged in MILESTONES:
                award(MILESTONES[judged], e.when)
            if judged == total:
                award("encore", e.when)
            if e.when.hour < 5:
                award("night shift", e.when)
            elif e.when.hour < 7:
                award("early bird", e.when)
        elif e.kind == "replay":
            replays += 1
            if replays == 1:
                award("second opinion", e.when)
            if replays == REPLAYS_FOR_PEDAL:
                award("loop pedal", e.when)
        elif e.kind == "session":
            if session_days and e.when.date() > max(session_days):
                award("comeback tour", e.when)
            session_days.append(e.when.date())
    return got


def banner(badge: Badge) -> str:
    title = f"BADGE UNLOCKED: {badge.name}"
    width = max(len(title), len(badge.line)) + 4
    return "\n".join(
        [
            "╔" + "═" * width + "╗",
            "║  " + title.ljust(width - 2) + "║",
            "║  " + badge.line.ljust(width - 2) + "║",
            "╚" + "═" * width + "╝",
        ]
    )


def collection(got: dict[str, datetime]) -> str:
    """The badges earned so far; the others stay a mystery."""
    lines = [f"Badges: {sum(b.name in got for b in BADGES)} of {len(BADGES)}"]
    lines += [f"  ✓ {b.name}" if b.name in got else "  · ???" for b in BADGES]
    return "\n".join(lines)


# --- The finale: Fast against Quality, once every spot is judged ---------------------------

PIPELINE_NAMES = {"none+adtof": "Fast", "combo+quality": "Quality"}
DRUMS = {"KD": "kick", "SD": "snare", "TT": "toms", "HH": "hi-hat", "CY": "cymbals"}
TIE = 0.0005  # equal at three decimals


def showdown(rows: Sequence[dict]) -> str:
    """The showdown from corrected.csv rows (stickler.errors.correct per pipeline and class):
    measured and corrected macro-F1 per pipeline, the winner per drum and overall."""
    pipes = list(dict.fromkeys(r["pipeline"] for r in rows))
    by = {(r["pipeline"], r["class"]): r for r in rows}

    def name(p: str) -> str:
        return PIPELINE_NAMES.get(p, p)

    def winner(cls: str) -> tuple[str, float]:
        values = {p: by[(p, cls)]["corrected"] for p in pipes}
        best = max(values.values())
        top = [p for p in pipes if best - values[p] < TIE]
        runner_up = max((v for p, v in values.items() if p not in top), default=best)
        return ("tie" if len(top) > 1 else name(top[0])), best - runner_up

    lines = [
        "╔══════════════════════════════╗",
        "║        THE SHOWDOWN          ║",
        "╚══════════════════════════════╝",
        "  " + "  vs  ".join(name(p) for p in pipes),
        "",
        f"  {'':9}{'measured':>9}{'corrected':>11}   95 % interval   unclear answers",
    ]
    for p in pipes:
        m = by[(p, "macro")]
        lines.append(
            f"  {name(p):9}{m['measured']:9.3f}{m['corrected']:11.3f}   "
            f"{m['low']:.3f}–{m['high']:.3f}     {m['unclear']} of {m['n_ref'] + m['n_est']}"
        )
    lines += ["", "  Round by round (corrected F1):"]
    for cls, drum in DRUMS.items():
        if all((p, cls) in by for p in pipes):
            who, _ = winner(cls)
            scores = " vs ".join(f"{by[(p, cls)]['corrected']:.3f}" for p in pipes)
            lines.append(f"    {drum:9}{who:9}({scores})")
    who, margin = winner("macro")
    lines.append("")
    if who == "tie":
        lines.append("  It's a tie. Split the drum solo.")
    else:
        lines.append(f"  And the winner is: {who} (+{margin:.3f} corrected macro-F1). Encore!")
    lines.append("  (All numbers: stickler report → results/report.html)")
    return "\n".join(lines)
