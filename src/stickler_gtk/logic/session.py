"""What the window shows, as states that change only through these functions (pure; the
widgets draw the current state). Each analysis has a job number: reports of a job that was
cancelled or replaced change nothing."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

from stickler import api
from stickler_gtk.i18n import _
from stickler_gtk.logic import analysis, steps

_jobs = itertools.count(1)


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class Analysing:
    song: Path
    steps: tuple[steps.StepRow, ...]
    job: int
    previous: State  # where "Cancel" goes back to


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


@dataclass(frozen=True)
class Failed:
    song: Path
    kind: str  # "setup", "unreadable" or "analysis"
    title: str
    description: str
    details: str  # the command to run, or the technical message
    previous: State

    @property
    def can_retry(self) -> bool:
        return self.kind == "analysis"


State = Empty | Analysing | Result | Failed


def open_song(song: Path, previous: State) -> Analysing:
    if isinstance(previous, Analysing | Failed):
        previous = previous.previous
    return Analysing(song, steps.planned(steps.FAST), next(_jobs), previous)


def _current(state: State, job: int) -> bool:
    return isinstance(state, Analysing) and state.job == job


def on_step(state: State, job: int, step: api.Step) -> State:
    if not _current(state, job):
        return state
    return Analysing(state.song, steps.report(state.steps, step), job, state.previous)


def finished(state: State, job: int, info: api.SongInfo, notation: api.Notation) -> State:
    if not _current(state, job):
        return state
    return Result(state.song, info, notation)


def cancel(state: State) -> State:
    return state.previous if isinstance(state, Analysing) else state


def failed(state: State, job: int, error: BaseException) -> State:
    if not _current(state, job):
        return state
    if isinstance(error, api.Cancelled):
        return state.previous
    name = state.song.name
    if isinstance(error, api.SetupMissing):
        models = ", ".join(steps.model_name(a) for a in error.adapters)
        commands = "\n".join(f"stickler setup --adapter {a}" for a in error.adapters)
        description = _(
            "Stickler needs these models before it can listen: {models}. "
            "Set them up once in a terminal:"
        ).format(models=models)
        return Failed(
            state.song, "setup", _("Models Not Set Up"), description, commands, state.previous
        )
    if isinstance(error, analysis.Unreadable):
        description = _("“{name}” cannot be read. Is it a complete sound file?").format(name=name)
        return Failed(
            state.song,
            "unreadable",
            _("Cannot Read This File"),
            description,
            str(error),
            state.previous,
        )
    description = _("Something went wrong while listening to “{name}”.").format(name=name)
    return Failed(
        state.song, "analysis", _("The Analysis Failed"), description, str(error), state.previous
    )


def retry(state: Failed) -> Analysing:
    return open_song(state.song, state.previous)
