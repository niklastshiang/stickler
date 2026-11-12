# Tasks: Stickler

Each task is only done once `scripts/check.sh task` is green and one commit has been made per task (see CONSTRAINTS.md).

## Phase 0: Docs

- [x] **Task 0: ADRs for decisions made** (XS)
  - Acceptance: `docs/adr/0001-demucs-fork.md` (adefossez/demucs instead of the archived repo) and `0002-nc-lizenzen.md` (NC weights allowed for private use), each with context, decision and consequences.
  - Verify: Files present, linked in SPEC.md.
  - Dependencies: none · Files: `docs/adr/*`, `SPEC.md`

## Phase 1: Vertical slice (`none` × `adt_str` on MDB)

- [x] **Task 1: Class mapping and scoring** (M)
  - Acceptance:
    - `Onsets` data class.
    - `config/classes.yaml` + `classes.py` map GM pitches to the 5-class scheme (KD/SD/TT/HH/CY) and the 3-class scheme (KD/SD/HH).
    - `evaluate.score()` returns P/R/F1 per class as well as micro and macro.
    - Self-comparison yields F1 = 1.0; a 60 ms offset counts as an error, a 40 ms offset as a hit (Success Criterion 1).
  - Verify: `uv run pytest tests/test_evaluate.py tests/test_classes.py`
  - Dependencies: none · Files: `src/stickler/{classes,evaluate}.py`, `config/classes.yaml`, tests

- [x] **Task 2: MDB Drums loader and `stickler fetch mdb`** (M)
  - Acceptance:
    - `api.fetch_dataset("mdb")` downloads MDB Drums to `data/mdb/`, idempotently.
    - `datasets/mdb.py` provides per track: mix path, drum-stem path and reference as `Onsets`.
    - The CLI only calls the API (test for Success Criterion 9).
  - Verify:
    - Unit test with a mini fixture of the annotation file.
    - `uv run stickler fetch mdb` reports 23 tracks.
  - Dependencies: 1 · Files: `src/stickler/{api,cli}.py`, `src/stickler/datasets/mdb.py`, tests

- [x] **Task 3: Adapter contract and dummy adapter** (M)
  - Acceptance:
    - `adapters.py` calls adapters via `uv run --project`, reads `meta.json` and logs errors without aborting.
    - `adapters/_common` provides device selection, timing and peak RSS.
    - A dummy transcriber under `tests/fixtures/` can be integrated through config only (Success Criterion 6).
  - Verify: `uv run pytest tests/test_adapters.py`
  - Dependencies: 1 · Files: `src/stickler/adapters.py`, `adapters/_common/*`, tests/fixtures

- [x] **Task 4: Transcriber adapter `adt_str` (CPU)** (M)
  - Acceptance:
    - `stickler setup --adapter adt_str` builds the environment and loads `setting-tau-0.8`.
    - `run.py` writes `drums.mid` with GM pitches and `meta.json`.
    - The adapter README names source, commit and license.
  - Verify:
    - `uv run pytest -m adapters -k adt_str` (10 s clip → valid MIDI).
    - Manual: view the MIDI of an MDB track in MuseScore.
  - Dependencies: 3 · Files: `adapters/transcribers/adt_str/*`, `src/stickler/api.py` (setup)

- [ ] **Task 5: `stickler run` and `stickler eval` with cache** (M)
  - Acceptance:
    - `run` computes the combinations active in `config/benchmark.yaml` over a dataset.
    - `eval` writes `results/metrics.csv`.
    - A second `run` has only cache hits (Success Criterion 7).
  - Verify:
    - Unit test with the dummy adapter (cache, CSV columns).
    - Real run of `none` × `adt_str` over MDB.
  - Dependencies: 2, 3, 4 · Files: `src/stickler/{api,cli,runner,cache}.py`, `config/benchmark.yaml`, tests

### Checkpoint A
- [ ] All tests green, `metrics.csv` with plausible F1 values for `none` × `adt_str` (kick clearly > 0.5)
- [ ] Review with the user

## Phase 2: GPU (early, because it is risky)

