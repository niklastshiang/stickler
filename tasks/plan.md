# Implementation Plan: Stickler

Source spec: SPEC.md

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

## GTK application: `sheet-view` (approved 2026-11-15, SPEC.md "Module `sheet-view`")

The sheet music on the result page: Verovio engraves, librsvg draws, cairo adds the marker.

Design decisions:
- **Verovio lives in `stickler_gtk/logic/engraving.py`:** it needs no GTK, so the layout, the
  measure of each written bar and its rectangle are tested in CI like the rest of the logic.
  Only drawing (librsvg, cairo) and the PDF are in `ui/`.
- **Rectangles from the SVG, not from librsvg:** a measure's staff lines give its left and
  right edge and the staff's top and bottom; the marker pads that box. Parsed with the standard
  library's XML parser from Verovio's SVG.
- **Song time → bar in one place (`logic/marker.py`):** the bar map gives the written bar, the
  engraving gives its measure; `playback` will only call it.
- **Layout follows the width:** Verovio's page width is the window's width divided by the zoom;
  a new width waits for the resizing to pause (about 150 ms) before Verovio runs again.
- **The font through fontconfig only:** `scripts/gtk.sh` writes a fonts.conf that adds
  `.venv-gtk/share/fonts`; nothing is installed into the user's own font folders.

Order: dependency, font and About (49) → engraving (50) → marker logic (51) → the page in the
window, width and zoom, dark (52) → marking by click and by time (53) → PDF and "Open With…"
(54).

| Risk | Impact | Mitigation |
|------|--------|------------|
| Verovio's layout at small widths is hard to read for drums | Medium | The owner looks at it at the checkpoint; scale and page width are the only levers the spec allows without asking |
| Re-engraving on every resize makes the window sluggish | Medium | Debounced; Verovio took ≤ 0.06 s per song in the Verovio test; measured again in Task 52 |
| Verovio's SVG structure (classes, ids) changes in a later version | Medium | The engraving tests pin the structure they read; a Verovio update is "ask first" |
| The font is found in development but not in the Flatpak | Low | The Flatpak's `/app/share/fonts` is on fontconfig's path; the `packaging` trial checks it |

## GTK application: `playback` (approved 2026-11-15, SPEC.md "Module `playback`")

Play the song, the detected hits as clicks, or both; the marker follows.

Design decisions:
- **One GStreamer pipeline, two branches:** `uridecodebin` → `audioconvert` → `audioresample`
  → `volume` for the song and for the clicks WAV, both into one `audiomixer` → `autoaudiosink`.
  Seeking and pausing the pipeline moves both; muting is the `volume` element's `mute`.
- **The player is a thin object with a small interface** (`load`, `play`, `pause`, `seek`,
  `position`, `duration`, `set_volumes`, `stop`), so widget tests use a fake and one test runs
  the real pipeline against `fakesink`.
- **Decisions in `logic/playback.py`:** volumes per hear mode, the jump target of a bar click,
  the previous/next bar for the arrow keys, and the bar's texts. No GStreamer there.
- **The clicks are made once per result** in the worker that finished the analysis, into the
  app's cache, so playing never waits for them.
- **The marker** is driven by a 50 ms timer that runs only while playing.

Order: logic (55) → player (56) → the playback bar on the result page (57) → hear mode, volumes,
marker, bar clicks (58) → keyboard, narrow, stopping, German (59).

| Risk | Impact | Mitigation |
|------|--------|------------|
| Song and clicks drift apart | High | One pipeline and one clock for both; the clicks WAV is as long as the song (engine-api) |
| A seek in a compressed file lands late | Medium | Accurate seeks (`Gst.SeekFlags.ACCURATE`); a test checks a seek lands within 50 ms |
| No audio device (CI, a broken setup) | Medium | The real-pipeline test uses `fakesink`; the app shows an error toast instead of crashing when the sink fails |
| The pipeline keeps playing after the window closed | Medium | `stop()` sets it to NULL on close, quit and a new song; a test checks the state |

## GTK application: `corrections` (approved 2026-11-15, SPEC.md "Module `corrections`")

Fix the beat and make the sheet easier to read, applied at once and remembered per song.

Design decisions:
- **`logic/corrections.py` owns the values:** `api.Corrections` plus the detected meter it
  started from; pure functions for each control (`with_tempo`, `with_beats`, `with_first_one`,
  `with_simplify`, `with_repeats`, `detected`) that keep the values in range, and a JSON store
  keyed by the song's absolute path.
- **One job function for both:** `analysis.analyse(..., corrections)` notates with the given
  corrections; a correction runs the same function (song info is cheap, the transcription
  cached), so there is one path to test.
- **Session:** `Result` gains `corrections` and the `detected` meter; `correcting(result)` opens
  a job number on a `Result` without leaving it (the sheet stays), `corrected(state, job, ...)`
  replaces the notation only for the newest job.
- **The window applies a change after 250 ms of quiet**, in the worker; the store is written
  when a correction is shown, removed by "Back to Detected".
- **Sidebar and bottom sheet share one controls widget**, moved between them by the narrow
  breakpoint, as the playback bar regroups.

Order: logic and store (60) → jobs and session (61) → the sidebar with its controls (62) →
applying, remembering, Back to Detected (63) → bottom sheet, keys, German (64).

| Risk | Impact | Mitigation |
|------|--------|------------|
| Several quick changes race each other | Medium | Debounce plus job numbers: only the newest result is shown |
| A correction makes the marker point at bars that no longer exist | Medium | The bar map comes with each notation; `Result` always holds the matching pair |
| Re-engraving with Verovio blocks the main loop on long songs | Low | Measured with notate at 0.2 s; Verovio runs as today on a result; measure on the longest own song in Task 63 |
| A stored correction no longer fits (song changed) | Low | Values are validated on load; an invalid entry is dropped alone |

