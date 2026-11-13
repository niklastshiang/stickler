"""Voting across pipelines: a hit counts if at least `min_agree` of the pipelines detect it.

Per class of the 5-class scheme, all pipelines' onsets are sorted and grouped: a group starts
at an onset and takes every onset up to WINDOW later. A group with onsets from at least
`min_agree` different pipelines yields one hit at the median of their times (one onset per
pipeline), with the group's most common pitch. Different models make partly independent
errors, so agreement filters false hits that a single model produces.

    votes:
      v2of3:
        pipelines: [none+adtof, demucs+muscriptor_m, roformer+adtof]
        min_agree: 2

Scored as separator "vote", transcriber = the vote's name; usable in combos as "vote+<name>".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from stickler.classes import Scheme
from stickler.runner import Record

VOTE_SEPARATOR = "vote"
WINDOW = 0.03  # seconds; within the ±50 ms scoring tolerance

Pipeline = tuple[str, str]


@dataclass(frozen=True)
class Vote:
    name: str
    pipelines: tuple[Pipeline, ...]
    min_agree: int


def parse_votes(raw: Mapping | None) -> list[Vote]:
    out = []
    for name, spec in (raw or {}).items():
        pipes = []
        for item in spec.get("pipelines", []):
            parts = str(item).split("+")
            if len(parts) != 2:
                raise ValueError(f"vote {name}: expected 'separator+transcriber', got {item!r}")
            pipes.append((parts[0], parts[1]))
        k = int(spec.get("min_agree", 0))
        if not 1 <= k <= len(pipes):
            raise ValueError(f"vote {name}: min_agree must be between 1 and {len(pipes)}")
        out.append(Vote(str(name), tuple(pipes), k))
    return out


def vote(
    sources: Sequence[Sequence[tuple[float, int]]], *, min_agree: int, scheme: Scheme
) -> list[tuple[float, int]]:
    out: list[tuple[float, int]] = []
    for cls in scheme.classes:
        events = sorted(
            (t, i, p)
            for i, notes in enumerate(sources)
            for t, p in notes
            if scheme.class_of(p) == cls
        )
        j = 0
        while j < len(events):
            start = events[j][0]
            k = j
            while k < len(events) and events[k][0] - start <= WINDOW:
                k += 1
            group = events[j:k]
            first: dict[int, float] = {}
            for t, i, _ in group:
                first.setdefault(i, t)
            if len(first) >= min_agree:
                pitch = Counter(p for _, _, p in group).most_common(1)[0][0]
                out.append((float(np.median(list(first.values()))), pitch))
            j = k
    return sorted(out)


def vote_records(
    records: Sequence[Record],
    votes: Sequence[Vote],
    scheme: Scheme,
    read_notes: Callable[[Path], list[tuple[float, int]]],
) -> list[Record]:
    """One record per vote and track that has at least one of the vote's pipelines."""
    index = {(r.dataset, r.track, r.separator, r.transcriber): r for r in records}
    tracks = list(dict.fromkeys((r.dataset, r.track) for r in records))
    out = []
    for v in votes:
        for dataset, track in tracks:
            parts = [index.get((dataset, track, *p)) for p in v.pipelines]
            if not any(parts):
                continue
            bad = [
                "+".join(p) for p, r in zip(v.pipelines, parts, strict=True) if not r or not r.ok
            ]
            notes, error = None, None
            if bad:
                error = f"missing or failed part: {', '.join(bad)}"
            else:
                sources = [r.notes if r.notes is not None else read_notes(r.midi) for r in parts]
                notes = tuple(vote(sources, min_agree=v.min_agree, scheme=scheme))
            present = [r for r in parts if r is not None]
            seps = {r.separator: (r.separator_meta or {}) for r in present}
            out.append(
                Record(
                    dataset,
                    track,
                    VOTE_SEPARATOR,
                    v.name,
                    None,
                    None,
                    {"seconds": sum(m.get("seconds", 0.0) for m in seps.values())},
                    {
                        "seconds": sum(
                            (r.transcriber_meta or {}).get("seconds", 0.0) for r in present
                        )
                    },
                    error,
                    notes,
                )
            )
    return out