- [x] **Task 6: ROCm spike and `stickler doctor`** (M)
  - Acceptance:
    - `setup --device rocm` installs `torch[device-gfx1152]` into the `adt_str` environment.
    - `doctor` reports GPU, environments, HF login and MuseScore.
    - GPU and CPU results deviate by at most 0.01 F1; runtimes are compared.
    - The channel decision (7.14 vs. 10.x) is recorded in `docs/adr/0003-rocm-kanal.md`.
  - Verify: `uv run stickler doctor`, comparison run on 3 MDB tracks
  - Dependencies: 5 · Files: `src/stickler/{api,doctor}.py`, `adapters/_common/*`, ADR

## Phase 3: Candidates across the board

- [x] **Task 7: Separator `demucs` (adefossez fork, `htdemucs_ft`)** (S)
  - Acceptance: provides `drums.wav`, cpu and rocm. README with source, commit and license.
  - Verify: `pytest -m adapters -k demucs`, run `demucs` × `adt_str` on MDB
  - Dependencies: 5 (6 for rocm) · Files: `adapters/separators/demucs/*`, `config/benchmark.yaml`

- [x] **Task 8: Separator `roformer` (python-audio-separator)** (S)
  - Acceptance: checkpoint with drum stem selected and justified in `docs/adr/0004-roformer-checkpoint.md`. Provides `drums.wav`.
  - Verify: `pytest -m adapters -k roformer`, run on MDB
  - Dependencies: 5 · Files: `adapters/separators/roformer/*`, ADR

- [x] **Task 9: Transcriber `adtof` (ADTOF-pytorch)** (M)
  - Acceptance: 5 classes mapped to GM pitches, valid MIDI.
  - Verify: `pytest -m adapters -k adtof`, run on MDB
  - Dependencies: 5 · Files: `adapters/transcribers/adtof/*`, `config/classes.yaml`

- [x] **Task 10: Transcribers `muscriptor_s` and `muscriptor_m`** (M)
  - Acceptance: Only the drum track is taken from the multi-instrument output. If the HF login is missing, a clear error message is shown.
  - Verify: `pytest -m adapters -k muscriptor`, run on MDB
  - Dependencies: 5, user login · Files: `adapters/transcribers/muscriptor/*`

- [x] **Task 11: Transcriber `yourmt3`** (M, risk): runnable on the first attempt; smoke test on 10 s of MDB mix, because the model detects nothing in the synthetic clip
  - Acceptance: The inference from the HF Space code runs locally with a pinned commit; the drum track comes out as GM MIDI. If this fails after 2 attempts: remove the candidate via ADR.
  - Verify: `pytest -m adapters -k yourmt3`
  - Dependencies: 5 · Files: `adapters/transcribers/yourmt3/*`

- [ ] **Task 12: Transcriber `drumsep_onset`** (M)
  - Acceptance: The 6-stem model DrumSep (MDX23C) and librosa onset detection per stem yield GM MIDI.
  - Verify: `pytest -m adapters -k drumsep`, run on MDB
  - Dependencies: 5 · Files: `adapters/transcribers/drumsep_onset/*`

### Checkpoint B
- [ ] Full matrix on MDB: every combination yields a MIDI or a logged error (Success Criterion 2)
- [ ] Review with the user

## Phase 4: Report and own songs

- [x] **Task 13: HTML report** (M): `stickler report` writes a stdlib-only HTML file; `score_records` now adds `audio_seconds` and `peak_rss_mb` (RTF, RAM)
  - Acceptance:
    - `stickler report` produces `results/report.html`.
    - Content: ranking by macro-F1, F1 per class (5/3-class), runtime, RTF, RAM and CPU vs. GPU.
    - Note on possible training-data overlap for MDB.
  - Verify: Unit test on the content; open manually in the browser
  - Dependencies: 5 · Files: `src/stickler/report.py`, tests (no template engine: standard library only)

- [x] **Task 14: Beat adapter `beat_this`** (S): CPU only (15 s per song); ROCm is dropped, as with ADTOF, because the GPU has never been faster so far (ADR 0003)
  - Acceptance: `beats.json` with beats and downbeats, cpu and rocm.
  - Verify: `pytest -m adapters -k beat_this`
  - Dependencies: 3 · Files: `adapters/beats/beat_this/*`