## GTK application: `setup-assistant` (approved 2026-11-15, SPEC.md "Module `setup-assistant`")

A first start without a terminal: consent, download with progress, errors that name the server.

Design decisions:
- **The two adapter changes come first and alone** (65, 66), each with the rekey procedure of
  CLAUDE.md, so a result change would show in its own commit.
- **The mirror URL is fixed before the release exists:**
  `https://github.com/niklastshiang/stickler/releases/download/beat-this-final0/final0.ckpt`,
  with the checkpoint's SHA-256 in Beat This!'s `common.py`. The code is tested against a local
  HTTP server; the release itself is published with the owner's go (Checkpoint M).
- **`logic/setup.py` decides, `ui/setup.py` draws:** what to show at start (consent, download,
  nothing), the step rows of what is missing, the byte progress of a step (folder sizes sampled
  every half second in the worker), and the server a failed step names.
- **`STICKLER_ADAPTERS`** points the app at another adapters folder, so a fresh setup can be
  tried without touching the models in use.

Order: ADTOF from an archive (65) → Beat This!'s mirror (66) → setup logic (67) → consent and
download pages (68) → errors, Not Now, the old page gone, German (69).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The archive build differs from the git build | High | Same commit, same lock versions (checked in the trial); one own song transcribed before and after, results compared |
| The mirror serves another file | High | SHA-256 checked before the file is used; a mismatch counts as failed |
| Byte progress jumps or stalls (uv links from its cache at the end) | Low | Capped at 99 % until the step ends; the step list still shows which step runs |
| The JKU server is down while testing | Medium | Tests use a local server; the owner's fresh setup can use the mirror once published |

## GTK application: `packaging` (approved 2026-11-15, SPEC.md "Module `packaging`")

A `.flatpak` and an AppImage for every release, built by GitHub Actions.

Design decisions:
- **App changes first** (71–73), so both packages are built from an app that already runs
  without the benchmark's imports, on Python 3.14 models, with its models in the XDG folders.
- **One adapter per step in Task 72** (the app's three: ADTOF, Beat This!, Demucs), each with the rekey procedure when its song result is
  identical; the downloads (a 3.14 environment per model) stay in uv's cache.
- **The Flatpak is built and installed locally first** (75), then in CI (77) with the
  `flatpak-github-actions` container for GNOME 51; the AppImage script (76) runs the same in a
  local Arch container and in CI.
- **A manual workflow run** builds both without a release; the tag run attaches them.

Order: no benchmark imports (71) → Python 3.14 (72) → packaged paths (73) → MetaInfo (74) →
Flatpak (75) → AppImage (76) → release workflow (77).

| Risk | Impact | Mitigation |
|------|--------|------------|
| An app model has no 3.14 wheel for a dependency | Medium | Checked per model (Demucs: numpy 2); if one cannot move, the owner is asked |
| uv in the Flatpak picks the wrong Python | Medium | `UV_PYTHON` points at the runtime's interpreter, `UV_PYTHON_DOWNLOADS=never`; a test of the environment the app passes |
| quick-sharun changes daily | Medium | Pinned to a commit; updated on purpose |
| GTK/libadwaita in the AppImage differ from the runtime's | Low | Arch has GTK 4.22 and libadwaita 1.9 like the development machine; the AppImage's own test runs it |

## `polish` (approved 2026-11-15, SPEC.md "Module `polish`")

Click volume per song, the artist in the PDF, removing the models from the installed app.

Design decisions:
- **Clicks:** `audio.click_gain(song, hits, sr)` measures the song's 50 ms windows at the hits
  and returns the factor that puts the clicks' windows a fixed number of dB above them; the
  number is chosen so Eye of the Tiger keeps today's level. `render_hits` applies it before the
  soft limit.
- **Artist:** `notation` writes `<credit>` elements after `<identification>`; a test engraves
  an A4 page with Verovio and finds the artist.
- **Removal:** `logic/removal.py` returns the folders for a packaged app (none from the
  checkout) and their size; the window runs the deletion in the worker, resets the consent and
  shows the empty window.

Order: artist (78) → clicks (79) → removal logic (80) → menu entry and alert (81).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The click level changes what the owner liked on Eye of the Tiger | Medium | The target offset is computed from Eye of the Tiger's current clicks; a test pins that the gain there is about 1 |
| A removal deletes something outside the app's folders | High | The logic only returns folders below the app's XDG folders, refuses the checkout; tests for every case |
| Deleting 2 GB blocks the window | Low | The deletion runs in the worker, the window waits on the analysing page |

## Release 7: New candidates (approved 2026-11-16, SPEC.md "Release 7")

Three new transcription candidates, measured like every pipeline; the app changes only for a
corrected improvement within the time budget.

Design decisions:
- **DrumSep first** (Task 12): cheapest, runs on the laptop, reuses the `roformer` adapter's
  pinned audio-separator 0.48.0. The weight download is checked before anything else, since the
  original host is gone. The per-stem onset step is a pure function in the adapter (unit tests
  on generated clicks); its parameters are chosen on MDB and ENST.
- **MuScriptor large** (82) is a copy of `muscriptor_m` with `SIZE = "large"`: new folder, new
  cache keys, existing results untouched.
- **Separate-and-Detect** (83) is the risky one: research code on Python 3.10 with madmom and
  CUDA scripts. A spike first: does the pinned commit run inference on a 10 s drum stem, on CPU
  and on a RunPod GPU? If it fails after two attempts, it is recorded as tried and left out
  (as YourMT3+ was), with the owner's agreement.
- **Measurement** (84): laptop for DrumSep and the time budget of every candidate; RunPod
  (`stickler remote`) for MuScriptor large and Separate-and-Detect on all datasets.
- **Listening** (85) only if a candidate comes within 0.01 of a mode; release 3's code draws and
  corrects, with the candidate's own spots.

Order: DrumSep (12) → MuScriptor large (82) → Separate-and-Detect spike and adapter (83) →
benchmark runs (84) → listening if needed (85) → decision ADR, report, README, release 7 (86).

| Risk | Impact | Mitigation |
|------|--------|------------|
| DrumSep weights no longer downloadable | Medium | Check the download first; a mirror only with a stated source and checksum, else drop the candidate (owner) |
| Separate-and-Detect does not run (old Python, madmom, CUDA-only code) | Medium | Spike with two attempts, then leave it out with the owner's agreement |
| MuScriptor large or Separate-and-Detect exceed 20 min per song | High (likely) | Measured on the laptop on one song early; reported, not put into the app |
| RunPod cost | Low | Runs planned per dataset, pod stopped automatically |

## `legend` (approved 2026-11-17, deferred the same day by the owner; SPEC.md "Module `legend`")

A legend on page 1 of the exported PDF: one entry per staff position the sheet uses, named in
the app's language.

Design decisions:
- **Positions** (`notation`): the distinct `Staff` values of the engraved MusicXML's
  instruments, sorted top to bottom with STAFF's order for ties; the legend's MusicXML is one
  stemless measure with those noteheads and the given labels as lyrics.
- **Names** (`logic/legend.py`): `N_()` constants per position, translated with `_()` at use;
  `notation` stays free of strings and of gi.
- **Room and drawing** (`logic/engraving.py`): blank right/bottom credits after the band, added
  in memory for the A4 pages only; the legend's top read from page 1's SVG; the legend's SVG
  nested into page 1's. `ui/pdf.py` unchanged.

Order: positions and legend MusicXML (88) → names (89) → room and drawing on page 1 (90) → the
PDF and the owner's check (91).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The legend overlaps the first system or the band | Medium | Its place is read from the engraved page 1 (first system's top), tested with and without a band |
| Quality writes many positions and the legend wraps | Low | A test with every STAFF entry in the longest language stays one line; if not, smaller lyrics |
| The blank credits leak into the exported MusicXML | Medium | They are added in memory for the A4 pages only; a test reads the stored file |

