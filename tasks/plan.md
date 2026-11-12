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