- [ ] **Task 15: Own songs: loader, alignment, click check** (M)
  - Acceptance:
    - `references/own/<song>.mid` + `.yaml` are mapped onto audio time via the beat positions.
    - `stickler align` produces a click-check WAV.
    - The song enters `run`/`eval` (Success Criterion 4).
  - Verify: Unit tests for `align` (synthetic tempo rubato); the user listens to the click-check WAV
  - Dependencies: 5, 14, user MIDI · Files: `src/stickler/{align,datasets/own}.py`, tests

- [ ] **Task 16: ENST application and loader** (S)
  - Acceptance: `docs/enst-request.md` as a draft for the user. `datasets/enst.py` loads the dataset as soon as `data/enst/` exists, otherwise it is skipped.
  - Status 2026-11-12: request draft done (`docs/enst-request.md`, licence summarised). The loader waits for the data, so it can be built against the real folder layout.
  - Verify: Unit test with a mini fixture
  - Dependencies: 1 · Files: `docs/enst-request.md`, `src/stickler/datasets/enst.py`, tests

### Checkpoint C
- [ ] Report with MDB and at least one own song (Success Criteria 3 and 4)
- [ ] Review with the user: choose the winning pipeline, `docs/adr/0005-gewinner-pipeline.md`

## Phase 5: Notes

- [x] **Task 17: Quantization and MusicXML** (M): stdlib MusicXML writer, music21 only as a dev dependency for round-trip tests; RATATATA (ADTOF + Demucs): 1811 hits → 126 bars of 4/4
  - Acceptance:
    - `notation.py` quantizes to the beat grid (1/16 and eighth-note triplets) and filters ghost notes via a velocity threshold.
    - MusicXML with time signature, percussion staff and note heads for cymbals.
  - Verify: Unit tests (quantization, triplet detection, valid MusicXML via a music21 round trip)
  - Dependencies: 14 · Files: `src/stickler/notation.py`, tests

- [x] **Task 18: `stickler notate` end to end** (S): MusicXML, PDF via MuseScore (verified: MuseScore 4.7.5 renders RATATATA, 4 pages, 140 BPM, 4/4), `--drums` export, default pipeline demucs+adtof
  - Acceptance: Audio → winning pipeline → MusicXML. PDF, if MuseScore 4 (Flatpak) is installed (Success Criterion 5).
  - Verify: Notate "Easy Fill Ins", open it in MuseScore and compare with the original PDF
  - Dependencies: 13, 17 · Files: `src/stickler/{api,cli}.py`

### Checkpoint D
- [ ] All 9 success criteria from SPEC.md met
- [ ] Final review with the user

## Phase 5b: Rented GPU for development (RunPod, decided 2026-11-12)

- [~] **Task 19: CUDA environments for adapters** (M): implemented and unit-tested (locked versions via `uv export`, torch from cu128 → cu130 → cu126, `doctor` shows NVIDIA GPU and CUDA envs); real check on the first pod still open
  - Acceptance: `stickler setup --device cuda` builds `.venv-cuda` from the adapter's direct dependencies with torch/torchaudio at the `uv.lock` version from the PyTorch CUDA index; `--device gpu` uses it; adapter files untouched.
  - Verify: unit tests with mocked subprocess; real check on the first pod (`stickler doctor`, smoke tests with `--device gpu`)
- [x] **Task 20: Cache migration** (M): done on 2026-11-12 after the owner stopped the laptop runs (sustained 95 °C; the laptop timings were already measured). v2 key = input content + adapter id + code without comments/docstrings; `stickler cache-migrate` moved all 169 entries, evaluation identical before and after. The adapters' run.py/setup.py/pyproject.toml can now be translated without losing results (still planned for after the benchmark).
  - Acceptance: cache key = input content + adapter id + comment-insensitive code digest (AST for .py, parsed TOML) without the device; a migration moves every existing entry to its new key; `stickler eval` gives identical numbers before and after. Then translate the adapters' run.py/setup.py/pyproject.toml.