## Release 8 (macOS app): `shared-core` (approved 2026-11-17, SPEC.md "Module `shared-core`")

The app's logic and translations move from `stickler_gtk` to a neutral package `stickler_app`,
and the Mac app's String Catalog is generated from `po/`. No change a Linux user could see.

Design decisions:
- **A move, not a rewrite:** `git mv` keeps each module's history; names stay
  (`stickler_gtk.logic.session` → `stickler_app.session`); no re-export shims, so a missed import
  fails loudly in the tests instead of working by accident.
- **One commit for the move** (Task 92): imports, `pyproject.toml`, CONSTRAINTS.md, tests and the
  i18n script must change together, or the checks fail in between. Packaging paths follow in
  their own task (93) because they are verified by building.
- **The catalog generator is test-first** (Task 94): placeholder mapping and plurals are where a
  silent mistake would show the wrong number in a translated sentence.

Order: move (92) → packaging paths and builds (93) → String Catalog (94) → owner's check (95).
93 and 94 are independent of each other.

| Risk | Impact | Mitigation |
|------|--------|------------|
| A path to `stickler_gtk/logic` is missed (scripts, packaging, docs) | Medium | `grep -rn "stickler_gtk.logic\|stickler_gtk/logic\|stickler_gtk.i18n"` must be empty; both packages built and started |
| Translations stop loading (localedir via `prefix()`) | Medium | `test_translations.py` moves along and still loads de and es; the owner's check in German |
| The pot changes beyond source references | Low | Diff of `msgid`/`msgstr` lines before and after `scripts/i18n.sh` |
| Xcode reads the generated catalog differently than assumed | Medium | Format from Apple's documentation; the first real check is `mac-shell` on a runner, so the script stays small and easy to adjust |

## Release 8 (macOS app): `mac-core` (approved 2026-11-17, SPEC.md "Module `mac-core`")

The Python core and the app's models on macOS arm64 (CPU), checked by a macOS runner; Linux
unchanged.

Design decisions:
- **Digest edits one at a time** (96, then 97): each takes `stickler cache-digests` before and
  after and adds its own pairs, so a chain stays readable and a mistake is one revert.
- **The Linux comparison is a script, kept** (`scripts/lock_platforms.py`): it lists every
  package, version and wheel hash a lock resolves for Linux; the next platform change (Windows)
  needs it again.
- **Verifying the pairs without touching `results/enst`** while the pod run writes it: `stickler
  eval` for MDB and the own songs at once, ENST after the pod run.
- **CI before the smoke tests** (98, then 99): the plain suite on macOS shows the platform spots
  first; the model runs build on a green job.

Order: peak RAM (96) → wider platforms (97) → macOS job (98) → smoke tests on the runner (99).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The relock moves a Linux package | High | The comparison script must show no difference; else stop, ask the owner |
| A pair is added for an edit that changes Linux results | High | Peak RAM: a test fixes the Linux number; locks: the comparison; `stickler eval` finds every result |
| Tests assume Linux (paths, /proc, GTK) | Medium | Seen in the first macOS run; each one fixed or skipped with its reason in the commit |
| macOS runner minutes or a flaky model download | Low | Smoke tests only on relevant pushes and weekly; weights cached between runs |

## Release 8 (macOS app): `core-bridge` (approved 2026-11-18, SPEC.md "Module `core-bridge`")

The core as one subprocess speaking JSON lines; the state lives in Python. The GTK window's
flows move into a GUI-neutral controller that both apps use.

Design decisions:
- **Controller first, bridge second, GTK last** (100–101, then 103–105, then 106): the bridge is
  built on a controller that is already tested; GTK switches only once the controller has
  carried the bridge through every flow, so its switch finds no new behaviour.
