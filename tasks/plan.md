# Implementation Plan: Stickler

## Overview
Stickler compares pipelines of drum-stem separation and drum transcription on MDB Drums, later ENST, and on your own songs. The best pipeline produces MusicXML. The basis is [SPEC.md](../SPEC.md); the quality limits are in [CONSTRAINTS.md](../CONSTRAINTS.md). The tasks are in [todo.md](todo.md).

## Architecture Decisions
- **Adapters as subprocesses with their own uv environment:** The models have incompatible dependencies (Torch versions, ROCm vs. CPU). The harness never imports model code; it only communicates with them via files (`drums.wav`, `drums.mid`, `beats.json`, `meta.json`).
- **Library API first:** `stickler.api` contains all the logic; the CLI is a thin layer. This way the later GTK interface can use the same API.
- **Unified intermediate format `Onsets`:** Onset times per class (5-/3-class scheme). All references and model outputs are mapped onto it, and scoring is done only on it (`mir_eval.onset`, ±50 ms).
- **Cache key:** Hash of audio file, adapter ID, adapter version and device. A second run recomputes nothing.
- **Vertical slicing:** First, one combination (`none` × `adt_str`) runs end to end, from data to metric. Then candidates are added across the board.
- **Risky things early:** The ROCm GPU is tested right after the first vertical slice (task 6), before the other adapters.

## Phases (index; details in todo.md)
| Phase | Tasks | Result |
|---|---|---|
| 0 Docs | 0 | ADRs for decisions already made |
| 1 Vertical slice | 1–5 | `none` × `adt_str` on MDB → `metrics.csv` |
| 2 GPU | 6 | ROCm on gfx1152 works or is justifiably rejected (ADR) |
| 3 Candidates | 7–12 | full matrix on MDB |
| 4 Report & own songs | 13–16 | HTML report, alignment of own songs, ENST application |
| 5 Notes | 17–18 | `stickler notate` → MusicXML/PDF |
| 6 Later | – | noted for later: release pipeline (Flatpak, AppImage), everything in English |

## Release 3: Error analysis (approved 2026-11-14, SPEC.md "Release 3")
Goal: honest numbers for Fast and Quality on the own songs. Tasks 22–28 in [todo.md](todo.md), Phase 7.

Architecture decisions:
- **Same records as the benchmark:** the breakdown reuses the record building of
  `evaluate_benchmark` (combos included, excluded regions removed), extracted into one helper,
  so error counts and F1 can never disagree.
- **`errors.py` is pure** (onsets in, categories/sample/corrections out); file and audio
  handling live in `listen.py` and `api.py`. Easy to test without audio.
- **Drum stems only from the cache:** snippets use the cached Demucs stems (Quality computed
  them for all 25 songs); `listen` never starts a model.
- **Line input instead of raw keys** in `listen` (a letter plus Enter): no terminal raw mode,
  testable with CliRunner; the player command is injected, tests never play sound.
- **Sample before listening:** `sample.csv` is written once and never redrawn; verdicts are
  appended to `verdicts.csv`, so quitting and resuming loses nothing.

Order: categories (22) → `stickler errors` end to end (23) → snippets (24, perceptual risk,
early) → sample (25) → listening loop (26) → owner listens (Checkpoint F) → correction (27, can
be built while the owner listens, on synthetic verdicts) → report and release (28).

| Risk | Impact | Mitigation |
|------|--------|------------|
| Marker click masks or is mistaken for the hit | High | Snippet plays plain first, then with the marker; marker in a distinct timbre; owner tries 3 snippets before the sample is judged (Task 24) |
| Demucs stem bleed makes a "no" sound like "yes" | Medium | Mix and stem together in the snippet; *unclear* is a valid answer and reported |
| Few spots of a pipeline's own error set (Quality-only kick/snare/toms errors) | Medium | Report n per pipeline and class next to every corrected value; intervals by bootstrap |
| Many *unclear* answers | Medium | Bounds with *unclear* counted either way; share reported |

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| ROCm wheels for gfx1152 run unstably | Medium | CPU fallback remains mandatory. Compare channels 7.14 vs. 10.x in the spike; decision via ADR |
| YourMT3/ADTOF have no official CLI | Medium | Rebuild inference from the Space/notebook code; pin source and commit. If this fails: remove the candidate via ADR |
| MuScriptor is gated | Low | User logs in (agreed). `doctor` checks the login |
| MDB data is part of the training of individual models | Medium | Note in the report. The own songs count as the clean test |
| Alignment of own songs fails on beat errors | Medium | Click-check WAV for listening, manual anchor in the YAML file |
| CPU runtime of the full matrix | Low | Caching, overnight runs, GPU where possible |

## Prerequisites from the user
- By task 10: accept the MuScriptor license on Hugging Face and run `uvx hf auth login`.
- By task 15: rebuild at least one song from `Projekte/Schlagzeug` in MuseScore and export it as MIDI (repeats written out).
- Optional: submit the ENST application (draft from task 16).

## Open Questions
- none. The ROCm channel is decided in task 6.