- [~] **Task 21: `stickler remote`** (M): implemented and unit-tested (bootstrap, rsync of code/data/audio/cache, CUDA setup, live run output, cache download, pod stop also on failure; HF token via stdin, API key from RUNPOD_API_KEY); first real run pending (needs Task 20 first so GPU results count as cache hits)
  - Acceptance: rsync code, required audio (MDB, own songs under the same `~`-relative paths) and cache to an SSH host; remote setup (uv, CUDA envs, HF token from env); run a config with `--device gpu`; rsync new cache entries back; optional pod stop via RunPod API (`RUNPOD_API_KEY`).
  - Verify: unit tests for command construction; first real run: RoFormer on the own songs (Secure Cloud, EU).

## Phase 6: Later (noted by the user, 2026-11-12)

Not planned yet, just recorded. Before starting each one, extend SPEC.md and break it into tasks.

- [ ] **Release pipeline: Flatpak and AppImage with every release**
  - Wish: A new release tag `vN` (ADR 0006) automatically builds a Flatpak and an AppImage.
  - Open points:
    - **Dependency:** Requires the GTK interface.
    - **Size:** The model environments are large (PyTorch per adapter, weights up to ~760 MB). It needs to be decided whether weights and environments are only loaded on first start.
    - **Licenses:** NC weights must not go into a distributed package (ADR 0002).
    - **CI:** The pipeline needs a CI service. Codeberg is out of the question, as it mostly disallows AI-generated programs.

- [ ] **Everything in English** (mostly done on 2026-11-12)
  - Done: code comments, docstrings, messages, tests, README, SPEC, ADRs, tasks, adapter READMEs, CONSTRAINTS.md, CLAUDE.md; commit messages in English from now on.
  - Remaining, only after the MDB benchmark has finished successfully (owner's decision): the adapters' `run.py`, `setup.py` and `pyproject.toml`. First make the cache key ignore comments (e.g. hash the AST / parsed TOML), migrate existing cache entries from old to new keys so no result is lost, then translate.

- [ ] **Design the interface together (before any GTK code)**
  - Wish (2026-11-12): design a beautiful interface together with the owner, following current design principles, including the GNOME Human Interface Guidelines.
  - Approach: collect the user flows (drop a song → separation and transcription with progress → sheet music preview → export of notes and drum track), then mockups (e.g. as an artifact or Penpot/SVG) to discuss and iterate before implementing in GTK 4 + libadwaita.

- [ ] **App feature: export the drum track**
  - Wish (2026-11-12): a button in the app that exports the separated drum stem ("can't hurt to have it").
  - Implementation: the stem already exists as an intermediate result. `transcribe_song` should return its path, and the GUI saves it as WAV or FLAC (FLAC via ffmpeg).

- [ ] **App icon in GNOME style**
  - Wish: An icon in the style of the GNOME app icons by Daudix (https://daudix.one/design/).
  - Implementation: Create as SVG following the GNOME HIG, with a symbolic variant.

- [ ] **Readable sheet music: repeat signs** (owner, 2026-11-12)
  - Today every hit is written out. Detect repeated bars and passages (identical quantized bars, 1-bar and 2-bar repeat signs, repeat barlines with voltas) and fold them, so the sheet music reads like a human transcription.
  - Keep the unfolded version available (e.g. for the benchmark and for playback).

- [ ] **Two pipeline modes for the app: "Fast" and "Quality"** (owner, 2026-11-12)
  - Working hypothesis from the partial results: Fast = Demucs + ADT_STR (~6 min per 3.5-minute song on the laptop CPU), Quality = RoFormer + ADT_STR (~30 min).
  - Before deciding: finish both runs, run RoFormer on the own songs (~4.5 h), and measure `htdemucs` (single model, ~4x faster than `htdemucs_ft`) as a faster Fast candidate.
  - ADT_STR has 26 classes (ride, china, open hi-hat, tom heights) and gives richer notation than ADTOF's 5 classes; the 5-class benchmark does not show this.

- [ ] **Prettier README badges** (small)
  - Wish (2026-11-12): nicer-looking badges in the README, in the style of https://shieldcn.dev/showcase, ideally with a gradient effect.
  - Must include a few nonsense badges as well (e.g. "drums: loud", "neighbours: annoyed").

- [ ] **Ultrareview once the application is finished**
  - The user starts it themselves with `/code-review ultra`. I cannot trigger it.