- **The controller copies the window's flows, it does not redesign them.** Each flow's test
  states the GTK behaviour of today (one job at a time, cancel back to the previous state, the
  setup meter twice a second, the song opened after the setup). A difference found on the way
  is noted and asked, not fixed silently.
- **Threads without GLib:** the controller takes a `post` callable from its host and calls it
  for every new state (GTK: `GLib.idle_add`, the bridge: a queue its writer drains). The
  sampling of the setup meter is a thread with a stop event instead of `GLib.timeout_add`.
- **One writer:** only the bridge's writer thread touches stdout, so replies and events never
  interleave inside a line; `seq` is assigned there.
- **The state's JSON comes from one function per state kind** (`bridge.encode`), tested
  against `docs/bridge.md`'s examples, so the document cannot drift.
- **`paths` before the bridge** (102): the Mac kind is a few lines with Linux's tests as the
  guard, and the bridge's tests on the macOS runner need it.
- **A fresh-context review after 106** (CLAUDE.md): the controller and the GTK switch touch the
  Linux app; a reviewer without this conversation reads the diff against SPEC.md.

Order: controller, analysis (100) → controller, setup and exports (101) → Mac paths (102) →
bridge loop and state (103) → the remaining commands and `docs/bridge.md` (104) → subprocess
test and demo with real models (105) → GTK onto the controller (106).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The GTK window changes behaviour in 106 | High | Widget tests unchanged and green; the owner's check on the laptop; the review |
| A race between a cancel and a finished job (an old job's state shown) | Medium | `session` already drops reports of an old `job`; tests cancel in every state |
| stdout blocked when Swift does not read | Medium | Events go through a queue; a full queue keeps only the newest state (the state is whole each time) |
| The bridge outlives a crashed app | Medium | stdin EOF ends it; a test closes stdin during an analysis and looks for processes |
| Large SVG lines for long songs | Low | Pages only on request, never in the state; measured in 105 (Eye of the Tiger) |

## Release 8 (macOS app): `mac-shell` (approved 2026-11-18, SPEC.md "Module `mac-shell`")

The first Swift: a Foundation-only package that talks to the core, and the SwiftUI app over it,
with the setup assistant. Built and tested on GitHub's runners; the owner tries the CI's app on
their Mac against a checkout.

Design decisions:
- **CI and the quality bar first** (107): the Swift rules in CONSTRAINTS.md, the floor guard's
  Swift patterns and both CI jobs exist before the first real Swift line, so nothing is written
  unchecked. No one here has Xcode; the runner is the only compiler for the app.
- **`SticklerCore` before the app** (108–110): decoding, the process client and the window's
  model are tested on Linux in WSL and CI against the real bridge, so the app's views only draw
  a model that is already proven. `docs/bridge.md`'s example lines are the decoding tests, as
  in Python.
- **One screen group per task** (111–115), each with its screenshots in light and dark as CI
  artifacts, so the owner can compare with the canvas without a Mac at hand.
- **The PDF is its own task** (115): it carries the one real risk (WebKit and the Leipzig font).
- **The owner's Mac only at the end** (116), after the review; the artifact works from 111 on
  for an early look if the owner wants one.

Order: CI and constraints (107) → protocol types (108) → process client (109) → window model
(110) → app shell and empty window (111) → analysis, errors, the stopped core (112) → setup
and removal (113) → exports and the saved bar (114) → PDF (115) → Mac guide, review, owner's
check (116).

| Risk | Impact | Mitigation |
|------|--------|------------|
| Swift compiles only on the runner: slow feedback for the app target | Medium | Logic in `SticklerCore`, tested locally on Linux; the app target thin |
| Foundation on Linux differs from macOS (line reading, `Process`) | Medium | The client reads with `read(upToCount:)` on its own thread; its tests run on both |
| WebKit lacks the Leipzig font in the PDF | Medium | A test checks the tempo mark's text; embed the font in the SVG or register it |
| XcodeGen's output changes with a new release | Low | Pinned version; the project is generated in CI only |
| "Open Anyway" missing on the owner's Mac | Low | `xattr` in `docs/mac-development.md` |

## Release 8 (macOS app): `mac-sheet` (approved 2026-11-18, SPEC.md "Module `mac-sheet`")

The sheet music in the Mac app, from the core's SVG pages, as wide as the window, with the note
size of the View menu and a pinch. The model (126) starts at once (owner, 2026-11-18); the view
(127–129) after `mac-shell`'s checkpoint U (the owner's check on the Mac).

Design decisions:
- **The model before the view** (126): what is asked for and when (a new result, a settled
  width, a zoom), and which reply wins, lives in `SticklerCore` and is tested on Linux against a
  scripted core, as `AppModel` was. The view then only draws pages it is handed.
- **The page as a pure function** (127): the HTML the web view loads is built by a function of
  the pages and the appearance, so the tests check it without WebKit (no script, the shadow, the
  inversion in dark mode only) and the coverage gate counts it like `Exports`.
- **One web view, JavaScript off** (`WKWebpagePreferences.allowsContentJavaScript = false`):
  the core's SVG is data placed into a fixed page, never code that runs.
- **Zoom last** (128): the menu and the pinch only send the core's zoom commands; the model of
  126 already asks for pages after them.
- **A fresh-context review at the end** (129), then the owner's check on the Mac.

Order: the sheet's model (126) → the sheet in the window (127) → View menu and pinch (128) →
review and the owner's check (129).

