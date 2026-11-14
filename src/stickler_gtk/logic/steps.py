"""The rows of a step list (design screens 2 and 5): what each step of `stickler.api` is called
for a drummer, and what it does in a line."""

from __future__ import annotations

from dataclasses import dataclass, replace

from stickler import api
from stickler_gtk.i18n import N_, _

# step id → (label, what it does); the ids are api.Step.id
LABELS = {
    "separate": (N_("Separate the drums"), N_("Only the drum track, without the band")),
    "transcribe": (N_("Detect the hits"), N_("Kick, snare, toms, hi-hat, cymbals")),
    "beats": (N_("Find the beat and the bars"), N_("Tempo, time signature, the first “one”")),
    "engrave": (N_("Write the notes"), N_("Bars, repeats, beams")),
    "pdf": (N_("Make the PDF"), N_("To print or to read on a tablet")),
}
FAST = ("transcribe", "beats", "engrave")  # what Fast runs with pdf=False

# adapter id → the model's own name, as its authors write it
MODEL_NAMES = {
    "adtof": "ADTOF",
    "beat_this": "Beat This!",
    "demucs": "Demucs",
    "roformer": "BS-RoFormer",
    "muscriptor_m": "MuScriptor",
    "muscriptor_s": "MuScriptor",
    "adt_str": "ADT_STR",
}


def model_name(adapter: str) -> str:
    return MODEL_NAMES.get(adapter, adapter)


@dataclass(frozen=True)
class StepRow:
    id: str
    label: str
    detail: str
    state: str = "waiting"  # "waiting", "running" or "done"


def row(step_id: str, state: str = "waiting") -> StepRow:
    label, detail = LABELS.get(step_id, (step_id, ""))
    return StepRow(step_id, _(label) if label else "", _(detail) if detail else "", state)


def planned(ids: tuple[str, ...]) -> tuple[StepRow, ...]:
    return tuple(row(step_id) for step_id in ids)


def report(rows: tuple[StepRow, ...], step: api.Step) -> tuple[StepRow, ...]:
    """The rows after a progress report; a step the plan did not expect is added."""
    state = "running" if step.state == "started" else "done"
    current = list(rows)
    while len(current) < step.index:
        current.append(row(step.id))
    if current[step.index - 1].id != step.id:
        current[step.index - 1] = row(step.id)
    current[step.index - 1] = replace(current[step.index - 1], state=state)
    return tuple(current)
