"""What the window shows, as states that change only through these functions (pure; the
widgets draw the current state)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stickler import api
from stickler_gtk.logic import steps


@dataclass(frozen=True)
class Empty:
    message: str | None = None  # why the last song did not work, shown once


@dataclass(frozen=True)
class Analysing:
    song: Path
    steps: tuple[steps.StepRow, ...]


@dataclass(frozen=True)
class Result:
    song: Path
    info: api.SongInfo
    notation: api.Notation

    @property
    def title(self) -> str:
        return self.info.title

    @property
    def subtitle(self) -> str:
        """Artist, tempo and meter for the header: the page cannot show the tempo mark."""
        num, den = self.notation.meter
        parts = [self.info.artist, f"♩ = {self.notation.tempo}", f"{num}/{den}"]
        return " · ".join(p for p in parts if p)


State = Empty | Analysing | Result


def open_song(song: Path) -> Analysing:
    return Analysing(song, steps.planned(steps.FAST))


def on_step(state: State, step: api.Step) -> State:
    if not isinstance(state, Analysing):
        return state
    return Analysing(state.song, steps.report(state.steps, step))


def finished(state: State, info: api.SongInfo, notation: api.Notation) -> Result:
    return Result(notation.transcription.audio, info, notation)


def failed(state: State, message: str) -> Empty:
    return Empty(message)