| Risk | Impact | Mitigation |
|------|--------|------------|
| A resize floods the core with `pages` requests (a whole song engraved each time) | Medium | The model waits 0.3 s for the width to settle; a test sends a quick series of widths and expects one request |
| WebKit draws the tempo mark as a box (font) | Low | Verovio embeds the Leipzig subset (seen in task 115); a screenshot shows the tempo mark |
| Long songs are slow to load as one document | Low | Measured with Eye of the Tiger on the owner's Mac; pages could be split later |
| The macOS runners are scarce (cancelled jobs) | Medium | Logic on Linux first; rerun cancelled jobs; only view work needs the runner |

## Website (approved 2026-11-18, SPEC.md "Website")

A static page in plain HTML and CSS, English and German, for drummers who are not technical:
built now, deployed with release 8. The mockup on the private canvas "Stickler website" is the
look to build (Figtree, Apricot, light and dark following the browser).

Design decisions:
- **One English slice first** (118): the skeleton with its stylesheet, the font, the tokens,
  the skip link and the site's test exist before any content, so every later section is
  checked as it lands. The test is pytest with `html.parser` (no new Python dependency).
- **The pictures before the content** (119): light and dark screenshots and the overview video
  come from one run of the app (`scripts/demo.py`), so they show the same song and moment;
  the content task then only places them. It needs the owner's copy of "Fluffing a Duck" and
  the Fast models on the laptop.
- **German after English is complete** (121): translating a finished page once, then the test
  keeps both in step (anchors, images, downloads), instead of keeping two moving pages equal.
- **No deploy before release 8** (123): the workflow builds, checks (axe-core light and dark)
  and uploads on every push to `site/`, but deploys only on a published release from 8 on or
  by hand; the download cards are filled from the release, so the HTML holds no version.
- **The Mac card waits for `mac-package`:** its size and its three "Open Anyway" pictures come
  from that module's install guide; until then the card shows the text steps.
- **A fresh-context review at the end** (124), against SPEC.md and WCAG 2.2 AA.

Order: skeleton, font and test (118) → pictures and video, light and dark (119) → the English
page's sections (120) → German, about, privacy, 404 (121) → meta, icons, CSP, sitemap (122) →
workflow with release data and axe-core (123) → DNS guide, review, owner's check (124).

| Risk | Impact | Mitigation |
|------|--------|------------|
| Recording the app on the laptop disturbs the owner's session (portals) | Medium | `scripts/gtk.sh demo` as today: only mutter in a private D-Bus session, the app on the normal bus; Stickler closed first |
| A dark `<source media>` on `<video>` is ignored by a browser | Low | The poster and the GIF fallback are light and dark through `<picture>`; checked in Firefox, Chrome and Safari by the owner |
| Two hand-kept languages drift | Medium | The test compares anchors, images, links and downloads of each pair |
| axe-core in CI adds Node and a browser | Low | Pinned versions, only in `site.yml`; approved with the spec |
| The custom domain's certificate takes long or fails | Low | The DNS guide (124) lists the steps from GitHub's docs; the site works at the github.io address meanwhile |

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

## Release 8 (macOS app): `mac-package` (approved 2026-11-19, SPEC.md "Module `mac-package`")

The `.dmg` a drummer installs without a Terminal: the app with `uv`, a Python, the core, ffmpeg
and the adapters' sources inside. Tasks 131–137.

