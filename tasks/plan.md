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
early) → sample (25) → listening loop (26) → badges (29, owner's wish: listening starts
only once they are in) → owner listens (Checkpoint F) → correction (27, can
be built while the owner listens, on synthetic verdicts) → finale (30) → report and release (28).

Gamification: rewards read an events log without answers, so they cannot bias the verdicts.

| Risk | Impact | Mitigation |
|------|--------|------------|
| Marker click masks or is mistaken for the hit | High | Snippet plays plain first, then with the marker; marker in a distinct timbre; owner tries 3 snippets before the sample is judged (Task 24). Happened: a mixed-in tone was inaudible; fixed with the click in its own ear and a half-speed loop of the spot |
| Demucs stem bleed makes a "no" sound like "yes" | Medium | Mix and stem together in the snippet; *unclear* is a valid answer and reported |
| Few spots of a pipeline's own error set (Quality-only kick/snare/toms errors) | Medium | Report n per pipeline and class next to every corrected value; intervals by bootstrap |
| Many *unclear* answers | Medium | Bounds with *unclear* counted either way; share reported |

## GTK application: `engine-api` (approved 2026-11-14, SPEC.md "GTK application")

The first module of the capability map: everything the app needs from the library, without GTK.
`design` (mockups with the owner) runs in parallel and has no tasks here.

Design decisions:
- **One path for progress and cancellation:** `api` builds the list of steps before it starts
  (from the mode's pipelines), then passes `progress` and `cancel` down through
  `runner.cached_or_run` to `adapters._run_group`, which already runs every adapter in its own
  process group. The group is polled instead of waited on, so a cancel ends it within a second.
- **A cancelled step cleans up after itself:** a cache entry counts only with its output and
  `meta.json`; a cancelled run removes what it wrote, so the next run starts clean.
- **`notation.engrave` returns the MusicXML and the bar map together;** `to_musicxml` stays
  and returns the MusicXML alone. The map comes from the same repeat blocks that write the
  repeat signs, so the two cannot disagree.
- **Corrections change the beat grid, not the hits:** a pure function turns beats, downbeats
  and `Corrections` into the corrected beats and downbeats; everything after it is today's code.
- **`render_hits` generalises `align`'s click track** (clicks only, no mix; the app mixes).
- **No adapter file is touched,** so no cache key changes.

Order: Python range (31) and the setup measurement (32) first, because both can change later
modules → progress (33) → cancellation (34) → setup progress and cancel (36); readiness (35),
bar map (37) → corrections (38) and hit audio (39) are independent of the progress chain.

| Risk | Impact | Mitigation |
|------|--------|------------|
| A cancelled `uv sync` or weight download leaves a broken environment | High | Task 32 measures it on a copy of an adapter folder before anything is built; a needed fix is specified before `setup-assistant` |
| Bar map and repeat signs drift apart | High | One source for both (the repeat blocks); test: expanding the written bars along the map gives back every song bar; checked against Verovio's expanded timemap for one song |
| Halving the tempo with an odd number of beats, or a meter override that leaves a rest of a bar | Medium | Pure function with its own tests for the edges; the last incomplete bar is kept as today |
| A dependency behaves differently on Python 3.14 | Low | The trial run passed (461 of 462); CI runs the suite on 3.12 and 3.14 |
| Clicks mask the drums or are hard to tell apart | Medium | Owner listens to one song (Task 39); samples stay an open decision for `playback` |

## GTK application: `app-shell` (approved 2026-11-14, SPEC.md "Module `app-shell`")

The first module with GTK code: the window, opening a song, the analysis, export of MusicXML
and the drum track, recent songs, appearance, keyboard, German. Screens 4, 5, 8 and 9 of
`design` (`docs/design/`).

Design decisions:
- **Logic and widgets apart from the first commit:** `stickler_gtk/logic` has no GTK and is
  tested in `check.sh` on 3.12 and 3.14; `stickler_gtk/ui` runs only on the system Python and
  is checked by a few smoke tests marked `gtk` plus by hand. CONSTRAINTS.md gets the two lines
  the spec proposes (approved with the spec).
- **The window is a state machine in `logic/session.py`:** empty, analysing, result, error,
  exporting; every change is a pure function of the state and an event (`api.Step`, done,
  failed, cancelled). The widgets only draw the current state.
- **One worker thread per job** (analysis or export) with an `api.CancelToken`; results and
  steps reach the main loop through `GLib.idle_add`. A new job cancels the running one.
- **The app writes only into its own folders:** `notate` writes the MusicXML into the app's
  cache folder (not next to the song, which the sandbox could not do); "Export" copies it to
  the place chosen in the save dialog. The drum track goes the same way.
- **Translations from the start:** gettext with the domain `stickler`; `scripts/i18n.sh`
  extracts with `xgettext` from `stickler_gtk` and merges `po/de.po`; the app installs its
  `.mo` files from `po/` at start in development. Every task adds its German strings.
- **What the window needs and the API lacks** (title, artist and length of a song for the
  header and the drum track's cost; tempo and meter of a result) comes as one small addition
  to `stickler.api` (`song_info`, `Notation.tempo`, `Notation.meter`), tested like the rest of
  `engine-api`; no GTK and no new dependency in `src/stickler`.

Order: skeleton and checks (41) → translations (42), so every later string is translatable →
the main path open → analyse → result (43) → cancel and errors (44) → recent songs (45) and
export (46) → menu, appearance and keyboard (47) → narrow windows and the German check (48).

| Risk | Impact | Mitigation |
|------|--------|------------|
| `.venv-gtk` with `--system-site-packages` picks up system packages that differ from `uv.lock` | Medium | The app environment installs the harness's locked dependencies on top (`uv sync` into it); only `gi` and `cairo` come from the system; `scripts/gtk.sh` prints both versions |
| GTK calls from the worker thread crash or corrupt the window | High | Workers never touch widgets; everything goes through `GLib.idle_add`; a smoke test runs a fake analysis with progress |
| Widget code grows logic that is not tested | Medium | Code review against "logic decides, widgets show"; coverage counts `logic/` only, so moving logic there pays off |
| A string slips through untranslated | Low | The translation test fails on string literals shown to the user without `_()` |
| Drop or file chooser paths behave differently in the Flatpak | Medium | Only portal-friendly GTK APIs (`Gtk.FileDialog`, `Gdk.FileList`, `Gtk.FileLauncher`); the sandbox trial in `packaging` checks them early |

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
