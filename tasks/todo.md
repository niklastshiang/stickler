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

- [x] **Task 5: `stickler run` and `stickler eval` with cache** (M): ticked 2026-11-15 by the owner; built early, releases 1–3 rest on it.
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

- [x] **Task 15: Own songs: loader, alignment, click check** (M): ticked 2026-11-15 by the owner; `datasets/own.py` and `stickler align` are in use since release 1.
  - Acceptance:
    - `references/own/<song>.mid` + `.yaml` are mapped onto audio time via the beat positions.
    - `stickler align` produces a click-check WAV.
    - The song enters `run`/`eval` (Success Criterion 4).
  - Verify: Unit tests for `align` (synthetic tempo rubato); the user listens to the click-check WAV
  - Dependencies: 5, 14, user MIDI · Files: `src/stickler/{align,datasets/own}.py`, tests

- [x] **Task 16: ENST application and loader** (S): ticked 2026-11-15 by the owner; `docs/enst-request.md` and `datasets/enst.py` (`stickler fetch enst`) exist.
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

- [x] **Task 19: CUDA environments for adapters** (M): implemented and unit-tested (locked versions via `uv export`, torch from cu128 → cu130 → cu126, `doctor` shows NVIDIA GPU and CUDA envs); checked for real on 2026-11-12 on a RunPod RTX 4090: all adapters set up and ran with `--device gpu`
  - Acceptance: `stickler setup --device cuda` builds `.venv-cuda` from the adapter's direct dependencies with torch/torchaudio at the `uv.lock` version from the PyTorch CUDA index; `--device gpu` uses it; adapter files untouched.
  - Verify: unit tests with mocked subprocess; real check on the first pod (`stickler doctor`, smoke tests with `--device gpu`)
- [x] **Task 20: Cache migration** (M): done on 2026-11-12 after the owner stopped the laptop runs (sustained 95 °C; the laptop timings were already measured). v2 key = input content + adapter id + code without comments/docstrings; `stickler cache-migrate` moved all 169 entries, evaluation identical before and after. The adapters' run.py/setup.py/pyproject.toml can now be translated without losing results (still planned for after the benchmark).
  - Acceptance: cache key = input content + adapter id + comment-insensitive code digest (AST for .py, parsed TOML) without the device; a migration moves every existing entry to its new key; `stickler eval` gives identical numbers before and after. Then translate the adapters' run.py/setup.py/pyproject.toml.
- [x] **Task 21: `stickler remote`** (M): implemented and unit-tested (bootstrap, rsync of code/data/audio/cache, CUDA setup, live run output, cache download, pod stop also on failure; HF token via stdin, API key from RUNPOD_API_KEY); real runs on 2026-11-12: own-roformer, the rest of MDB and own (0 errors), pod stopped automatically via the REST API v2
  - Acceptance: rsync code, required audio (MDB, own songs under the same `~`-relative paths) and cache to an SSH host; remote setup (uv, CUDA envs, HF token from env); run a config with `--device gpu`; rsync new cache entries back; optional pod stop via RunPod API (`RUNPOD_API_KEY`).
  - Verify: unit tests for command construction; first real run: RoFormer on the own songs (Secure Cloud, EU).

## Phase 5c: Getting the most out of the existing models (decided 2026-11-13)

Method: tune on MDB and ENST, keep the own songs (the target music) for the final check only.

- [x] **Quality combo** (`combos` in configs, stickler.combine): MuScriptor medium on the Demucs stem for KD/SD/TT + ADTOF on the mix for HH/CY. Macro-F1 (5 classes) own 0.815 (best single 0.788), MDB 0.784 (best single 0.778). Chosen on the own songs, confirmed on MDB.
- [x] **ADTOF activations, fusion and per-class thresholds** (stickler.peaks, stickler.fusion, `stickler tune`, `fusions` in configs). The harness peak picking reproduces ADTOF's MIDI exactly. Result: no gain on the target music. Tuned on MDB (thresholds and weights): MDB 5-class F1 rises a lot (TT 0.35 → 0.54, SD 0.71 → 0.79), but the own songs drop from 0.788 to 0.729 (SD threshold 0.04 fits MDB's jazz ghost notes and adds false snares in rock/metal; TT threshold 0.46 misses toms). Weights only, ADTOF thresholds: own 0.788 → 0.771. ADTOF's default thresholds and the plain mix transfer best. Re-check once ENST is in (tuning on MDB + ENST).
- [x] **Voting across pipelines** (`votes` in configs, stickler.vote): no overall gain. Chosen per class on MDB among 7 pipelines (single, 2 of 3, 3 of 5): MDB improves a lot (TT 0.35 → 0.65), the own songs drop overall from 0.788 to 0.773 (TT +0.04, HH +0.03, but KD, SD and especially CY worse). Same pattern as the fusion: MDB favours separated stems, the own music does not.
- [x] **Cross-validated tuning on the own songs** (25 songs, 5 folds, 2026-11-13): ADTOF's default thresholds are already close to optimal on the target music (macro 0.770 → 0.774 cross-validated). Only stable change: cymbal threshold 0.30 → 0.44, chosen in all five folds, cymbal F1 on unseen songs 0.680 → 0.710 (config: fusion `adtof_cy`, combo `quality_cy`; MDB −0.004). Fusion with the Demucs stem gives nothing here either (0.768).
- [x] **25 own songs (2026-11-13):** Quality 0.776 vs Fast 0.770 (pooled); per song better on 16, worse on 2 of 25 (mean +0.015, 95 % CI −0.001…+0.030). The first 10 songs (on which the combination was chosen) +0.028, the 15 new ones +0.007. Toms no longer favour MuScriptor (0.65 vs 0.65), snare does slightly (0.90 vs 0.88). Cymbal threshold 0.44: pooled cymbals +0.03, per song ±0, costs on ENST/MDB: not used. Owner: keep Quality (it can be clearly better for a particular song), Fast stays ADTOF on the mix with its defaults.
- [ ] **After release 1 (owner, 2026-11-13):** (1) error analysis (release 3) on the own songs: class confusions, misses vs false hits, a click track at error spots to check whether the reference or the model is wrong; (2) new candidates: DrumSep + onsets (Task 12), a fresh search for 2026 models, MuScriptor large for Quality. No fine-tuning (owner: makes no sense).
- [ ] **Lesson so far**: choices made on MDB do not transfer to the owner's rock/metal recordings. Next: check ENST (styles incl. rock and metal), and tune on more own-genre songs once the owner has found them; until then the quality combo (chosen on the own songs, confirmed on MDB) stays the best pipeline.
- [x] **Measure the end product** (`grid` in configs, stickler.grid, scored as `@grid`): notes snapped to the Beat This! grid like the sheet music. Snapping costs almost nothing on the own songs (quality 0.815 → 0.812, ADTOF on the mix 0.788 → 0.793) and ~0.02 on MDB (swing, jazz timing).
- [x] **Consensus across repeated bars** (`consensus` in configs, scored as `@rep`): no gain. Best setting on MDB (similarity 0.6, add at 2/3, never remove) +0.002 on MDB, ±0.001 on the own songs. Diagnosis on the own songs: 357 hits added in 1562 bars, only 31 % correct; what one of several similar bars lacks is mostly a real variation (hi-hat left out before a fill, crash instead of hi-hat), while the models' errors repeat in every bar. Not used in the configs; the bar similarity may still serve the repeat signs in the sheet music.
- [ ] **More reference songs in the owner's genres** (rock/metal): with 10 songs, tuning on them is not possible without overfitting; with ~30 they could be split for tuning and testing.
- [ ] **Finer classes for notation** (owner, 2026-11-13: later): open/closed hi-hat, ride/crash; ADTOF does not distinguish them, MuScriptor does.

## Phase 7: Release 3, error analysis (approved 2026-11-14, SPEC.md "Release 3")

- [x] **Task 22: Error categories** (M)
  - Acceptance:
    - `errors.categorise(ref, est)` gives per class: tp, missed, invented, off time (same class, 50–100 ms) and confusions as pairs A → B (±50 ms, one-to-one), with the times of every error spot.
    - confused + off time + missed = fn and confused + off time + invented = fp of `evaluate.score` for the same onsets.
  - Verify: `uv run pytest tests/test_errors.py` (synthetic onsets for every category, a property test of the sums on random onsets)
  - Dependencies: none · Files: `src/stickler/errors.py`, `tests/test_errors.py`

- [x] **Task 23: `stickler errors` end to end** (M)
  - Acceptance:
    - The record building of `evaluate_benchmark` is shared with `api.error_breakdown(config, pipelines)`; default pipelines `none+adtof` and `combo+quality`.
    - `results/own/errors.csv` (per song, pipeline, class and category, confusion pairs) and a summary table in the CLI.
    - `results/own/summary.csv` is byte-identical before and after (`stickler eval`).
  - Verify: unit tests with the fake MDB fixture; `uv run stickler errors --config config/own.yaml` on the 25 songs, sums checked against `metrics.csv`
  - Dependencies: 22 · Files: `src/stickler/{api,cli,errors}.py`, `tests/test_{api,cli}.py`

### Checkpoint E
- [ ] Breakdown reviewed with the owner (largest error sources, top confusions), before any listening