Design decisions:
- **The spike first** (131): one throwaway workflow builds the whole bundle the plain way and
  the owner opens it on the Mac. Its three answers (the core starts from inside a quarantined
  app; `uv`'s Python and the wheels run; sizes and build times) can change everything after
  it, so nothing else is planned in detail before checkpoint Y.
- **One build script** (`scripts/mac_bundle.sh`, 132–133): CI and the release run the same
  script; every download in it is pinned by version and SHA-256, as `scripts/appimage.sh` does.
- **The app changes last** (134): the folder question stays until the bundle is proven, so
  every push keeps giving the owner a working app.
- **Signing inside out** (136): each helper, then the app, never `--deep` (Apple DTS).

| Risk | Likelihood | What then |
|---|---|---|
| `uv`'s Python is killed on the owner's Mac (uv issue 16726) | Low | the core signs it ad hoc after `uv` installed it; decided at checkpoint Y |
| The core does not start from a translocated app | Low | the guide asks to drag the app to Applications first (it does already); the app says so when it runs from a random path |
| The ffmpeg build takes long or breaks with a new Xcode | Medium | the built programs are cached by their source's checksum; Martin Riedl's builds as the fallback (asks the owner) |
| The image is far larger than estimated | Low | measured in the spike; the owner decides before 132 |


## Release 9: `linux-packages` (approved 2026-11-20, SPEC.md "Module `linux-packages`")

A `.deb` for Ubuntu 26.04+ and an `.rpm` for Fedora 44+, on the release page next to the
Flatpak, the AppImage and the `.dmg`. Tasks 138–144.

Design decisions:
- **Python 3.15 first** (138): Fedora 45's Python decides whether one `.rpm` can serve 44 and 45;
  the app's range is raised and tested before any packaging code exists.
- **The app learns `"system"`** (139) like the AppImage: models, uv's Python and downloads in
  Stickler's XDG folders, the adapters' sources read-only under `/usr/share/stickler`.
- **One build script** (140) for CI and by hand, every download pinned by version and SHA-256 (nFPM,
  `uv`, the wheels from `uv.lock`); one `packaging/nfpm.yaml` for both formats.
- **Containers prove it** (141): install, start on an invisible screen, remove, in clean
  `ubuntu:26.04`, `fedora:44` and `fedora:45`; the same script runs in CI and locally (podman).

| Risk | Likelihood | What then |
|---|---|---|
| A harness dependency has no cp315 wheel, so the lock cannot cover 3.15 | Medium | only the app's packages are tested on 3.15 (a marker in `pyproject.toml`); asks the owner if even that fails |
| Fedora's `ffmpeg-free` or its GStreamer libav plugin cannot decode MP3 or AAC | Medium | measured in 141; the owner decides (RPM Fusion as a recommendation, or fewer formats promised) |
| A software centre refuses an unsigned local file | Low | the install texts give the terminal line first |
| GitHub has no Ubuntu 26.04 runner image yet | Low | the containers run on the existing runner, as the AppImage's Arch container does |


## Website: How it works as a story (approved 2026-11-22, SPEC.md "Website", "Change 2026-11-22")

The four cards of "How it works" become four steps that scroll by next to a picture that moves
with them, in CSS only, with pictures drawn from Stickler's real output instead of screenshots.
Tasks 145–149.

Design decisions:
- **Data first, kept in the repository** (145): the analysis needs the models, so it runs once by
  hand; the SVGs are made from the stored data, so CI and the test need no models.
- **Static before motion** (146, 147): the page must be complete without scroll-driven
  animations; the motion is added on top and switched off by `prefers-reduced-motion`.
- **One timeline per step**: each picture lives in its own step and animates on its own `view()`
  timeline; no `timeline-scope`, whose support is not confirmed.

| Risk | Likelihood | What then |
|---|---|---|
| A sticky picture inside its step jumps when the next step starts | Medium | the step's height and the picture's `top` are tuned at 390, 900 and 1280 px; else the picture stays still and only fades |
| The engraved notes are too small to read on a phone | Medium | one system only on a phone, two on a wide screen |
| Safari or Firefox animate a property differently | Low | only `opacity` and `transform` are animated |


## Release 10: keep and remove (approved 2026-11-22, SPEC.md "Release 10 (proposed): keep and remove")

Back Up / Restore Backup and Uninstall Stickler, in the GTK app and the Mac app. Tasks 150–160.

Design decisions:
- **Risk first** (150): the three things not confirmed (a running AppImage to the Bin, a running
  Mac app handing its bundle to a helper, GNOME Software's uninstall button for a Flatpak from a
  file) are tried before any feature code depends on them.
- **Logic in `stickler_app`, system calls at the edge:** what a backup holds, how it merges, what
  an uninstall removes and which menu entries an AppImage integration made are plain Python
  in `stickler_app` (no `gi`, CONSTRAINTS.md "GTK boundary"), tested with temporary folders.
  The D-Bus call to PackageKit and the open-URI call live in `stickler_gtk` (Gio); the Mac app
  does its own `~/Library` cleanup and helper in Swift, and asks the core for the rest over the
  bridge, as it does for "Remove Downloaded Models…".
- **Songs by content before the backup** (151): without it a restored backup finds nothing on
  a new computer; it also helps when a user moves a song today.
- **Containers prove the removal:** the `.deb` and `.rpm` remove themselves through PackageKit
  in the existing container test (as the Software app's install does since task 144).

| Risk | Likelihood | What then |
|---|---|---|
| A running AppImage cannot go to the Bin (the trash may refuse a mounted file) | Low | it is deleted instead after the user agreed; the menu entries and data go as planned |
| The Mac helper cannot move the bundle (permissions, translocation) | Medium | the app shows the steps instead, as for a translocated app |
| GNOME Software shows no uninstall button for a Flatpak from a file | Low | the dialog shows the `flatpak uninstall` line there too |
| PackageKit asks no password on some system (a polkit rule) | Low | the app's own dialog has already asked; documented |

## Mac playback: `mac-playback` (approved 2026-11-25, SPEC.md "Mac playback")

The Mac app plays the song, its clicks or both, with the marker following (screens M10).

Design decisions:
- **The rules stay in Python:** the bars with their texts come in the `result` state; a bar
  click's target, the arrow keys' step and the gains per Song/Hits/Both are bridge commands
  (`jump`, `step`, `volumes`), wrapping `stickler_app.playback`. Swift only looks up, 20 times
  a second, which of the core's bars sounds and which rectangle marks it (mirrors of
  `marker.written_at`/`locate`, tested with the same cases).
- **One AVAudioEngine, two player nodes** started at one host time, as GTK's one pipeline;
  tested for real in offline manual rendering on the macOS runner, so no sound device is
  needed in CI.
- **A model before any view:** `PlaybackModel` in `SticklerCore` drives a `Playing` protocol,
  tested on Linux with a fake player, as `SheetModel` was before its view.
- **The marker is the app's own script** in the loaded sheet (content scripts stay off), drawn
  outside the inverted paper so the accent colour stays itself in dark mode.

Order: bridge (161) → model (162) → player (163) → controls (164) → marker and clicks (165) →
menu, keys, texts (166) → review, build for the owner (167). 161 and 162 are checked on Linux;
from 163 on each push goes through the `mac` workflow.

| Risk | Impact | Mitigation |
|------|--------|------------|
| Song and clicks drift apart | High | One engine, both nodes started at the same host time and seeked from the same frame; an offline test checks it sample for sample |
| macOS 26 cannot read a format macOS 27 reads (Ogg) | Medium | The core's FLAC copy (`playable`) when `AVAudioFile` refuses; a test on the runner lists what macOS 26 reads |
| A command waits behind `pages` while the core engraves | Low | Only clicks and keys wait, not the marker (looked up in Swift); a short wait after a resize is accepted |
| Headphones unplugged stop the engine | Medium | The configuration change pauses playback and rebuilds the engine at the same position |
| Space taken by a focused control | Low | Space is the Controls menu's key equivalent, which the menu gets first; checked by hand |

## Mac corrections: `mac-corrections` (approved 2026-11-25, SPEC.md "Mac corrections"; release 11)

The Mac app corrects the beat and the reading as the GTK app does (screens M11).

Design decisions:
- **The rules stay in Python:** what the inspector shows comes in the `result` state as
  `controls` (`corrections.controls`, moved out of the GTK view so all apps share it); each
  control sends one change through `correct`, which keeps it in range with the `with_*`
  functions and hands it to `Controller.correct`. Windows will use the same command.
- **The sheet follows the notation, not the wanted values:** `result` gains `sheet`, which
  changes with every new notation; `SheetModel` keys on it. Keyed on `corrections` (today) it
  would engrave the old notes at a correction's start and miss the new ones.
- **Steppers send steps, not values** (`beats_per_bar_by`, `first_one_by`): the core counts
  each from its newest values, so quick clicks are not lost (changed while building 190).
- **The inspector is SwiftUI's own** (`inspector`, `Form` grouped), open or closed kept in
  `@AppStorage`; the View menu item is a gated logic type like `ControlsMenu`.

Order: core and bridge (190) → SticklerCore (191) → inspector and spinner (192) → menu, key,
texts (193) → review, build for the owner (194). 190 and 191 are checked on Linux (and this
Mac's Command Line Tools for `swift test`); from 192 on each push goes through the `mac`
workflow.

| Risk | Impact | Mitigation |
|------|--------|------------|
| The sheet shows the old notes after a correction | High | `sheet` in the state, `SheetModel` keyed on it; a test that pages are fetched once per new notation and not at the start |
| Quick stepper clicks lost or sent twice | Medium | Steps (`_by`) counted by the core in order; a test with two quick clicks |
| `correct` waits behind `pages` while the core engraves | Low | The 250 ms pause already joins quick changes; a wait of one engraving is accepted |
| The GTK panel changes while its rule moves to `stickler_app` | Medium | The GTK widget test of the shown values runs before and after (`scripts/gtk.sh test`) |
| A toolbar button at the far right lands over the inspector on macOS 26 | Low | Placement checked in the screenshot against M11; the menu and ⌃⌘I work either way |

## Release 11 (Windows app): `win-core` (approved 2026-11-24, SPEC.md "Module `win-core`")

The Python core and the first version's models on Windows 11 x64 (CPU), checked by a Windows
runner; Linux and macOS unchanged. Tasks 168–175.

Design decisions:
- **What Linux can show comes first** (168–173): encodings (Python's `EncodingWarning` finds
  them here), peak RAM, the locks, the kill, the folders and the bridge's lines are each built
  with a stand-in for the platform and a test on Linux, as `_peak_rss_mb(platform)` was for the
  Mac. The runner then shows what is left (174), not everything at once.
- **Digest edits one at a time** (169, then 170), as for `mac-core`: each takes `stickler
  cache-digests` before and after and adds its own pairs.
- **The runner is the only Windows:** the branch `claude/win-core` is pushed after each task
  from 174 on; a red Windows job is read from its log (`gh run view --log-failed`), fixed and
  pushed again. Linux' check stays the pre-commit hook.
- **Sub-agents** (owner, 2026-11-24: cheaper models where sensible): mechanical or
  self-contained tasks (168's encodings, 172's folders, the workflow files) go to a cheaper
  model with the task's acceptance as its brief; every diff is read and `scripts/check.sh task`
  run before its commit. The digest tasks (169, 170) and reading the runner's failures stay
  with the main session.

Order: encodings (168) → peak RAM (169) → wider platforms (170) → the kill (171) → folders
(172) → bridge lines (173) → Windows job (174) → smoke tests on the runner (175).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The relock moves a Linux or macOS package | High | The comparison must show no difference; else stop, ask the owner |
| A pair is added for an edit that changes results | High | Peak RAM: tests fix the Linux and macOS numbers; locks: the comparison; `stickler eval` reads every result |
| `taskkill` leaves a model running (a process outside the tree) | Medium | The cancel tests run with real processes on the runner; a Job Object if they fail |
| Many tests assume POSIX; the first Windows run is very red | Medium | 168 and the process helper take the known ones first; the rest one by one from the log, each fixed or skipped with its reason |
| An adapter's package does not install or import on Windows (adtof-pytorch, Demucs) | Medium | Seen in 175; a platform note in the adapter only with `digests.yaml` pairs if behaviour-neutral, else stop and ask |
| Windows runner minutes, slow model downloads | Low | Free for a public repository; smoke tests only on relevant pushes and weekly |

## Release 11 (Windows app): `win-spike` (approved 2026-11-24, SPEC.md "Module `win-spike`")

A throwaway installer that proves the way the app brings its core along, on the runner and
then on the owner's company laptop. Tasks 176–180. Nothing but findings reaches
`claude/win-core` or `main`.

Design decisions:
- **A branch of its own** (`claude/win-spike`, from `claude/win-core`): the workflow
  `win-spike.yml`, the Inno Setup script, the launcher and the driver live only there. The
  findings are written into SPEC.md and `tasks/todo.md` on `claude/win-core`; the branch is
  deleted on GitHub at the end (its last run's number stays in the notes).
- **The runner answers first** (176–178): layout, installer, a silent install, the launcher on
  a synthetic clip, signatures, hashes, path lengths, the uninstaller. The owner is asked to
  install only something that already ran once on Windows.
- **The log is the spike's result:** the launcher writes one text file with every step, every
  program started and its exit code. On the owner's PC a held-back program shows as the last
  line; no guessing from a window that closed.
- **No tests of the usual kind:** the spike's code is deleted with its branch. What proves it
  is the workflow's run; `scripts/check.sh task` still gates every commit of the branch (lint,
  floor guard, the existing suite), and the driver stays small enough to read.
- **Sub-agents:** a cheaper model builds the workflow and iterates on the runner (each try is
  a push and a wait); the main session reads every run's summary itself before a finding is
  written down.

Order: layout and installer (176) → launcher and driver (177) → the runner's two runs and the
summary (178) → the owner's PC (179) → findings, branch deleted (180).

| Risk | Impact | Mitigation |
|------|--------|------------|
| The antivirus holds a program back for good | High for the owner's checks | A valid result (decision 2); the log names the program; tried again after an hour and a day |
| An environment's launcher differs per user, so no reputation can grow | Medium | Measured on the runner; starting the models with the downloaded Python directly is tried there |
| Paths over 260 characters without `LongPathsEnabled` | Medium | The runner's second run; a shorter folder is `win-package`'s change if needed |
| The relocated Python does not find its own files or the adapters' sources | Medium | Seen in the runner's first install; `STICKLER_ADAPTER_SOURCES` from the launcher |
| The installer is too large for an artifact or slow to build | Low | Sizes in the summary; ffmpeg's essentials build |


## Release 11 (Windows app): `win-shell` (being built from 2026-11-25, SPEC.md "Module `win-shell`")

The WinUI 3 window over the bridge, as `mac-shell` built the Mac's. Tasks 181–188, on the
branch `claude/win-shell`; the spike's retry on the owner's PC comes after it (owner).

Design decisions:
- **What Linux and Python can check comes first** (181–184): the certificates in the core,
  the texts and string tables, the C# floor, then `SticklerCore` with its tests on Linux (WSL)
  and Windows. The WinUI app (185, 186) only draws what `SticklerCore` holds.
- **Built and tested on this PC too:** the .NET 10 SDK installed for the user (open question
  2); the runner stays the check every C# change goes through (`win.yml`, 187).
- **No NuGet package beyond the Windows App SDK, MSTest and its coverage** (the release's
  boundary): no MVVM toolkit, `System.Text.Json`'s source generator for the protocol.

Order: certificates (181) → texts and tables (182) → C# floor (183) → `SticklerCore` (184) →
window, steps, errors (185) → dialogs, exports, backup (186) → `win.yml` (187) → review and a
build for the owner (188).

| Risk | Impact | Mitigation |
|------|--------|------------|
| `dotnet build` cannot compile WinUI XAML without Visual Studio | Medium | Built on the runner (Visual Studio there); `SticklerCore` needs no XAML and builds here |
| Panda holds back the built `Stickler.exe` on this PC | Medium | The runner's screenshots carry the module; the owner's check waits as `win-spike` decided |
| The unpackaged app's new pickers fail | Low | The older pickers with `InitializeWithWindow` |
| Runner screenshots blank (no GPU) | Low | Accepted; the owner's look counts |

## Release 11 (Windows app): `win-sheet` (approved 2026-11-26, SPEC.md "Module `win-sheet`")

The sheet music in WebView2 and the PDF, as `mac-sheet` built the Mac's. Tasks 200–205, on the
branch `claude/win-shell`, checked with `win-shell` at checkpoint AF (owner, 2026-11-26).
`win-package` is built at the same time in a session of its own (tasks from 210 on).

Design decisions:
- **The model and the HTML first, in `SticklerCore`** (200, 201): tested on Linux and here
  with the Mac's cases; the WinUI side (202, 203) only hands the width in and the HTML to
  WebView2.
- **Served from memory** under `https://sheet.stickler.invalid/`, not `NavigateToString` (2 MB
  limit) and not files on disk.
- **No new NuGet package:** WebView2 comes with the Windows App SDK.

Order: replies and the sheet model (200) → the page HTML (201) → the sheet in the window and
the zoom (202) → the PDF (203) → screenshots and the PDF in CI (204) → review and a build for
the owner (205).

| Risk | Impact | Mitigation |
|------|--------|------------|
| A precision touchpad's pinch does not arrive as Ctrl+wheel | Low | Ctrl+Plus/Minus/0 and the menu still work; noted for the owner's check |
| `PrintToPdfAsync` takes no title from `<title>` | Low | The PDF's title then stays empty; a later fix through the core's PDF (question 3) |
| The runner draws WebView2 blank | Low | The PDF and the HTML are checked as data; the owner's look counts |

## Release 11 (Windows app): `win-package` (approved 2026-11-26, SPEC.md "Module `win-package`")

The installer that brings the app and its core along, and the way out again, as `mac-package`
did for the Mac. Tasks 210–219 on the branch `claude/win-package`, built while
`win-sheet` is built on `claude/win-shell` (195–209 are `mac-site`'s and `win-sheet`'s); the
branches meet when release 11 is merged.

Design decisions:
- **What Linux and Python can check comes first** (210, 211): the removal's folders, the
  core's uninstall entry, the installed core's command line in `SticklerCore`. The installer
  only puts files in place and asks; what goes on an uninstall is the core's decision, as on
  every other system.
- **One script assembles the folder** (`scripts/win_bundle.sh`, Git's bash on the runner as
  the spike's workflow), every download checked against its SHA-256 before use; the Mac's
  `mac_bundle_tools.py` learns the Windows layout instead of a second copy of its rules.
- **The installer's texts come from `po/`** through `scripts/winstrings.py`, as the app's do;
  Inno's own texts for everything else (its official German and Spanish).
- **Small changes in the files `win-sheet` edits** (`MainWindow`, `CoreLaunch`), so the merge
  stays easy.

Order: core and removal (210) → installed core in `SticklerCore` (211) → icon (212) → bundle
(213) → installer and its uninstall question (214) → "Uninstall Stickler…" in the app (215) →
release job (216) → guide and README (217) → website (218) → SignPath texts, review and a build
for the owner (219).

| Risk | Impact | Mitigation |
|------|--------|------------|
| `CreateCustomForm` does not work in the uninstaller | Medium | Two plain questions (SPEC scope 4) |
| Panda holds back the new `Stickler.exe` and `unins000.exe` | Medium | The runner's start test carries the module; the owner's check waits, as in the spike |
| The installer grows past 200 MB | Low | Supported trimming switches only (SPEC risks) |
| Paths under `Programs\Stickler\core\python` too long | Low | Measured on the runner with `LongPathsEnabled=0`, as the spike did |
