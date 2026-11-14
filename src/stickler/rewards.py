"""Badges for `stickler listen` (SPEC.md, "Gamification of `stickler listen`").

Rule above all: the game must not bias the verdicts. Badges are computed from events that say
only *when* something happened and *what* (a spot judged, a loop played, a session started),
never what was answered. So no badge can reward yes, no or unclear, and none rewards speed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EventKind = Literal["judged", "loop", "slow_loop", "session"]


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
    Badge("slow motion", "Half speed, full concentration."),
    Badge("loop pedal", "Ten loops. Your ears are a loop station now."),
    Badge("comeback tour", "Back on another day. The band is back together."),
)
MILESTONES = {  # spots judged → badge
    1: "first hit",
    10: "warmed up",
    25: "quarter note",
    50: "neighbours: annoyed",
    75: "three-quarter time",
}
LOOPS_FOR_PEDAL = 10


def earned(events: Sequence[Event], total: int) -> dict[str, datetime]:
    """Badge name → when it was earned (the event that triggered it). `total`: spots in the
    sample, for `encore`."""
    got: dict[str, datetime] = {}

    def award(name: str, when: datetime) -> None:
        got.setdefault(name, when)

    judged = loops = 0
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
        elif e.kind in ("loop", "slow_loop"):
            loops += 1
            if e.kind == "slow_loop":
                award("slow motion", e.when)
            if loops == LOOPS_FOR_PEDAL:
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