- [x] **Task 24: Snippets** (M): trial on 2026-11-14 with 3 real spots: a soft marker tone mixed into the music was inaudible (2-4x quieter than the music, in the hi-hat range); now music left, click right (as `align`'s click.wav), plus a 1.25 s loop of just the spot, which the owner judged at half speed.
  - Acceptance:
    - `listen.render` writes a WAV of ~4 s around the spot: drum stem and mix, played once plain and once with a click at the spot; `listen.render_loop` only the spot, for a loop.
    - Stems only from the cache; a missing stem is a clear error, never a model run.
  - Verify: tests on a generated WAV (length, marker position, levels); owner listens to 3 snippets and confirms the marker is clear and does not hide the hit
  - Dependencies: 22 · Files: `src/stickler/listen.py`, `src/stickler/api.py`, `tests/test_listen.py`

- [x] **Task 25: Draw the sample** (S)
  - Acceptance:
    - `errors.draw_sample(spots, per_class_side=10, seed)`: 10 `ref` and 10 `est` spots per class from the union of the pipelines' error spots, each spot listing the pipelines it belongs to; random order; same seed → same sample.
    - `data/own/_listening/sample.csv` is written once; drawing again refuses.
  - Verify: `uv run pytest tests/test_errors.py tests/test_api.py -k sample`
  - Dependencies: 23 · Files: `src/stickler/{errors,api}.py`, tests

- [x] **Task 26: `stickler listen`** (M)
  - Acceptance:
    - Asks spot by spot "Is there a <class> hit at the marker?" without saying who claims it; answers y / n / u, r = repeat the snippet, l = loop the spot, s = loop at half speed (a loop runs until Enter), q = quit (a letter plus Enter).
    - Verdicts appended to `data/own/_listening/verdicts.csv`; a new start resumes at the first unjudged spot; shows progress (k / 100).
    - The CLI only calls the API; the player (`ffplay`) is injected.
  - Verify: CliRunner tests with a fake player (answer, repeat, quit, resume); owner judges 3 spots as a trial
  - Dependencies: 24, 25 · Files: `src/stickler/{listen,api,cli}.py`, tests

- [x] **Task 29: Badges for `stickler listen`** (M) (SPEC.md, "Gamification")
  - Acceptance:
    - `rewards.earned(events)` gives the 11 badges from an events log (spot judged, loop played, half-speed loop, session started; with timestamps, without answers); banner texts in drummer humour.
    - `stickler listen` records the events in `data/own/_listening/events.csv`, shows a banner when a badge is new and the collection on `q` and at the end.
    - Badges never depend on verdicts, speed or results (by construction: events carry no answer; test).
  - Verify: `uv run pytest tests/test_rewards.py tests/test_api.py tests/test_cli.py -k "reward or badge or listen"`; owner starts listening (the first 3 spots are also Task 26's trial)
  - Dependencies: 26 · Files: `src/stickler/{rewards,api,cli}.py`, `tests/test_rewards.py`, tests

### Checkpoint F
- [x] The owner has judged all 100 spots (done 2026-11-14; owner: "partly very difficult")

- [x] **Task 27: Corrected scores** (M)
  - Acceptance:
    - `errors.correct(counts, verdicts)`: per pipeline and class r_ref and r_est from the pipeline's own spots, corrected tp/fp/fn and F1, 95 % bootstrap interval, n and share of *unclear*, bounds with *unclear* counted either way.
    - `stickler eval --config config/own.yaml` writes `results/own/corrected.csv` once verdicts exist; `report.html` shows measured and corrected values side by side.
  - Verify: tests with hand-computed counts and synthetic verdicts (can be built during Checkpoint F); `metrics.csv`/`summary.csv` unchanged
  - Dependencies: 23, 25 · Files: `src/stickler/{errors,api,report}.py`, tests

- [x] **Task 30: The finale** (S) (SPEC.md, "Gamification")
  - Acceptance:
    - After spot 100, and on every later `stickler listen`: a showdown of Fast against Quality (measured and corrected macro-F1, winner per class) and the badge collection.
    - The README's nonsense row gets `ears: certified` (scripts/badges.py).
  - Verify: CliRunner test with a fake API; owner sees the finale after spot 100
  - Dependencies: 27, 29 · Files: `src/stickler/{api,cli}.py`, `scripts/badges.py`, tests

- [x] **Task 28: Report and release 3** (S)
  - Acceptance:
    - `docs/report.md`: section "Errors and reference quality" (breakdown, top confusions, corrected F1 with intervals, limits); section 1 quotes measured and corrected values.
    - README roadmap and status; release steps of ADR 0006; release notes in Keep a Changelog style.
  - Verify: all 5 success criteria of SPEC.md "Release 3"; `scripts/check.sh task`
  - Dependencies: 27, 30 · Files: `docs/report.md`, `README.md`, `tasks/todo.md`, version files

### Checkpoint G
- [x] All success criteria of SPEC.md "Release 3" met, review with the owner, then release 3

## Phase 8: GTK application, module `engine-api` (approved 2026-11-14, SPEC.md "GTK application")

- [x] **Task 31: The harness on Python 3.12–3.14** (S): done 2026-11-14. Found on the way: uv settings of the harness (`UV_PYTHON`, `UV_PROJECT_ENVIRONMENT`, `UV_PROJECT`, `VIRTUAL_ENV`) were inherited by the adapters' `uv run`/`uv sync`, so a harness on 3.14 ran the 3.12 adapters on 3.14 (22 failing tests), and `UV_PROJECT_ENVIRONMENT` would have built an adapter's environment in the harness's place; adapter processes now get an environment without them (test). `.python-version` keeps 3.12 the default for development.
  - Acceptance:
    - `requires-python` of the harness is `>=3.12,<3.15`; `uv.lock` follows; the adapters' files are untouched.
    - CI runs the checks on 3.12 and 3.14.
  - Verify: `uv run --python 3.14 pytest -q` and `scripts/check.sh task` (3.12) both green
  - Dependencies: none · Files: `pyproject.toml`, `uv.lock`, `.github/workflows/check.yml`, `SPEC.md` (Tech Stack)

- [x] **Task 32: Measure an interrupted setup** (S): done 2026-11-14, results in SPEC.md (`engine-api`, resolved question 2). `uv sync` resumes well enough; `torch.hub` restarts and leaves a `.partial`; readiness is misjudged after an interruption (now in Task 35); the Beat This! weight server returned HTTP 500 throughout, so the weight case was measured against a local server.
  - Acceptance:
    - On a copy of `adapters/beats/beat_this` in a scratch adapters root: `setup` is killed during `uv sync` and during the weight download; a second `setup` is timed against a fresh one, and the result works (`doctor`).
    - The result is written into SPEC.md (`engine-api`, resolved question 2): resumes, or starts over and what the fix would be.
  - Verify: the numbers in SPEC.md; the real adapter folders and the cache are unchanged (`git status`, `stickler cache-digests`)
  - Dependencies: none · Files: `SPEC.md`

- [x] **Task 33: Progress for `transcribe_song` and `notate`** (M): done 2026-11-14. `Step` also names the model (`adapter`); a step is `cached` when `runner.cached_or_run` took it from the cache (new field `AdapterResult.cached`). On Eye of the Tiger: four steps, MusicXML identical to before.
  - Acceptance:
    - `api.Step` (id, index, total, state `started`/`done`, `cached`) and a `progress` parameter on both functions; the steps are known before the first one starts.
    - Step ids `separate`, `transcribe`, `beats`, `engrave`, `pdf`; a cached step reports `done` with `cached`.
    - `stickler notate` prints the steps; the CLI still holds no logic.
  - Verify: `uv run pytest tests/test_api.py tests/test_cli.py -k progress` (Fast, a pipeline with a separator, a fully cached song); `uv run stickler notate` on a cached own song
  - Dependencies: none · Files: `src/stickler/{api,runner,cli}.py`, tests

- [x] **Task 34: Cancellation of an analysis** (M): done 2026-11-14. `CancelToken` is a `threading.Event` with `cancel()` (so `run_benchmark` accepts it too); a running adapter is polled every 50 ms and its group killed with SIGKILL, its cache folder removed; between steps the token stops the call before the next one starts. Noticed, not changed: Ctrl+C in `stickler notate` does not reach the adapter (own session), so the model keeps running after the CLI exits; the CLI could turn Ctrl+C into a cancel.
  - Acceptance:
    - `api.CancelToken` and `api.Cancelled`; `cancel` on `transcribe_song` and `notate`.
    - A set token ends the adapter's process group within 1 s; the cancelled step leaves nothing a later run takes for a result.
  - Verify: test with a sleeping dummy adapter (raises within 1 s, no process of the group left, second run computes again)
  - Dependencies: 33 · Files: `src/stickler/{api,runner,adapters}.py`, tests

- [x] **Task 35: Readiness** (S): done 2026-11-14. `adapters.missing_setup(spec, device)` is the one check (`.venv` present and `uv sync --check --offline`, or the GPU environment that would run; marker `weights/.setup-complete`, so deleting the weights drops it too). Adapters missing from the registry are not listed (setup cannot fix a missing folder). `SetupMissing` is a `RuntimeError`, so the CLI prints it. On the real checkout `mode_ready("fast")` is empty after `stickler setup --adapter beat_this` (7.5 s, no download); every other adapter with a `setup.py` reads "weights missing" in `doctor` until `stickler setup` has run once for it, and `--mode quality` raises `SetupMissing` until then.
  - Acceptance:
    - `api.mode_ready(mode)` returns the adapters of the mode that are not set up (environment or weights missing).
    - An environment counts only if `uv sync --check --offline` passes (a killed `uv sync` leaves an empty `.venv`); weights count only if `setup.py` finished, recorded by a marker the harness writes after it succeeds; `setup` removes stray `*.partial` files (Task 32). The marker lives outside the files that make up the cache key.
    - `doctor` uses the same check.
    - `transcribe_song` raises `api.SetupMissing` naming them before any adapter is started.
  - Verify: tests with dummy adapters: no environment, an empty `.venv`, weights with only a `.partial`, complete; on the real checkout `mode_ready("fast")` is empty after one `stickler setup --adapter beat_this` (writes the marker for an existing install)
  - Dependencies: none · Files: `src/stickler/{api,doctor}.py`, tests

- [x] **Task 36: Progress and cancellation for `setup_adapters`** (M): done 2026-11-14. `setup_adapter` is split into `setup_environment` and `setup_weights`, which the API runs as steps (`Step.adapter` names the adapter); `uv sync` and `setup.py` run in their own process group. Building `.venv-rocm`/`.venv-cuda` (developer tools) is cancelled only between steps. Tests: a hanging `setup.py` and a stand-in `uv` on `PATH` are cancelled, the next setup finishes. On the real checkout `stickler setup --adapter beat_this` prints both steps.
  - Acceptance:
    - `progress` reports `environment:<adapter>` and `weights:<adapter>`; `cancel` ends the running `uv` or `setup.py` process group and raises `Cancelled`.
    - `stickler setup` prints the steps.
    - What Task 32 found about resuming holds after a cancel.
  - Verify: tests with a dummy adapter and a stand-in for `uv`, without network; `uv run stickler setup --adapter beat_this` on the set-up checkout reports both steps
  - Dependencies: 32, 34 · Files: `src/stickler/{api,adapters,cli}.py`, tests

- [x] **Task 37: Bar map** (M): done 2026-11-14. `notation.engrave` returns `Engraving(musicxml, bars)`; `to_musicxml` wraps it. A last bar that runs past the last beat ends at the average beat length. Eye of the Tiger (cached, 0.19 s): 110 entries without gaps; the written bars are the 43 the score shows (46 `<measure>` elements, the first four one multi-measure rest; SPEC criterion 4 reworded accordingly); with the rest collapsed the order equals Verovio's timemap (107 entries; Verovio run via `uvx`, not a dependency).
  - Acceptance:
    - `notation.engrave(...)` returns the MusicXML and `bars`: per song bar in played order its start and end in seconds and the written bar's number; `to_musicxml` is unchanged for its callers.
    - `api.Notation.bars` carries it.
    - Repeats, a pickup and a multi-bar rest are covered.
  - Verify: `uv run pytest tests/test_notation.py -k bar_map`; Eye of the Tiger: 110 entries, times rise without gaps, written bars are exactly the 46 of the MusicXML, and the order matches Verovio's expanded timemap
  - Dependencies: none · Files: `src/stickler/{notation,api}.py`, tests

- [x] **Task 38: Corrections** (M): done 2026-11-14. Pure function `notation.corrected_grid`; `half` keeps the beats on the first downbeat's parity and adds one beat before the song when that drops beat 0, so no hit falls off the grid; `first_downbeat` is 1-based on the corrected beats. Given `corrections` take over `simplify`/`repeats`; impossible values raise in `Corrections` itself, before any model runs. Eye of the Tiger (cached): every correction 0.16–0.18 s, no adapter started, 1375 hits each time; `half`/`double` keep 110 bars (2 or 8 beats each), 3/4 gives 147, a downbeat on beat 2 gives 111 (pickup). The CLI has no correction options (not part of the task).
  - Acceptance:
    - `api.Corrections(tempo, beats_per_bar, first_downbeat, simplify, repeats)`; `notate(..., corrections=...)`; today's `simplify` and `repeats` parameters keep working.
    - A pure function gives the corrected beats and downbeats; the hits never change; the bar map follows the corrected grid.
    - No adapter is started for a correction on a cached song.
  - Verify: tests (`half` then `double` is the original grid; meter and downbeat overrides give the expected bars; a test fails if an adapter is started); each correction of a cached own song takes < 1 s
  - Dependencies: 37 · Files: `src/stickler/{notation,api}.py`, tests

- [x] **Task 39: Detected hits as audio** (S): done 2026-11-14; the owner listened to Eye of the Tiger with the clicks: they sit on the drums. `audio.clicks` makes the clicks for `render_hits` and `align`'s click track alike; `render_hits` takes the song's length from ffprobe. Eye of the Tiger: 1375 hits, 245.64 s like the song, 0.18 s to render.
  - Acceptance:
    - `api.render_hits(transcription, dest)`: a mono WAV as long as the song, one click per hit, three pitches (kick, snare/toms, cymbals); `align`'s click track uses the same clicks.
  - Verify: test on a generated song (length, energy at the hit times); the owner listens to one own song with the clicks and confirms they sit on the drums
  - Dependencies: none · Files: `src/stickler/{api,audio}.py`, tests

- [x] **Task 40: Ctrl+C cancels `stickler notate` and `stickler setup`** (S) (owner, 2026-11-14; part of release 4): done 2026-11-14. A second Ctrl+C stops at once (for ROCm/CUDA builds, which are cancelled between steps only). By hand: SIGINT to the CLI's process group during ADTOF on an uncached clip; model and `uv run` gone after 100 ms, CLI after 200 ms with "Cancelled" and exit code 130, no cache entry left.
  - Today the adapter runs in its own session, so Ctrl+C ends the CLI but not the model, which keeps computing in the background.
  - Acceptance:
    - Ctrl+C during `notate` or `setup` sets a `CancelToken`; the running model or `uv`/`setup.py` process group ends, the CLI prints "Cancelled" and exits with code 130.
    - The CLI still holds no logic beyond turning the signal into a cancel.
  - Verify: CLI test with a sleeping dummy adapter and SIGINT (no process of the group left, exit code 130); by hand: Ctrl+C during `uv run stickler notate` on an uncached song, then `pgrep -f run.py` finds nothing
  - Dependencies: 34, 36 · Files: `src/stickler/cli.py`, tests

### Checkpoint H
- [x] All 8 success criteria of SPEC.md `engine-api` met; review with the owner (2026-11-14: criterion 4 reworded, criterion 8 with test doubles that only gained the new parameters)
- [x] **Release 4 published on 2026-11-14** (tag v4, GitHub release): the library groundwork for the GTK application (Phase 8, Tasks 31–40).
- [x] Release of its own (owner, 2026-11-14): release 4, the groundwork for the app

## Phase 9: GTK application, module `app-shell` (approved 2026-11-14, SPEC.md "Module `app-shell`")

- [x] **Task 41: Skeleton, app environment and checks** (M): done 2026-11-14. `gi.require_version` sits in `stickler_gtk/ui/__init__.py`, so no module needs an import after code; the `Adw.Application` lives in `ui/application.py` and `main.py` only calls it. `.venv-gtk`: Python 3.14.10, PyGObject 3.56.3, GTK 4.22.5, libadwaita 1.9.4; `UV_PYTHON` keeps `.python-version` (3.12) from rebuilding it. The dashed drop area of screen 4 comes with the drop itself (Task 43).
  - Acceptance:
    - `src/stickler_gtk/` with `logic/` and `ui/`; `stickler-gtk` (entry point) opens an `Adw.ApplicationWindow` with the ID `ng.tshia.Stickler` and the empty page of screen 4 (drop area and "Open a Song…", no function yet).
    - `scripts/gtk.sh` builds `.venv-gtk` on the system Python with `--system-site-packages`, installs the project with its locked dependencies into it, prints the versions of `gi`, GTK and libadwaita, and starts the app; `scripts/gtk.sh test` runs `pytest -m gtk`.
    - CONSTRAINTS.md: coverage counts `src/stickler_gtk/logic`; `src/stickler_gtk/ui` and `main.py` are excluded like `cli.py`. A test fails if `src/stickler` or `stickler_gtk/logic` imports `gi`.
    - `packaging/ng.tshia.Stickler.desktop` (`data/` holds the datasets and is ignored).
  - Verify: `scripts/check.sh task`; `scripts/gtk.sh` shows the empty window; `scripts/gtk.sh test` (window opens)
  - Dependencies: none · Files: `pyproject.toml`, `src/stickler_gtk/*`, `scripts/gtk.sh`, `CONSTRAINTS.md`, `tests/gtk/*`, `packaging/*`

- [x] **Task 42: Translations** (S): done 2026-11-14. `stickler_gtk/i18n.py` (no GTK) with `_()`/`N_()`; the app name stays untranslated (`APP_NAME`). The tests read source and `.po` files with Python, so CI needs no gettext tools; `scripts/gtk.sh` builds the `.mo` files with `msgfmt` into `.venv-gtk/share/locale`. No `po/POTFILES`: `scripts/i18n.sh` takes the sources from git. German follows the GNOME German team's style ("Song öffnen …").
  - Acceptance:
    - `_()` through gettext (domain `stickler`), the `.mo` built from `po/` at start in development; `scripts/i18n.sh` writes `po/stickler.pot` and merges `po/de.po`.
    - Tests: a string literal shown to the user without `_()` fails; `po/de.po` without a translation for a string of the `.pot` fails.
    - The strings of Task 41 in German.
  - Verify: `uv run pytest -q tests/gtk -k translat`; `LANGUAGE=de scripts/gtk.sh` shows the empty window in German
  - Dependencies: 41 · Files: `src/stickler_gtk/i18n.py`, `po/*`, `scripts/i18n.sh`, `tests/gtk/test_translations.py`

- [x] **Task 43: Open a song, analyse, show the result** (M): done 2026-11-14. Tempo and meter come from `notation.Engraving` (the grid that was engraved, corrections included). Songs also open from the command line and "Open With" (`HANDLES_OPEN`). Real app on the laptop: a cached own song reaches the result 1.3–1.5 s after starting the app (the analysis itself 0.25 s); an uncached 60 s clip in 7.2 s with ADTOF and Beat This! running as their own processes. Found on the way: the app on Python 3.14 computed other cache keys than the CLI on 3.12 and analysed cached songs again; fixed separately (`f552ed8`).
  - Acceptance:
    - `api.song_info(path)` (title, artist, seconds) and `Notation.tempo`, `Notation.meter` in `stickler.api`, with tests.
    - `logic/session.py`: states empty → analysing → result, driven by `api.Step`; `logic/steps.py`: label and detail for each step id (screen 5).
    - Drop and "Open a Song…" (`Gtk.FileDialog`, audio filter, Ctrl+O) start Fast in a worker thread; the step list follows; the result page shows title, artist, tempo and meter in the header and a placeholder body. A dropped file that is not audio gives a toast.
    - `notate` writes into the app's cache folder (`logic/paths.py`).
  - Verify: logic tests; `scripts/gtk.sh test` with a fake `stickler.api` from drop to result; by hand: an uncached own song shows the three steps, a cached one reaches the result in < 1 s
  - Dependencies: 42 · Files: `src/stickler/api.py`, `src/stickler_gtk/logic/{session,steps,paths}.py`, `src/stickler_gtk/ui/*`, tests

- [x] **Task 44: Cancel and errors** (S): done 2026-11-14. The analysis job is `logic/analysis.py`; every analysis has a job number, so reports of a cancelled or replaced one are ignored. Error pages: models not set up (the commands, open), unreadable file, failed analysis (Try Again, technical details folded). Real models: cancel through the window's action ends ADTOF's group in 0.07 s, nothing cached. Found on the way: ending the app by a signal or closing it left a half-written cache folder, because the process ended before the cancelled worker cleaned up; the window now cancels and waits for its job on close-request (0.04 s), and SIGINT/SIGTERM close the window first (`GLibUnix.signal_add`, not the deprecated `GLib.unix_signal_add`). A second start hands the song to the running instance (GApplication).
  - Acceptance:
    - "Cancel" and Escape set the token; the window returns to the previous page within 1 s.
    - Error pages for `SetupMissing` (names the models and `stickler setup --adapter …`), a failed analysis ("Try Again", the technical message folded away) and an unreadable file.
  - Verify: logic tests for every error state; `scripts/gtk.sh test` (fake analysis cancelled, fake failure); by hand: cancel during ADTOF, `pgrep -f run.py` finds nothing
  - Dependencies: 43 · Files: `src/stickler_gtk/logic/session.py`, `src/stickler_gtk/ui/*`, tests

- [x] **Task 45: Recent songs** (S): done 2026-11-15. A song joins the list once its analysis has finished, with the analysis's title and artist; the list is written atomically. Dates older than yesterday use a translatable `strftime` pattern (German "12. November"). The app's tests point all XDG folders at a temporary folder (`tests/gtk/conftest.py`), so they never touch the user's data. Real app: Eye of the Tiger lands in `~/.local/share/stickler/recent.json`.
  - Acceptance:
    - `logic/recent.py`: the newest ten, a song opened again moves to the top, a missing file is marked and can be removed, a damaged JSON file starts an empty list; stored under the XDG data folder.
    - The empty window lists them (screen 4); a click opens the song (a cached one at once).
  - Verify: logic tests; by hand: restart keeps the list, a renamed file shows as missing
  - Dependencies: 43 · Files: `src/stickler_gtk/logic/recent.py`, `src/stickler_gtk/ui/*`, tests

- [x] **Task 46: Export: MusicXML and the drum track** (M): done 2026-11-15. When Demucs is not set up, the export sets it up itself (`api.setup_adapters`, steps in the same list; `api.mode_ready(..., drums=True)` tells); rows follow step ids, since setup and analysis number their steps each. A failed export is its own kind (no "Try Again" that would analyse again). The size uses the locale's number format (German "1,2 GB"); the minutes are a plural (`ngettext`). Real job, Eye of the Tiger: a 245.64 s FLAC in 0.6 s (stem cached from Quality). The dialogs (cost, save) were not driven by a test; the owner's check at Task 48 covers them.
  - Acceptance:
    - Export menu (screen 8, Ctrl+E) with MusicXML and the drum track; the save dialog proposes "<title>.musicxml" and "<title> (drums).flac".
    - The drum track names its cost first (`logic/exports.py`: 1.84 × the song's length, the 1.2 GB download while Demucs is not set up) and runs as a step list with "Cancel".
    - A toast says where the file went and opens it with "Open" (`Gtk.FileLauncher`).
  - Verify: logic tests (names, cost for a 4:06 song ≈ 7.5 min); `scripts/gtk.sh test` (fake export); by hand: MusicXML of a cached song, the drum track of one song
  - Dependencies: 44 · Files: `src/stickler_gtk/logic/exports.py`, `src/stickler_gtk/ui/*`, tests

- [x] **Task 47: Main menu, appearance, keyboard** (S): done 2026-11-15. The appearance circles are a `Gtk.CheckButton` group in the `Gtk.PopoverMenu`, as GNOME's own apps draw them; the shortcuts use `Adw.ShortcutsDialog` (libadwaita 1.8, replacing the deprecated `Gtk.ShortcutsWindow`), so the minimum libadwaita is now 1.8 (SPEC.md). Ctrl+W closes the window, Ctrl+Q quits through the same path as a signal (jobs cancelled and waited for). The real app starts without a GTK or CSS warning.
  - Acceptance:
    - Main menu (screen 9, F10) with the three-way appearance switch, remembered in the XDG config folder (`logic/settings.py`); follow the system by default.
    - Shortcuts window (Ctrl+?) listing Ctrl+O, Ctrl+E, Escape, Ctrl+W, Ctrl+Q, Ctrl+?, F10; "About Stickler".
  - Verify: logic tests (settings, damaged file); `scripts/gtk.sh test`; by hand: dark is kept after a restart, every action works without the mouse
  - Dependencies: 43 · Files: `src/stickler_gtk/logic/settings.py`, `src/stickler_gtk/ui/*`, tests

- [x] **Task 48: Narrow windows and the German check** (S): done 2026-11-15 (owner's look at the window is part of Checkpoint I). Breakpoint `max-width: 550sp`: the header swaps its labelled Open and Export buttons for icon buttons; minimum window size 360 × 294 (HIG). A test measures every page's minimum width in English and German: the error page needed 368 px in German, so its buttons now wrap (`Adw.WrapBox`). German: 72 strings, complete, informal ("du").
  - Acceptance:
    - Breakpoint at 400 px: the header keeps icon buttons, every page of this module fits without horizontal scrolling (screens 10/11 apply where the module has the parts).
    - `po/de.po` complete; every visible string German with `LANGUAGE=de`; German addresses the user informally ("du", owner 2026-11-14).
  - Verify: translation tests; by hand at 400 px, in German, light and dark
  - Dependencies: 46, 47 · Files: `src/stickler_gtk/ui/*`, `po/de.po`

### Checkpoint I
- [x] All 9 success criteria of SPEC.md `app-shell` met; review with the owner (2026-11-15): cancel back to where you came from is as wanted; the drum track's line in the export menu now names only the format, "As FLAC or WAV" (also on the design canvas); the appearance circles showed the radio indicator of grouped check buttons, now hidden (checked in a rendered PNG and by the owner).

## Phase 10: GTK application, module `sheet-view` (approved 2026-11-15, SPEC.md "Module `sheet-view`")

- [x] **Task 49: Verovio, the Leipzig font, credits** (S): done 2026-11-15. `verovio==6.4.1` pinned exactly (another version is "ask first"); `[tool.uv] default-groups = ["dev", "app"]`. Font from Verovio's tag, licence from `rism-digital/leipzig` (commit in `packaging/fonts/README.md`). GTK has no OFL licence type, so the About dialog's Leipzig section is `CUSTOM` with the licence's name.
  - Acceptance:
    - Verovio 6.4.1 in a uv dependency group `app`, synced by default and by `scripts/gtk.sh`; a test fails if `src/stickler` imports `verovio`.
    - `packaging/fonts/Leipzig.ttf` from Verovio's tag `version-6.4.1` with `OFL.txt`; `scripts/gtk.sh` copies it into `.venv-gtk/share/fonts` and sets `FONTCONFIG_FILE` to a config adding that folder.
    - The About dialog names Verovio (LGPL-3.0) and Leipzig (SIL OFL).
  - Verify: `scripts/check.sh task`; `FONTCONFIG_FILE=… fc-list | grep Leipzig` inside `scripts/gtk.sh`'s environment
  - Dependencies: none · Files: `pyproject.toml`, `uv.lock`, `packaging/fonts/*`, `scripts/gtk.sh`, `src/stickler_gtk/ui/menu.py`, tests

- [x] **Task 50: Engraving with Verovio** (M): done 2026-11-15. Scale 50 % at zoom 1 (a staff about 36 px high); one long page per song (Verovio's largest page height); measures matched by id between Verovio's SVG and its MEI (`n` = written bar). Eye of the Tiger: 43 rectangles at 1000 and 360 px in 0.06 s, the 8 bars with dotted notes as tall as all others (72 px with padding). Verovio's layout warnings are silenced (errors stay); at 360 px it warns of tightly packed bars, for the owner's look at Checkpoint J.
  - Acceptance:
    - `logic/engraving.py`: MusicXML → SVG pages for a page width and zoom; for each written bar its page and rectangle, taken from the measure's staff lines.
    - Tests on MusicXML from `notation.engrave` (repeats, pickup, multi-measure rest): one rectangle per written bar, inside its page, left to right within a system.
  - Verify: `uv run pytest -q tests/gtk/test_engraving.py`; Eye of the Tiger: 43 measures with rectangles, the 8 bars with dotted notes as tall as their staff
  - Dependencies: 49 · Files: `src/stickler_gtk/logic/engraving.py`, tests

- [x] **Task 51: From song time to the marked bar** (S): done 2026-11-15. A written bar without a rectangle of its own (inside a multi-measure rest) is shown by the nearest engraved bar before it. Eye of the Tiger: all 110 song bars mark the bar map's written bar and every one has a rectangle; song bar 3 marks written bar 1.
  - Acceptance:
    - `logic/marker.py`: seconds → song bar (`Notation.bars`) → written bar → measure; a point on a page → the measure under it.
  - Verify: tests; Eye of the Tiger: every song bar's start time marks the bar map's written bar (110), song bar 3 marks written bar 1
  - Dependencies: 50 · Files: `src/stickler_gtk/logic/marker.py`, tests

- [x] **Task 52: The page in the window** (M): done 2026-11-15. Eye of the Tiger: the page is drawn 0.2 s after the result, at 1000 and 360 px (one bar per line there). Found on the way: under GTK's German locale Verovio wrote "scale(0,72, 0,72)" and librsvg dropped every notehead, rest and clef; Verovio now runs with `LC_NUMERIC=C` (`engraving.c_numbers`, tested where a comma locale exists). Zoom steps are `logic/zoom.py` (0.5–3×, ×1.25 per step). In a screenshot taken right after switching to dark the header looked empty; to be checked by the owner at Checkpoint J.
  - Acceptance:
    - The result page shows the pages under one another (librsvg), as wide as the window; re-engraved after resizing pauses; Ctrl+plus/minus, Ctrl+scroll, Ctrl+0; dark style inverts the page.
  - Verify: widget tests (page appears after a fake analysis, zoom changes the layout); by hand: Eye of the Tiger within 1 s of the result, at 360 px and 1000 px
  - Dependencies: 50 · Files: `src/stickler_gtk/ui/sheet.py`, `src/stickler_gtk/ui/window.py`, `po/*`, tests

- [x] **Task 53: Marking bars** (S): done 2026-11-15. The sheet keeps the marked written bar and finds its rectangle again after every new layout (zoom, width); a time scrolls its bar a third down from the top when it is out of view. Eye of the Tiger: each of the 43 bars is marked by a click on it; the marker is blue in light and dark (rendered and looked at).
  - Acceptance:
    - A click marks the bar under it; `Window.show_position(seconds)` marks the bar sounding then and scrolls it into view; the marker is blue in both styles.
  - Verify: widget tests (click, position); by hand: click through Eye of the Tiger
  - Dependencies: 51, 52 · Files: `src/stickler_gtk/ui/sheet.py`, tests

- [x] **Task 54: PDF export and "Open With…"** (S): done 2026-11-15. A4 in Verovio units (2100 × 2970: a 7.2 mm staff), Verovio's header for title on the first page; Eye of the Tiger fits one page, PDF written in 0.18 s. Found on the way: Verovio dropped the tempo mark of Eye of the Tiger, because it followed the attributes of a bar starting a multi-measure rest; `notation` now writes the tempo direction before the attributes (allowed by MusicXML; MuseScore's PDF of the song checked unchanged), and the app's PDF shows "♩=109" drawn with Leipzig. Verovio does not print the artist (composer); MuseScore does. The design canvas's "Open in MuseScore" became "Open With…".
  - Acceptance:
    - Export menu: "Sheet Music (PDF)…" writes Verovio's A4 pages with librsvg into a cairo PDF; "Open With…" opens the system's app chooser for the MusicXML.
  - Verify: a test finds one PDF page per Verovio page for a short song; by hand the tempo mark reads "♩ = 109" in the PDF of Eye of the Tiger
  - Dependencies: 49, 50 · Files: `src/stickler_gtk/ui/pdf.py`, `src/stickler_gtk/ui/window.py`, `po/*`, tests

### Checkpoint J
- [x] All 7 success criteria of SPEC.md `sheet-view` met; the owner looks at the sheet music at small widths and in dark style (2026-11-15: readable when narrow, smooth zoom, tempo mark right; Verovio's header, footer and page-height options accepted)
  - Owner, 2026-11-15: pinch zoom was not smooth (nothing moved until the new layout). Each page now keeps its drawn picture; a gesture or Ctrl+scroll scales it at once, Verovio lays out sharply once the input pauses.
  - Owner, 2026-11-15: a setting for the note size; chosen: a "−  100 %  +" row in the main menu (design screen 9 updated, SPEC.md design decisions), remembered in settings.json for every song; zoom works on every page now, not only on a result.
  - Owner, 2026-11-15: "♩=109" lacked its spaces: Verovio writes no-break spaces, librsvg drops them at the edge of a text part; the leading one became a shift (dx, 0.25 em, the width Verovio reserves), the trailing one is preserved. Pinch zoom on the touchpad did not work: `Gtk.GestureZoom` added, the layout follows when the fingers pause.
  - Owner, 2026-11-15: the window could not be made smaller while the sheet was shown; the pages' width was the window's minimum (`hscrollbar_policy` NEVER). Fixed with EXTERNAL; a test measures it.

### Next: the app icon (owner, 2026-11-15: right after `sheet-view`)
- [x] Done 2026-11-15: draft B of four (page and drumsticks), `packaging/icons/ng.tshia.Stickler.svg` and `-symbolic.svg`, installed by `scripts/gtk.sh`, used for the window and the About dialog. Design round on the canvas with the owner: a few drafts in the GNOME style (Daudix's icons as the reference), then the chosen one as SVG plus its symbolic variant, named `ng.tshia.Stickler`; see "App icon in GNOME style" under Later.

## Phase 11: GTK application, module `playback` (approved 2026-11-15, SPEC.md "Module `playback`")

- [x] **Task 55: Playback logic** (S): done 2026-11-15. A bar click goes to the bar's first pass that starts after the current song bar's start, else its first pass (so inside its only pass: its start). The arrow keys step song bars, kept inside the song.
  - Acceptance:
    - `logic/playback.py`: the volume of song and clicks for Song / Hits / Both; the time a click on a written bar jumps to (its next pass from now, else its first); the previous and next song bar for the arrow keys; the texts "0:06" and "Bar 2 of 110".
    - `settings`: the two volumes, remembered, bad values fall back; `paths`: where a song's clicks WAV goes.
  - Verify: `uv run pytest -q tests/gtk/test_playback.py tests/gtk/test_settings.py`
  - Dependencies: none · Files: `src/stickler_gtk/logic/{playback,settings,paths}.py`, tests

- [x] **Task 56: The player** (M): done 2026-11-15. Each branch converts to one format (F32, 48 kHz, stereo) before the `audiomixer`; seeks are FLUSH | ACCURATE and wait for the pipeline to settle; a song without its clicks plays alone. Tested with a real pipeline on `fakesink` in real time.
  - Acceptance:
    - `ui/player.py`: one pipeline mixing the song and the clicks, with `load`, `play`, `pause`, `seek`, `position`, `duration`, `set_volumes`, `stop`; an error on the bus reaches a callback.
  - Verify: a widget test with `fakesink` and a generated song: plays, the position advances, a seek lands within 50 ms, `stop` leaves the pipeline NULL
  - Dependencies: 55 · Files: `src/stickler_gtk/ui/player.py`, tests

- [x] **Task 57: The playback bar** (M): done 2026-11-15. The analysis job writes the clicks after the notation (left out if that fails); the pipeline loads on the first play, the length comes from `SongInfo`; the bar is stopped whenever the result page is left and on close.
  - Acceptance:
    - The clicks WAV is made with `api.render_hits` when a result appears; the result page has the playback bar (design screen 6): play/pause, time, position slider (seek), length, "Bar n of N".
  - Verify: widget tests with a fake player; by hand: Eye of the Tiger plays, pauses, seeks
  - Dependencies: 56 · Files: `src/stickler_gtk/ui/{playbar,window}.py`, `src/stickler_gtk/logic/analysis.py`, `po/*`, tests

- [x] **Task 58: What to hear, volumes, the marker, bar clicks** (M): done 2026-11-15. Song / Hits / Both is an `Adw.ToggleGroup`, the volume popover has one slider each (remembered); a click on a bar seeks to its next pass. The two-row narrow layout (Task 59) came along: the one-row bar no longer fit 360 px. The narrow breakpoint calls `PlayBar.set_narrow`, which regroups the widgets as on design screen 10.
  - Acceptance:
    - Song / Hits / Both and the volume popover (two sliders, remembered); while playing the marker follows (50 ms timer) and scrolls; a click on a bar seeks to its next pass.
  - Verify: widget tests (fake player: volumes per mode, seek target of a click in repeats, the marker after a position); by hand: clicks in time with the drums (owner)
  - Dependencies: 55, 57 · Files: `src/stickler_gtk/ui/{playbar,window,sheet}.py`, `po/*`, tests

- [x] **Task 59: Keyboard, narrow window, stopping** (S): done 2026-11-15. Space, Left, Right and Home are app accelerators (`win.play`, `win.previous-bar`, `win.next-bar`, `win.to-start`) and in the shortcuts dialog; the two-row bar came with Task 58; playback stops when the result page is left (another song, an export) and on close, which quitting goes through.
  - Acceptance:
    - Space, Left, Right, Home (in the shortcuts dialog); the bar in two rows below the narrow breakpoint; playback stops on a new song, close and quit; German complete.
  - Verify: widget tests (keys through actions, stop on close); by hand at 400 px
  - Dependencies: 58 · Files: `src/stickler_gtk/ui/*`, `po/*`, tests

### Checkpoint K
- [x] All 8 success criteria of SPEC.md `playback` met; the owner listens to Eye of the Tiger with the clicks. Done 2026-11-15: the clicks follow the marks, switching Song / Hits / Both is smooth; the first clicks were too quiet, the fuller ones are "much better to hear" (owner).

## Phase 12: GTK application, module `corrections` (approved 2026-11-15, SPEC.md "Module `corrections`")

- [x] **Task 60: Corrections logic and store** (S): done 2026-11-15. `api.Notation` gained `first_downbeat` (the detected or corrected first one, 1-based on the corrected beats), so the sidebar can show it. A new tempo resets the first one, which is counted on the corrected beats.
  - Acceptance:
    - `logic/corrections.py`: each control's change with its range (beats 1–12, the first "one" within the bar, kept there when the beats shrink); "anything corrected?"; the texts "Beat n".
    - The store: per song by absolute path, round trip, bad entries dropped one by one, a missing file is empty, atomic save.
  - Verify: `uv run pytest -q tests/gtk/test_corrections.py`
  - Dependencies: none · Files: `src/stickler_gtk/logic/corrections.py`, tests

- [x] **Task 61: Jobs and session for a correction** (S): done 2026-11-15. `Analysing` carries the song's stored corrections into its `Result`; a change is a `Pending` (job number and values) on the `Result`, whose `wanted` the controls show. No detected meter is kept: `Notation` carries the current meter and first one (Task 60).
  - Acceptance:
    - `analyse` passes corrections to `notate`; `Result` holds the corrections and the detected meter; `correcting` and `corrected` show only the newest correction's result; a failed correction keeps the result.
  - Verify: `uv run pytest -q tests/gtk/test_session.py tests/gtk/test_analysis_errors.py`
  - Dependencies: 60 · Files: `src/stickler_gtk/logic/{analysis,session}.py`, tests

- [x] **Task 62: The sidebar** (M): done 2026-11-15. `ui/corrections.py` (`CorrectionsPanel`) shows `Result.wanted` and the engraved meter and first one; an `Adw.OverlaySplitView` at the end with a header toggle bound to it and F9.
  - Acceptance:
    - `ui/corrections.py` with the controls of design screen 7, showing a result's values; an `Adw.OverlaySplitView` with the sidebar at the end, a header toggle and F9, closed at first.
  - Verify: widget tests (values shown, F9 toggles); by hand at 1000 px
  - Dependencies: 60 · Files: `src/stickler_gtk/ui/{corrections,window,application,menu}.py`, `po/*`, tests

- [x] **Task 63: Applying, remembering, Back to Detected** (M): done 2026-11-15. The window tells a correction from a new analysis by the `SongInfo` it keeps, so playback goes on with the new bar map (`PlayBar.set_bars`); it compares notations, not MusicXML paths, because a correction rewrites the same file. Found on the way: `session.on_step` rebuilt `Analysing` and dropped its corrections; it now keeps every field.
  - Acceptance:
    - A change re-notates after 250 ms in the worker and shows the new sheet, title, bar map; exports use it; the song's corrections are stored and applied when it is opened again; "Back to Detected" clears them and is insensitive while nothing is corrected.
  - Verify: widget tests with the fake analysis (a change reaches `notate`, the title follows, reopening applies the stored ones); by hand: Eye of the Tiger at half tempo, the longest own song timed
  - Dependencies: 61, 62 · Files: `src/stickler_gtk/ui/{window,corrections}.py`, tests

- [x] **Task 64: Bottom sheet, shortcuts, German** (S): done 2026-11-15. One `CorrectionsPanel` moves between the sidebar and an `Adw.BottomSheet` at the narrow breakpoint, staying open or closed; the header toggle and F9 open whichever is in use. Timed on the longest own song (Zombie, 308 s): a correction notates in 0.18–0.22 s and engraves in 0.11–0.16 s.
  - Acceptance:
    - Below the narrow breakpoint the controls sit in an `Adw.BottomSheet` (design screen 11); F9 in the shortcuts dialog; every page still fits 360 px; German complete.
  - Verify: widget tests (narrow window shows the bottom sheet, the width test); by hand at 400 px
  - Dependencies: 63 · Files: `src/stickler_gtk/ui/*`, `po/*`, tests

### Checkpoint L
- [x] All 8 success criteria of SPEC.md `corrections` met; the owner corrects Eye of the Tiger. Done 2026-11-15 (owner: "Prima"); the title cut short in the narrow header was accepted as is.

## Phase 13: GTK application, module `setup-assistant` (approved 2026-11-15, SPEC.md "Module `setup-assistant`")

- [x] **Task 65: ADTOF from a GitHub archive** (S): done 2026-11-15. The lock changed only the source (plus the archive's SHA-256); 423 cache entries rekeyed. Eye of the Tiger transcribed fresh: the same 1375 hits, the MIDI file byte-identical to the cached one.
  - Acceptance:
    - `adtof-pytorch` comes from the archive of commit 85c192e…; `uv.lock` updated with the same package versions; cached ADTOF results rekeyed (`cache-digests` before, `cache-migrate --rekey-from` after).
  - Verify: the environment rebuilt; one own song transcribed: the same hits as the cached result
  - Dependencies: none · Files: `adapters/transcribers/adtof/{pyproject.toml,uv.lock}`

- [x] **Task 66: A mirror for Beat This!'s checkpoint** (S): done 2026-11-15. The download lives in a torch-free `download.py` (tested against a local server); `setup.py` uses it and then loads the checkpoint as `run.py` does; 115 cache entries rekeyed. In an empty copy with JKU down and the release not yet published: "JKU Linz (cloud.cp.jku.at): 500; Stickler's copy (github.com): 404", nothing left behind. The release itself waits for Checkpoint M.
  - Acceptance:
    - `setup.py` downloads from JKU, else from the release URL; the SHA-256 is checked; a mismatch or both failing raises an error naming both servers; cached results rekeyed.
  - Verify: tests against a local HTTP server (JKU answering; failing with the copy answering; wrong checksum; both failing)
  - Dependencies: none · Files: `adapters/beats/beat_this/{setup.py,common.py}`, tests

- [x] **Task 67: Setup logic** (S): done 2026-11-15. Sizes per step from `docs/requirements.md`; bytes are uv's cache plus the adapter's folder, links not counted.
  - Acceptance:
    - `logic/setup.py`: at start consent, download or nothing; the step rows of what is missing; a step's bytes against its size, capped at 99 %; the server a failed step names. `settings` remembers the consent; `STICKLER_ADAPTERS` sets the adapters folder.
  - Verify: `uv run pytest -q tests/gtk/test_setup.py tests/gtk/test_settings.py`
  - Dependencies: none · Files: `src/stickler_gtk/logic/{setup,settings,paths}.py`, tests

- [x] **Task 68: Consent and download pages** (M): done 2026-11-15. `Consent` and `SettingUp` are session states; the download uses the analysing page's step list. Progress is the free disk space a step used, sampled every 0.5 s (walking uv's cache would be too slow), capped at 99 %. The consent page lists only the missing models.
  - Acceptance:
    - Design screens 1 and 2; Download runs `api.setup_adapters` in the worker with steps and bytes; Cancel stops it; done → the empty window; an agreed but unfinished setup goes on at the next start.
  - Verify: widget tests with a fake `setup_adapters`
  - Dependencies: 67 · Files: `src/stickler_gtk/ui/{setup,window}.py`, `po/*`, tests

- [x] **Task 69: Errors, Not Now, the old page gone** (M): done 2026-11-15. `SetupFailed` names the step's server and keeps the step list (Ready / Not reached); Try Again restarts the setup, whose finished steps are quick. A `SetupMissing` from an analysis or an export leads to the consent page, which keeps the song and opens it once the models are there. The fresh setup by hand waits for Checkpoint M.
  - Acceptance:
    - Design screen 3 (server named, details, Try Again, Later); Not Now → the empty window, a song asks again; `SetupMissing` leads to consent instead of the command page; German complete; every page fits 360 px.
  - Verify: widget tests; by hand: a fresh setup with `STICKLER_ADAPTERS` pointing at a copy
  - Dependencies: 68 · Files: `src/stickler_gtk/ui/*`, `src/stickler_gtk/logic/session.py`, `po/*`, tests

- [x] **Task 70: Spanish as a third language** (S): done 2026-11-15. 134 strings; `po/LINGUAS` drives `scripts/i18n.sh` and the tests (complete, placeholders kept, width). The sheet's instrument name "Drumset" comes from the MusicXML and stays English in every language. (owner, 2026-11-15: the owner's drum teacher is from Peru)
  - Acceptance:
    - `po/es.po` complete, neutral Latin American Spanish, informal "tú" (as German "du"); built and installed like German; the tests check every language's catalogue, not only German; the width test also measures Spanish; SPEC.md records the third language.
  - Verify: `uv run pytest -q tests/gtk/test_translations.py`; `scripts/gtk.sh test`; by hand: `LANGUAGE=es scripts/gtk.sh`
  - Dependencies: 69 · Files: `po/es.po`, `po/LINGUAS` if any, `scripts/{i18n,gtk}.sh`, tests, `SPEC.md`

### Checkpoint M
- [x] All 6 success criteria of SPEC.md `setup-assistant` met; the owner publishes the mirror release (or gives the go) and runs a fresh setup. Done 2026-11-15: the owner gave the go, the release `beat-this-final0` is published (not "latest"); with JKU down, `download.fetch` took the copy (81 MB, SHA-256 matching). The owner's fresh setup into a copy of the adapters worked. German wording fixed after the owner's remark ("Sein Modell" → "Dieses"/"Das Modell"). Resuming and Not Now are covered by widget tests.

## Phase 14: Packaging (approved 2026-11-15, SPEC.md "Module `packaging`")

- [x] **Task 71: The app imports no benchmark code** (S): done 2026-11-15. The only use was `mir_eval.util.match_events` (align, errors, evaluate); `stickler.events.match_events` loads it on the first call. The GTK window now loads neither mir_eval, scipy nor typer.
  - Acceptance: importing `stickler.api` and the GTK app loads neither `mir_eval` nor `scipy`; the benchmark still works (they load when it runs).
  - Verify: a test that imports the app in a fresh interpreter and checks `sys.modules`; `scripts/check.sh task`
  - Dependencies: none · Files: `src/stickler/api.py` (lazy imports), tests

- [x] **Task 72: Python 3.14 for the app's models** (M): done 2026-11-15. ADTOF and Beat This! on Eye of the Tiger: identical (1375 hits, byte-identical MIDI; 441 beats). Demucs needed numpy 2.5.4 (the old lock kept 1.26.4, which has no 3.14 wheel); its stem differs from 3.12 by 24.0 dB SNR, but two runs on 3.14 differ by 26.3 dB: its random shift (`shifts 1`), not the version. 653 cache entries rekeyed. Each of the three got a `.python-version` (3.14), since the repository's 3.12 would otherwise apply. The ROCm environment of Demucs (developer tool) still runs 3.12 until `stickler setup --device rocm` rebuilds it. (owner, 2026-11-15: ADTOF, Beat This!, Demucs; the benchmark-only models stay on 3.12)
  - Acceptance: each of the three adapters' `requires-python` is 3.14, its lock resolved with wheels for every package, its environment rebuilt; one own song compared with the 3.12 result; identical results rekeyed, differences noted and left to be recomputed.
  - Verify: per adapter, the comparison; `stickler doctor`; `scripts/check.sh task`
  - Dependencies: none · Files: `adapters/*/*/{pyproject.toml,uv.lock}`, `.python-version` if needed, README notes

- [x] **Task 73: Packaged paths** (S): done 2026-11-15. A packaged app is recognised by `FLATPAK_ID` (ours) or `APPIMAGE`; its launcher sets `STICKLER_ADAPTER_SOURCES`, whose files the start copies into the models folder where they differ. Analysis, drum export and both readiness checks get the folders. Which Python uv uses is set by the packages' environment (Tasks 75, 76): `UV_PYTHON` itself is dropped for adapters by the harness.
  - Acceptance: in a packaged app models live in `$XDG_DATA_HOME/stickler/adapters` (sources copied from the app, refreshed on a new version, environments and weights kept) and results in `$XDG_CACHE_HOME/stickler`; `uv` uses the runtime's Python in the Flatpak and its own in the AppImage; the checkout keeps today's folders.
  - Verify: logic tests for each case
  - Dependencies: 72 · Files: `src/stickler_gtk/logic/{paths,analysis,setup}.py`, `src/stickler_gtk/ui/window.py`, tests

- [x] **Task 74: AppStream MetaInfo** (S): done 2026-11-15. Screenshots of "Fluffing a Duck" (Kevin MacLeod, CC BY 4.0; the owner's choice after a search for a free, funny song), linked at the commit that added them; credited in the captions and `docs/screenshots/README.md`. The desktop file no longer claims audio/mp4.
  - Acceptance: `packaging/ng.tshia.Stickler.metainfo.xml` with description, screenshots (from the app), releases, OARS, licences, developer; `appstreamcli validate` in CI.
  - Verify: `appstreamcli validate --pedantic`
  - Dependencies: none · Files: `packaging/*`, `docs/screenshots/*`, `.github/workflows/check.yml`

- [x] **Task 75: The Flatpak** (M): done 2026-11-15. Built locally with org.flatpak.Builder; the owner set up the models in the sandbox, analysed, played and exported a PDF. Found on the way: `classes.yaml` lay next to the repository, not in the package (an installed app has no repository: the first analysis failed); the step list rebuilt every row on each report, so the spinner stuttered; the app finds its files under the prefix it is installed in (/app). Python packages come from uv.lock through `scripts/flatpak_deps.py` (no build backend needed: Stickler is copied in).
  - Acceptance: the manifest builds offline from pinned sources (Python wheels from flatpak-pip-generator, uv with SHA-256); installed locally, the app starts, the setup assistant sets up the models inside the sandbox, a song is analysed and played.
  - Verify: `flatpak-builder --install`; by hand with Eye of the Tiger
  - Dependencies: 71, 73, 74 · Files: `packaging/flatpak/*`

- [x] **Task 76: The AppImage** (M): done 2026-11-15. quick-sharun pinned to a commit, in the Anylinux Arch image with its debloated packages (Arch's mesa pulls in LLVM); about 133 MB. The owner analysed, played and exported in it. Found on the way: quick-sharun leaves out the app's own translations (now copied and checked); GTK_CLASS_FIX preloads a library that prints into ffprobe's output (dropped); Arch's ffprobe 9.0 writes localized numbers, so every ffmpeg/ffprobe call now runs with LC_ALL=C; a headless test in a private D-Bus session unmounted the owner's document portal (never again).
  - Acceptance: `scripts/appimage.sh` builds `Stickler-x86_64.AppImage` with quick-sharun (pinned) in an Arch container; it starts, sets up, analyses and plays.
  - Verify: the script in a local container; `quick-sharun --test`; by hand
  - Dependencies: 71, 73, 74 · Files: `scripts/appimage.sh`, `packaging/appimage/*`

- [x] **Task 77: Release workflow** (M): done 2026-11-15. A manual run built both (Flatpak 30 MB, AppImage 127 MB); attaching them to a release is confirmed with release 5. The Flatpak is built with Ubuntu's flatpak-builder (Flathub's action has had no commit since April 2025), whose git source needed `branch: HEAD`.
  - Acceptance: `.github/workflows/release.yml` builds both on a release tag and attaches them, and on a manual run uploads them as artifacts; the release notes template says how to install each.
  - Verify: a manual run
  - Dependencies: 75, 76 · Files: `.github/workflows/release.yml`, `docs/` release notes

- [x] **Before every release: the AI's tokens and cost** (owner, 2026-11-15; done for release 5, and from now on as a release step, ADR 0006): run `scripts/ai_usage.py` and update the table in README `> ORIGIN`.
- [x] **Before release 5: every document checked** (owner, 2026-11-15; a fresh-context subagent compared the documents with the code, about 20 fixes; a second one reviewed the packaging code, its fixes went in): README, CONTRIBUTING, CITATION.cff, docs/cli.md, docs/report.md, SPEC.md, CONSTRAINTS.md, the AppStream MetaInfo and the release notes agree with the app, the GPL (ADR 0007), Python 3.14 for the app's models and the packages.

### Checkpoint N
- [x] All 6 success criteria of SPEC.md `packaging` met; the owner installs the Flatpak and the AppImage from a CI run. Done 2026-11-15: the owner tested both (built locally, the same scripts CI runs); CI built both twice; attaching them is confirmed with release 5.

## Phase 15: `polish` (approved 2026-11-15, SPEC.md "Module `polish`")

- [x] **Task 78: The artist in the PDF** (S): done 2026-11-15. Credits for title (centred) and artist (right) after `<identification>`; Verovio engraves both once (the title no longer comes from its auto header alone). Checked on Fluffing a Duck's PDF with the app's font setup.
  - Acceptance: the MusicXML holds `<credit>` elements for title and artist; the first A4 page engraved by Verovio shows the artist; no artist, no artist credit.
  - Verify: `uv run pytest -q tests/test_notation.py`; a GTK test engraves an A4 page
  - Dependencies: none · Files: `src/stickler/notation.py`, tests

- [x] **Task 79: Click volume per song** (S): done 2026-11-15. The target (4.0 dB over the song at its hits) is what Eye of the Tiger had: its gain is now 1.01; Fluffing a Duck's clicks come out 7.1 dB quieter. The gain is found by bisection because the soft limit is not linear; render_hits takes about a second. Fearless is the owner's to hear (not in data/own).
  - Acceptance: `render_hits` scales the clicks by the song's loudness at the hits, so a quiet and a loud copy of a song get the same click-to-song ratio; Eye of the Tiger keeps about today's level; silent songs keep the fixed level; no clipping.
  - Verify: `uv run pytest -q tests/test_api.py tests/test_audio.py`; by ear: Fearless and Eye of the Tiger (owner)
  - Dependencies: none · Files: `src/stickler/{audio,api}.py`, tests

- [x] **Task 80: What a removal deletes** (S): done 2026-11-15. Nothing from the checkout; by default `adapters/` and `python/` in Stickler's data folder and its whole cache folder, in the Flatpak also uv's cache inside the sandbox folder (only when the cache lies under `.var/app/ng.tshia.Stickler/`); everything means Stickler's three folders.
  - Acceptance: `logic/removal.py`: the folders for the Flatpak and the AppImage, with and without "everything"; nothing from the checkout, nothing outside the app's folders; their size; the deletion itself.
  - Verify: `uv run pytest -q tests/gtk/test_removal.py`
  - Dependencies: none · Files: `src/stickler_gtk/logic/removal.py`, tests

- [x] **Task 81: "Remove Downloaded Models…"** (M): done 2026-11-15. The entry only in the installed app, disabled while a job, a download or a removal runs; the alert shows the size for either choice and switches it with the check box; afterwards the consent is reset (everything: the recent list too). msgmerge had pre-filled the new texts with wrong fuzzy translations; all seven are translated by hand in German and Spanish.
  - Acceptance: the main menu entry only when packaged, disabled while a job runs; an alert with the size and the check box; the deletion in the worker; afterwards the empty window and the consent asked again; German and Spanish.
  - Verify: widget tests (packaged and not, the alert's choices); by hand in the Flatpak or AppImage (owner)
  - Dependencies: 80 · Files: `src/stickler_gtk/ui/{menu,window,application}.py`, `po/*`, tests

### Checkpoint O
- [x] All 4 success criteria of SPEC.md `polish` met (the owner listens, prints and removes; 2026-11-15). Found on the way and fixed: removal took the shipped model sources too (b5f5b78), libsndfile failed on some MP3s (e904c8e), the model download overshot its size (c07afbc)

## Phase 16: Release 7, new candidates (approved 2026-11-16, SPEC.md "Release 7")

Task 12 (DrumSep + onsets, Phase 3) is part of this phase and comes first.

- [ ] **Task 82: Transcriber `muscriptor_l`** (S)
  - Acceptance: copy of `muscriptor_m` with `SIZE = "large"` (own name, lock, README with source, version, licence CC BY-NC 4.0, gated, 5.47 GB); in `config/benchmark.yaml` and `config/own.yaml` like `muscriptor_m` (Demucs stem, skip on the mix); existing cache entries untouched.
  - Verify: `uv run pytest -m adapters -k muscriptor_l` (on RunPod or the laptop after `stickler setup --adapter muscriptor_l`); laptop time for one 4-minute song recorded
  - Dependencies: none · Files: `adapters/transcribers/muscriptor_l/*`, `config/*.yaml`, `SPEC.md` candidates table

- [ ] **Task 83: Transcriber `sad` (Separate-and-Detect)** (M, risk)
  - Acceptance: spike first: the pinned commit of ddman1101/Separate-and-detect turns a 10 s drum stem into five stems and onsets, on CPU and on a RunPod GPU; then an adapter that gives GM MIDI from a Demucs stem, README with source, commit and licence (MIT), and the owner's exception noted. If the spike fails after two attempts: recorded in SPEC.md and the report as tried and left out (owner agrees).
  - Verify: `uv run pytest -m adapters -k sad`; laptop time for one 4-minute song recorded
  - Dependencies: none · Files: `adapters/transcribers/sad/*`, `config/*.yaml`

- [ ] **Task 84: Benchmark runs** (M)
  - Prepared 2026-11-16: `stickler tune --transcriber drumsep_onset` tunes DrumSep's thresholds on its saved envelopes; the adapter picks peaks exactly as `stickler.peaks` (copy, kept identical by a test), so a tuned threshold reproduces its MIDI. Fusions take `transcriber:` (default adtof).
  - Noticed 2026-11-16: an adapter's cache key covered only `run.py`, `setup.py` and `pyproject.toml`, not helper modules; fixed in Task 87.
  - Runbook (2026-11-16; runs from the laptop, a cloud session cannot reach a pod over SSH). No config of its own: `config/benchmark.yaml`, `config/enst.yaml` and `config/own.yaml` already hold the candidates (Demucs stem; oracle on MDB and ENST); everything cached is skipped.
    0. Before pulling: `cp -r results results-before-87` (results/ is not in git).
    1. On the laptop, after pulling: `uv run stickler eval --config config/benchmark.yaml`, the same for `config/enst.yaml` and `config/own.yaml`. Eval computes nothing but looks every result up, which renames it to its Task 87 key; without this the pod would rename the uploaded copies and the laptop would keep both. Not `cache-migrate`: it sets aside entries of inputs outside the datasets and reference songs (e.g. `stickler notate` runs).
    2. Task 87's verify: `diff -r results-before-87 results` shows only the new candidates' rows (as errors, "not computed"); every old pipeline's numbers are unchanged.
    3. A RunPod pod (RTX 4090, Secure Cloud in the EU, as for the own songs before); Hugging Face login on the laptop (MuScriptor large is gated; the token goes to the pod over SSH input).
    4. `uv run stickler remote root@<ip> --port <port> --config config/benchmark.yaml`, then the same with `config/enst.yaml --wipe` and `config/own.yaml --pod-id <id> --wipe` (licensed data and the owner's songs are deleted from the pod; the last run stops it). Check the first run's times before starting the others: Separate-and-Detect's speed on the GPU is not measured yet.
    5. Thresholds of `drumsep_onset` and `sad` on MDB and ENST, without the own songs: `uv run stickler tune --transcriber drumsep_onset --inputs demucs --config config/benchmark.yaml --config config/enst.yaml --name drumsep_tuned` (likewise `sad`); the printed `fusions` entry goes into all three configs and is scored from the cached activations (nothing recomputed).
    6. Laptop time budget (SPEC Release 7, method 5): one 4-minute own song with `demucs+muscriptor_l` and `demucs+sad` on the laptop CPU (`meta.json` seconds); above 20 minutes, measure on the pod's GPU (the reference for a Quality that requires a GPU).
    7. `uv run stickler eval` for the three configs and `uv run stickler report`.
  - Risk: `stickler setup --device cuda` builds `.venv-cuda` from each lock's torch version; sad's lock pairs torch 2.15 with torchaudio 2.11.1 (fine on CPU, not checked on CUDA). If its setup fails on the pod, the other candidates still run (a failed adapter is logged, not blocking).
  - Acceptance: `demucs+drumsep_onset`, `demucs+muscriptor_l`, `demucs+sad` (and a combination like Quality's for a candidate that is strong on some classes) on MDB, ENST and the 25 own songs; every combination gives MIDI or a logged error (SPEC Release 7, criterion 1); `metrics.csv` and `report.html` updated; RunPod pods stopped.
  - Verify: `uv run stickler eval` for the three configs; the time per 4-minute song on the laptop for each candidate in the report
  - Dependencies: 12, 82, 83 · Files: `config/*.yaml`, results (not committed)

- [ ] **Task 85: Listening round, only if needed** (S)
  - Acceptance: for each candidate within 0.01 of Fast's or Quality's measured macro-F1 on the own songs (or above it): about 40 spots from its own errors, drawn once with a fixed seed, judged blind with `stickler listen`; its corrected score as in release 3. Skipped, with the numbers stated, if no candidate comes close.
  - Verify: `uv run pytest -q tests/test_errors.py tests/test_api.py -k "sample or correct"`; `results/own/corrected.csv`
  - Dependencies: 84 · Files: `src/stickler/{errors,api}.py` if the sample needs a candidate filter, tests

- [ ] **Task 86: Decision, report and release 7** (S)
  - Acceptance: ADR 0008 with the decision per mode (unchanged or replaced; owner); `docs/report.md` section on the new candidates; README candidates and results tables; release steps of ADR 0006 incl. the hand-tried feature list.
  - Verify: SPEC Release 7 success criteria; `scripts/check.sh task`
  - Dependencies: 84, 85 · Files: `docs/adr/0008-*.md`, `docs/report.md`, `README.md`, version files

- [x] **Task 87: Cache keys cover everything that defines an adapter** (M) (owner, 2026-11-16): done 2026-11-16. The digest covers every Python module and `pyproject.toml` of the adapter and `adapters/_common` (before: only `run.py`, `setup.py`, `pyproject.toml`, so a changed helper such as `onsets.py` kept old results valid). Pairs of equivalent digests are listed in `src/stickler/digests.yaml`; `cache_dir_for` renames an entry under an earlier digest to the current key on first use, but only along a chain that ends at the current digest, in the benchmark and the app, so neither the laptop nor installed apps compute anything again. Listed: every adapter unchanged since release 6; not drumsep_onset (its helper changed under the same old digest). A fresh-context review found three problems in the first version, all fixed: a listed digest stayed valid after later real changes (now pairs and chains), `cache-migrate` set listed entries aside (it now knows the pairs, and refuses snapshots of the old definition), and the digest depended on the machine (a `.venv` in the path, stray files; now only imported modules, relative names). The key now also covers `uv.lock` and `.python-version`. Same digests on Python 3.12 and 3.14.
  - Verify: `uv run pytest -q tests/test_cache_keys.py tests/test_runner.py tests/test_cachemigration.py`; on the laptop, the first `stickler run` after the update finds every cached result (nothing computed)

### Checkpoint P
- [ ] All success criteria of SPEC.md "Release 7" met; the decision per mode by the owner; release 7

## Phase 6: Later (noted by the user, 2026-11-12)

- [x] **Later release: click volume follows the song** (done in module `polish`) (owner, 2026-11-15): songs differ in loudness; the clicks suit Eye of the Tiger but are too loud on Amaranthe's "Fearless". Measure the song's loudness where the hits are and set the clicks relative to it.
- [x] **Later release: "Remove Downloaded Models…" in the app** (done in module `polish`) (owner, 2026-11-15): a menu entry that deletes the models, their environments and the results after asking, so an AppImage user need not know the folders.
- [x] **Later release: the band's name in the PDF** (done in module `polish`) (owner, 2026-11-15): the engraved page shows the title but not the artist.
- [ ] **Screenshots in the README** (owner, 2026-11-16): a few telling screenshots of the app in the README; today it has none (only the `how-it-works.svg` diagram). Start from the three AppStream screenshots in `docs/screenshots/` (sheet, corrections, dark; "Fluffing a Duck", CC BY 4.0) and decide with the owner which screens show Stickler best.
  - 2026-11-16 (owner, after GymMane's README): an animated overview at the very top, the app icon under it, single screenshots further down; the ASCII banner goes (it suits a CLI-only project, noted in the owner's skill template). Done: the README's top (the sheet screenshot stands in for the overview until it is recorded), a section `> THE APP` with the three screenshots, `scripts/gtk.sh demo` with `scripts/demo.py` to record the overview. Open: record `docs/screenshots/overview.gif` on the laptop (`scripts/gtk.sh demo <Fluffing a Duck>`), check it, and point the README's top image at it.
- [x] **Lessons learned, once most of the project is done** (owner, 2026-11-15; first noted for after release 5): write down what building the app taught us (mistakes, detours, what worked), so a comparable project starts faster and more directly. Done 2026-11-16 as the portable skill `owner-led-projects` in [niklastshiang/claude-skills](https://github.com/niklastshiang/claude-skills) (MIT, owner): general working rules only, each with its reason from Stickler, built on addyosmani/agent-skills, plus a README template (to be improved by comparing with successful projects, owner). Its rules came from this file, the ADRs, SPEC.md and the git history; a fresh-context subagent reviewed it.

Not planned yet, just recorded. Before starting each one, extend SPEC.md and break it into tasks.

- [x] **Release 3 published on 2026-11-14** (tag v3, GitHub release): error analysis and honest numbers (Phase 7). Owner, 2026-11-14: Quality stays as a mode for now, although Fast is ahead after the correction.
- [x] **Release 2 published on 2026-11-13** (tag v2, GitHub release): readable sheet music (similar bars simplified, repeat signs). Release 3 (owner, 2026-11-13): the error analysis on the own songs (see Phase 5c).
- [x] **Release 1 published on 2026-11-13** (tag v1, GitHub release, repository public; private vulnerability reporting and Dependabot alerts on, pull requests and wiki off).
- [x] **Release plan (owner, 2026-11-13):** the repository goes public with release 1; the old music folder names in the git history may stay. Release 1 = the command line tool (`notate --mode fast|quality` once the 25-song results are in, docs in `docs/`); the GTK application is the next release after it, whatever its number is (ADR 0006: every release counts, fixes to the command line tool in between included; owner, 2026-11-13). With the application, add the GitHub topics `gtk4`, `libadwaita`, `flatpak` (18 of 20 are set since 2026-11-13). Owner, 2026-11-13: release 2 is another command line release; the application comes after it.
- [ ] **README picture of `stickler notate`** (owner, 2026-11-13): `docs/images/how-it-works.svg` is drawn (song → Fast/Quality → notation → MusicXML/PDF/drum track); in the README since 2026-11-13; `notate --mode fast|quality` exists (note removed); still update the accuracy line in its footer from the 25-song results.
- [ ] **Contributions (owner, 2026-11-13):** no outside pull requests (CONTRIBUTING.md, issue forms for bugs and model suggestions, no code of conduct). Pull requests are switched off in the repository settings (owner, 2026-11-13; GitHub setting since 2026-02). If issues become too many: restrict issue creation to collaborators (GitHub setting since 2026-06). SECURITY.md asks for private reports; owner enables private vulnerability reporting and Dependabot alerts (not security/version updates: they need pull requests, and model versions are pinned on purpose). Before every release: go through open Dependabot alerts.
- [x] **Dependabot alerts (2026-11-13):** torch 2.15 for Demucs (the lock was held at 2.2.2 by demucs's Intel-macOS pin; now resolved for Linux only), Beat This! and ADT_STR; outputs compared before/after on three MDB songs (Beat This! identical, ADT_STR 2 of 246 notes 9 ms apart, Demucs differs as much as two runs of the same version, because of its random shift) and the cache rekeyed (snapshot `data/archive/digests-before-torch-2.15.json`, needed again for results from pods that ran the old versions). YourMT3+ removed (transformers could not be updated); its results stay in the report. New smoke test: ADTOF on a real mix (Fast mode).
- [ ] **GitHub Pages site (owner, 2026-11-13: idea for later):** built automatically from `docs/` (report, CLI guide, requirements), so the source stays versioned with the code; no GitHub wiki (not versioned with the code, editable by others).
  - Build (owner, 2026-11-16): as small and lean as possible, made with a static site generator (which one is chosen when the site is specified, after checking candidates on the web), and no JavaScript where it can be avoided (light and dark through CSS `prefers-color-scheme`).
  - Style (owner, 2026-11-16): a landing page like GymMane's (https://inlitx.github.io/GymMane/), but with light and dark following the system. Look at that page closely before starting (the session's network did not reach it on 2026-11-16).
  - Domain: maybe `stickler.tshia.ng` (owner, 2026-11-16: not decided). It works next to the site on the VPS: a CNAME `stickler` → `niklastshiang.github.io` at the DNS of `tshia.ng`, the custom domain in the repo's Pages settings, the domain verified in the GitHub account (TXT `_github-pages-challenge-niklastshiang`), and `letsencrypt.org` allowed if `tshia.ng` has a CAA record.
- [ ] **Windows and macOS packages (owner, 2026-11-16: idea):** `.msi` and `.exe` for Windows, the fitting format for macOS (a `.dmg` with the `.app`; see the macOS note below). To check first, before a spec: GTK 4 and libadwaita on Windows (MSYS2 or gvsbuild, as other GTK apps ship them) and on macOS; `uv` and the models' PyTorch wheels per platform (CPU everywhere, CUDA on Windows, MPS on Apple Silicon), and which adapter locks are resolved for Linux only (Demucs, MuScriptor); ffmpeg, GStreamer and the Leipzig font in the package; the installer tools (WiX for `.msi`, Inno Setup or NSIS for `.exe`) and code signing (unsigned installers warn on both systems); CI runners for both. Stickler never ships model weights, so the setup assistant downloads them on every platform, as today.
- [ ] **macOS research (2026-11-16, at the owner's request; two research subagents, key facts checked):**
  - Models: all four app models resolve for macOS arm64. ADTOF's and Beat This!'s locks already hold torch 2.15 `macosx_14_0_arm64` wheels; Demucs and MuScriptor need their `environments` widened by `sys_platform == 'darwin' and platform_machine == 'arm64'` (the Linux-only restriction exists for an old torch on Intel Macs; a trial lock in a copy resolved). macOS 14 or newer. MPS (Metal) is untested for these models: ship CPU first, measure Demucs and MuScriptor on a Mac against the CPU (identical notes) before using it; the harness's device choice only knows CUDA today (`stickler_adapter.choose_device`), and `PYTORCH_ENABLE_MPS_FALLBACK=1` would be needed. Widening a pyproject changes its digest: add a `digests.yaml` pair for Linux (behaviour unchanged there).
  - Interface: GTK 4 + libadwaita on macOS works and ships in Gaphor (`.dmg` built with Homebrew + PyInstaller), with libadwaita drawing its own style (native window buttons since 1.8, no global menu bar); a native SwiftUI interface would rewrite the sheet view, playback, corrections and setup assistant over the Python core (as a subprocess). The research recommends GTK first, the owner's note of 2026-11-13 prefers native: open.
  - Distribution: signing and notarization outside the App Store need the Apple Developer Program (99 USD a year). Unknown and to test first on a real Mac: whether the hardened runtime lets the app run the `uv`, Python environments and models it downloads at first start. Verovio 6.4.1 has a `macosx_13_0_arm64` wheel; GStreamer has arm64 builds in Homebrew; GitHub's macOS arm64 runners are free for a public repository.
- [ ] **macOS version (owner, 2026-11-13: only an idea):** if at all, then Apple Silicon only, GPU via Metal (MPS), shipped as a .dmg, with a native macOS interface library instead of GTK. Points to check first: Apple Silicon only (Intel Macs are held at torch < 2.3 by Demucs), the GPU path would be MPS instead of CUDA/ROCm, several adapter locks are resolved for Linux only (Demucs, MuScriptor), Flatpak/AppImage do not exist there (a .app/.dmg or Homebrew instead), GTK 4 runs on macOS but does not look native.
- [x] **README badges** (owner's wish: shieldcn style, gradient, some nonsense badges): `scripts/badges.py` renders a rainbow row of facts and a shimmering row of jokes into `docs/badges/*.svg` (in the repo, so the README does not depend on the service); rerun it when test count, coverage or version change.
- [ ] **Open-source release (owner, 2026-11-13: publish so others can use it, no commercial intent)**
  - Documentation for humans:
    - **Benchmark report**: every decision (ADRs) and every result, readable without the code: datasets, pipelines, scores per class, runtimes, what was tried and did not help (fusion, voting, bar consensus) and why.
    - **CLI guide**: install, `setup`, `fetch`, `run`/`eval`/`report`, `align` for own songs, `notate`, `remote`, `tune`, with examples.
    - **Requirements**: CPU/RAM/disk per adapter and per mode (Fast/Quality), measured on the laptop and the GPUs: real-time factors, peak RAM, environment and weight sizes, optional GPU (CUDA/ROCm).
  - Licences: code MIT; a third-party overview (models and weights: ADTOF CC BY-NC-SA, MuScriptor CC BY-NC, YourMT3 GPL-3.0, Demucs MIT, BS-RoFormer, Beat This! MIT, ADT_STR CC BY-SA; datasets: MDB CC BY-NC-SA, ENST on request). Weights are downloaded by `setup`, never shipped. Decided 2026-11-13: MIT stays (the owner does not want to earn money with it; commercial use by others is fine).
  - Never published: own recordings, musescore transcriptions, ENST, aligned.json (all gitignored). How others build their own references must not describe bypassing musescore.com's paywall.
  - Done 2026-11-13: secret scan of the whole history (gitleaks 8.30.1: no leaks in 93 commits; no RunPod/HF token patterns), commit email anonymised (history rewritten, owner pushed), references name only file names (no folder or playlist names), CI on GitHub Actions (checks + gitleaks), CITATION.cff. Open: CONTRIBUTING.md (owner still deciding).
  - Privacy check before publishing: personal music paths and playlist names in references/own/*.yaml (use paths relative to a configurable music folder) (the commit email may stay public, owner 2026-11-13), a secret scan of the whole history (gitleaks).
  - Further ideas: CONTRIBUTING.md (adding an adapter, TDD, checks), CITATION.cff (Stickler plus the datasets and models it builds on, ENST citation required), CI with the unit tests, issue templates, a "reproduce the benchmark" guide.

- [ ] **Flathub (owner, 2026-11-13: maybe later):** only the GTK application (no console apps on Flathub). Rules as of 2026-10: AI-generated code allowed with disclosure, reviewers may still reject by its extent; the Flatpak manifest, the submission pull request, commit messages and replies must not be AI-generated, so the owner writes them himself. Technical: no network during the build (every dependency incl. PyTorch as a manifest source), no complicated post-install setup (today's `stickler setup`). First step instead: our own Flatpak via GitHub releases.
- [ ] **Raise the adapters' Python (owner, 2026-11-14: plan for the future):** all seven adapters are pinned to 3.12; the harness runs on 3.12–3.14 from Task 31 on. Raising an adapter changes its `pyproject.toml`, so its cache keys change and its results must be recomputed (no rekeying: new environments are a real change). To check first: wheels of the pinned PyTorch builds for the target version, above all AMD's ROCm wheels (ADR 0003 was verified on 3.12), and each model's own dependencies. Best done together with the next model refresh, so the benchmark is recomputed once.

- [ ] **Release pipeline: Flatpak and AppImage with every release**
  - Wish: A new release tag `vN` (ADR 0006) automatically builds a Flatpak and an AppImage.
  - Open points:
    - **Dependency:** Requires the GTK interface.
    - **Size:** The model environments are large (PyTorch per adapter, weights up to ~760 MB). It needs to be decided whether weights and environments are only loaded on first start.
    - **Licenses:** NC weights must not go into a distributed package (ADR 0002).
    - **CI:** The pipeline needs a CI service. Codeberg is out of the question, as it mostly disallows AI-generated programs.

- [x] **Everything in English** (done on 2026-11-12)
  - Done: code comments, docstrings, messages, tests, README, SPEC, ADRs, tasks, adapter READMEs, CONSTRAINTS.md, CLAUDE.md; commit messages in English from now on.
  - Adapters' `run.py`, `setup.py` and `pyproject.toml` translated after the benchmark finished. The `description` values and two error messages changed the code digests, so the cache was rekeyed (`stickler cache-digests` before, `stickler cache-migrate --rekey-from` after): 445 entries moved, evaluation identical before and after.

- [x] **Design the interface together (before any GTK code)**: done 2026-11-14, module `design` approved (SPEC.md, `docs/design/`): eleven screens in two rounds with the owner.
  - Wish (2026-11-12): design a beautiful interface together with the owner, following current design principles, including the GNOME Human Interface Guidelines.
  - Approach: collect the user flows (drop a song → separation and transcription with progress → sheet music preview → export of notes and drum track), then mockups (e.g. as an artifact or Penpot/SVG) to discuss and iterate before implementing in GTK 4 + libadwaita.

- [ ] **App feature: export the drum track**
  - Wish (2026-11-12): a button in the app that exports the separated drum stem ("can't hurt to have it").
  - Implementation: the stem already exists as an intermediate result. `transcribe_song` should return its path, and the GUI saves it as WAV or FLAC (FLAC via ffmpeg).

- [x] **App icon in GNOME style** (done 2026-11-15, see Phase 10)
  - Wish: An icon in the style of the GNOME app icons by Daudix (https://daudix.one/design/).
  - Implementation: Create as SVG following the GNOME HIG, with a symbolic variant.

- [x] **Readable sheet music: repeat signs** (owner, 2026-11-12; done 2026-11-13 for release 2)
  - `notate` gives nearly equal bars their common pattern (`notation.simplify`, Jaccard index ≥ 0.8, groups of ≥ 3 bars; fills stay) and writes runs of equal bars or phrases (up to 8 bars) once between repeat signs, with "n×" above from three times on. `--no-simplify`, `--no-repeats` write every hit as detected.
  - Measured as `@simple` (`simplify: true` in a config): similarity 0.6 cost 0.012 macro-F1 on the own songs and 0.022 on ENST; 0.8 is neutral on the own songs (ENST −0.003) and cuts the 25 own songs from 3354 to 2594 written bars (repeat signs alone: 3042). Owner chose 0.8.
  - Checked in MuseScore 4 (Eye of the Tiger: 110 → 46 bars, PDF without errors; music21 expands the repeats back to 110 bars).

- [x] **Two pipeline modes for the app: "Fast" and "Quality"** (owner, 2026-11-12): decided with the 25-song results and available as `notate --mode fast|quality` since release 1 (Phase 5c).

- [ ] **Ultrareview once the application is finished**
  - The user starts it themselves with `/code-review ultra`. I cannot trigger it.
