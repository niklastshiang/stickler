"""What the window shows, as states that change only through these functions (pure; the
widgets draw the current state). Each analysis has a job number: reports of a job that was
cancelled or replaced change nothing."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from pathlib import Path

from stickler import api
from stickler_gtk.i18n import _
from stickler_gtk.logic import analysis, steps

_jobs = itertools.count(1)
DETECTED = api.Corrections()  # nothing corrected


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class Analysing:
    song: Path
    steps: tuple[steps.StepRow, ...]
    job: int
    previous: State  # where "Cancel" goes back to
    corrections: api.Corrections = DETECTED  # the song's stored ones


@dataclass(frozen=True)
class Pending:
    """A correction being notated: its job number and the values the controls show."""

    job: int
    corrections: api.Corrections


@dataclass(frozen=True)
class Result:
    song: Path
    info: api.SongInfo
    notation: api.Notation
    corrections: api.Corrections = DETECTED  # what `notation` was made with
    pending: Pending | None = None

    @property
    def wanted(self) -> api.Corrections:
        """What the controls show: the newest change, even before its sheet is ready."""
        return self.pending.corrections if self.pending else self.corrections

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
class Exporting:
    """A drum track being separated and saved; "Cancel" goes back to the result."""

    song: Path
    steps: tuple[steps.StepRow, ...]
    job: int
    previous: Result
    dest: Path


@dataclass(frozen=True)
class Failed:
    song: Path
    kind: str  # "setup", "unreadable", "analysis" or "export"
    title: str
    description: str
    details: str  # the command to run, or the technical message
    previous: State

    @property
    def can_retry(self) -> bool:
        return self.kind == "analysis"


@dataclass(frozen=True)
class Consent:
    """Design screen 1: may the models be downloaded?"""

    missing: tuple[str, ...]  # the adapters not set up
    song: Path | None = None  # opened once they are


@dataclass(frozen=True)
class SettingUp:
    """Design screen 2: the models are downloaded."""

    steps: tuple[steps.StepRow, ...]
    job: int
    song: Path | None = None
    grown: int = 0  # bytes the running step has used so far


State = Empty | Analysing | Result | Exporting | Failed | Consent | SettingUp


def open_song(song: Path, previous: State, corrections: api.Corrections = DETECTED) -> Analysing:
    if isinstance(previous, Analysing | Exporting | Failed):
        previous = previous.previous
    return Analysing(song, steps.planned(steps.FAST), next(_jobs), previous, corrections)


def export_drums(result: Result, dest: Path, *, setup: bool) -> Exporting:
    """`setup`: the separator is downloaded first."""
    separator = api.DRUM_TRACK_SEPARATOR
    ids = (f"environment:{separator}", f"weights:{separator}") if setup else ()
    return Exporting(result.song, steps.planned((*ids, "separate")), next(_jobs), result, dest)


def _current(state: State, job: int) -> bool:
    return isinstance(state, Analysing | Exporting | SettingUp) and state.job == job


def consent(missing: tuple[str, ...], song: Path | None = None) -> Consent:
    return Consent(tuple(missing), song)


def start_setup(ids: tuple[str, ...], song: Path | None = None) -> SettingUp:
    return SettingUp(steps.planned(ids), next(_jobs), song)


def on_setup_step(state: State, job: int, step: api.Step) -> State:
    if not _current(state, job):
        return state
    return replace(state, steps=steps.report_by_id(state.steps, step), grown=0)


def setup_grew(state: State, job: int, grown: int) -> State:
    return replace(state, grown=grown) if _current(state, job) else state


def setup_done(state: State, job: int) -> State:
    """Set up: the empty window (the window then opens the song it was for, if any)."""
    return Empty() if _current(state, job) else state


def on_step(state: State, job: int, step: api.Step) -> State:
    if not _current(state, job):
        return state
    if isinstance(state, Exporting):
        return replace(state, steps=steps.report_by_id(state.steps, step))
    return replace(state, steps=steps.report(state.steps, step))


def exported(state: State, job: int) -> State:
    return state.previous if _current(state, job) else state


def finished(state: State, job: int, info: api.SongInfo, notation: api.Notation) -> State:
    if not _current(state, job):
        return state
    return Result(state.song, info, notation, state.corrections)


def correct(result: Result, corrections: api.Corrections) -> Result:
    """A change in the sidebar: the sheet stays until the new one is ready."""
    return replace(result, pending=Pending(next(_jobs), corrections))


def _correcting(state: State, job: int) -> bool:
    return isinstance(state, Result) and state.pending is not None and state.pending.job == job


def corrected(state: State, job: int, notation: api.Notation) -> State:
    """The newest correction's sheet; an older one finishing late changes nothing."""
    if not _correcting(state, job):
        return state
    return replace(state, notation=notation, corrections=state.pending.corrections, pending=None)


def correction_failed(state: State, job: int) -> State:
    """The last sheet stays, and so do the values it was made with."""
    return replace(state, pending=None) if _correcting(state, job) else state


def cancel(state: State) -> State:
    """What is done stays; a cancelled setup goes on at the next start."""
    if isinstance(state, SettingUp):
        return Empty()
    return state.previous if isinstance(state, Analysing | Exporting) else state


def failed(state: State, job: int, error: BaseException) -> State:
    if not _current(state, job):
        return state
    if isinstance(state, SettingUp):
        return Empty()  # Task 69: the page that names the server
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
    if isinstance(state, Exporting):
        description = _("Saving the drum track of “{name}” did not work.").format(name=name)
        return Failed(
            state.song, "export", _("The Export Failed"), description, str(error), state.previous
        )
    description = _("Something went wrong while listening to “{name}”.").format(name=name)
    return Failed(
        state.song, "analysis", _("The Analysis Failed"), description, str(error), state.previous
    )


def retry(state: Failed) -> Analysing:
    return open_song(state.song, state.previous)
