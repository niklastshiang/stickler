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
- [x] All tests green, `metrics.csv` with plausible F1 values for `none` × `adt_str` (kick clearly > 0.5)
- [x] Review with the user (owner, 2026-11-16)
  - Evidence (2026-11-16, for the owner's review): 697 tests green. `none` × `adt_str` was dropped by decision: ADT_STR is trained on isolated drums and hallucinates on the mix, so it only runs on stems (report section 7; `skip` in the configs). On stems its kick is clearly above 0.5: 0.93 (oracle), 0.94 (RoFormer), 0.91 (Demucs) on MDB (report 5.2). The criterion is met in substance with this deviation.

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

- [x] **Task 12: Transcriber `drumsep_onset`** (M): done 2026-11-16 (release 7). DrumSep's weights still come from audio-separator's own mirror (the original host answers 404); onsets per stem through `stickler_adapter.onsets` (shared with `sad`, peaks picked as `stickler.peaks`, tunable with `stickler tune --transcriber drumsep_onset`). MDB in a cloud container, oracle stems, untuned threshold: 10 of 23 tracks before the container's 2-hour limit stopped the run twice; KD 0.96, SD 0.89, TT 0.14, HH 0.77, CY 0.58, macro-F1 0.668 (5 classes), 0.873 (3 classes); 40 minutes for 10 minutes of audio on a shared CPU. The full MDB run is part of Task 84 (`config/benchmark.yaml` holds it).
  - Acceptance: The 6-stem model DrumSep (MDX23C) and librosa onset detection per stem yield GM MIDI.
  - Verify: `pytest -m adapters -k drumsep`, run on MDB
  - Dependencies: 5 · Files: `adapters/transcribers/drumsep_onset/*`

### Checkpoint B
- [x] Full matrix on MDB: every combination yields a MIDI or a logged error (Success Criterion 2)
- [x] Review with the user (owner, 2026-11-16)
  - Evidence (2026-11-16): report 5.2 scores every active MDB combination (ADTOF, ADT_STR, MuScriptor medium on oracle, Demucs, RoFormer; ADTOF also on the mix); the combinations left out are skipped by decision in `config/benchmark.yaml` (ADT_STR and MuScriptor medium on the mix, MuScriptor small), not missing. The release 7 candidates have their own criterion (SPEC "Release 7", criterion 1).

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
- [x] Report with MDB and at least one own song (Success Criteria 3 and 4)
- [x] Review with the user: choose the winning pipeline, `docs/adr/0005-gewinner-pipeline.md`: closed 2026-11-17 by [ADR 0008](../docs/adr/0008-modi.md) (the two modes and their history; `0005` is YourMT3+'s ADR)
  - Evidence (2026-11-16): `docs/report.md` and `report.html` cover MDB, ENST and 25 own songs (sections 5.1–5.4, with per-class F1, runtime, RTF and RAM). The winning pipeline was chosen by the owner as two modes, Fast and Quality (2026-11-13, kept on 2026-11-14 after the correction), recorded in report section 7 and Phase 5c, but not as an ADR: `0005` became YourMT3+'s ADR. Gap: no ADR for the modes; Task 86's ADR 0008 records their history too (owner, 2026-11-16), then this checkpoint can be ticked.

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
- [x] All 9 success criteria from SPEC.md met
- [x] Final review with the user (owner, 2026-11-16)
  - Evidence per criterion (2026-11-16): (1) `tests/test_evaluate.py`: self-comparison, 60 ms miss, 40 ms hit. (2) Checkpoint B. (3) `metrics.csv`, `report.html` and report 5.1–5.4 (P/R/F1 per class, micro and macro, runtime, RTF, peak RAM, ranking). (4) 25 own songs passed the quality criteria, click tracks heard by the owner (Task 15, report section 3). (5) `stickler notate` output opened in MuseScore 4.7.5 without errors, with time signature and drum notation (Task 18). (6) `tests/test_adapters.py`: dummy adapters from `tests/fixtures/adapters` by folder and config only. (7) `tests/test_runner.py::test_second_run_hits_cache`. (8) `stickler doctor` reports the GPU (Task 6); ADT_STR, MuScriptor, Demucs and RoFormer ran with `--device gpu` on the Radeon 840M with identical notes (their `pyproject.toml` notes, ADR 0003); CPU and GPU runtimes in report 5.4. (9) `tests/test_cli.py::test_cli_imports_only_the_api_from_stickler` and the delegation tests. All nine met; Checkpoint C's ADR gap stays.

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
- [ ] **Finer classes for notation** (owner, 2026-11-13: later): open/closed hi-hat, ride/crash; ADTOF does not distinguish them, MuScriptor does. Measured 2026-11-15 on the cached results: on the own songs MuScriptor M's open hi-hats are right half the time and it finds 10 % of the rides; ADTOF timing + MuScriptor's kind is no better than always "closed" (82 %). Waits for a new model that is measurably better (owner, 2026-11-15).

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

- [x] **Task 82: Transcriber `muscriptor_l`** (S): done 2026-11-17. Adapter and config entries in `main` (8a841da); `pytest -m adapters -k muscriptor_l` passes on the laptop; laptop time see Task 84 step 6.
  - Acceptance: copy of `muscriptor_m` with `SIZE = "large"` (own name, lock, README with source, version, licence CC BY-NC 4.0, gated, 5.47 GB); in `config/benchmark.yaml` and `config/own.yaml` like `muscriptor_m` (Demucs stem, skip on the mix); existing cache entries untouched.
  - Verify: `uv run pytest -m adapters -k muscriptor_l` (on RunPod or the laptop after `stickler setup --adapter muscriptor_l`); laptop time for one 4-minute song recorded
  - Dependencies: none · Files: `adapters/transcribers/muscriptor_l/*`, `config/*.yaml`, `SPEC.md` candidates table

- [x] **Task 83: Transcriber `sad` (Separate-and-Detect)** (M, risk): done 2026-11-16. The spike asked by the owner ("does a newer Python work?") showed the code runs on Python 3.12, torch 2.15 and pytorch-lightning 2.6 through seven shims in `compat.py`, without changing a file of the paper's code; the checkpoint loads with `weights_only=True` (no code in it runs) and holds the VAE and the vocoder, so MusicLDM's Zenodo files are not needed. Each 10.24 s window is a track of its own; the onset step is DrumSep's (`stickler_adapter.onsets`). First 10 s of MDB Punk's drum stem on a shared CPU: 92 minutes, 10.2 GB, F1 kick 0.84, snare 0.90, toms 0.20, hi-hat 0.24, cymbals 0.00 with the untuned threshold. The GPU run is part of Task 84.
  - Acceptance: spike first: the pinned commit of ddman1101/Separate-and-detect turns a 10 s drum stem into five stems and onsets, on CPU and on a RunPod GPU; then an adapter that gives GM MIDI from a Demucs stem, README with source, commit and licence (MIT), and the owner's exception noted. If the spike fails after two attempts: recorded in SPEC.md and the report as tried and left out (owner agrees).
  - Verify: `uv run pytest -m adapters -k sad`; laptop time for one 4-minute song recorded
  - Dependencies: none · Files: `adapters/transcribers/sad/*`, `config/*.yaml`

- [x] **Task 84: Benchmark runs** (M): done 2026-11-17 (ed95346); every candidate on MDB, ENST (64/64) and the 25 own songs, pods stopped and terminated. The laptop times go into the report with Task 86.
  - Prepared 2026-11-16: `stickler tune --transcriber drumsep_onset` tunes DrumSep's thresholds on its saved envelopes; the adapter picks peaks exactly as `stickler.peaks` (copy, kept identical by a test), so a tuned threshold reproduces its MIDI. Fusions take `transcriber:` (default adtof).
  - Status 2026-11-17 (read from `results/`, run on 2026-11-16 evening; no run log kept): runbook steps 0–2 done: `diff` against `results-before-87` adds only the new candidates' rows, no old row changed (Task 87 verified). Step 4 partly done on a RunPod GPU, untuned thresholds, macro-F1 with 3 classes:
    - MDB complete: `demucs+muscriptor_l` 0.831, `demucs+drumsep_onset` 0.798, `demucs+sad` 0.725 (oracle 0.869 / 0.844 / 0.754).
    - ENST: only oracle `muscriptor_l` 0.827 and oracle `drumsep_onset` 0.834 (61 of 64 tracks, 3 errors); oracle `sad` and every `demucs+` candidate missing.
    - Own songs: `demucs+muscriptor_l` 0.837, `demucs+drumsep_onset` 0.767 (Quality 0.849, `none+adtof` 0.841); `demucs+sad` missing.
    - GPU speed: `sad` 3194 s for 1309 s of MDB audio (about 2.4× real time, so roughly 10 minutes per 4-minute song); `muscriptor_l` about 0.17× real time; `drumsep_onset` about 0.08×.
    - Laptop time (step 6, 2026-11-17, AMD Ryzen AI 5 340, 12 threads, CPU): `drumsep_onset` on the cached Demucs stem of `eye_of_the_tiger` (245.6 s): 702 s, peak 1.9 GB (Demucs not included). `muscriptor_l` on the same stem: 699 s, peak 10.7 GB (under the 20-minute budget, so no GPU reference needed). `sad` goes to the pod (92 minutes for 10 s on CPU).
    - **Steps 4, 5 and 7 done (2026-11-17 evening):** a second pod ran ENST's `demucs+muscriptor_l` and `demucs+drumsep_onset` (61 tracks); the three "rock'n'roll" tracks were skipped on every pod run because `--only` lost their apostrophes in the host's shell (fixed in acd9a26), and were computed on the laptop's CPU (25 min). ENST now 64/64 for every candidate. `drumsep_tuned` (thresholds tuned on MDB + ENST, Demucs stem, 87 tracks) is in all three configs. Macro-F1, 3 classes, MDB / ENST / own: Quality 0.844 / 0.761 / 0.849; Fast 0.802 / 0.792 / 0.841; demucs+muscriptor_l 0.831 / 0.788 / 0.837; demucs+drumsep_onset 0.798 / 0.794 / 0.767; drumsep_tuned 0.809 / 0.803 / 0.742 (tuning helps MDB and ENST, hurts the own songs again). `stickler report` regenerated.
  - Separate-and-Detect (owner, 2026-11-17): tune first, then decide. Its thresholds are tuned on MDB from the saved envelopes (no pod time), and DrumSep's the same way so both get the same treatment: `uv run stickler tune --transcriber sad --inputs oracle --config config/benchmark.yaml --name sad_tuned`, likewise `--transcriber drumsep_onset --name drumsep_tuned`. If tuned `sad` stays more than 0.03 macro-F1 behind tuned `drumsep_onset` and `muscriptor_l` on MDB, it is closed as tested and inferior (report and ADR say so) and its ENST and own-song runs are skipped; otherwise they are run. Why: on MDB's oracle stems, close to its training data, it came last (0.754 vs 0.844 and 0.869, 3 classes) and weakest on hi-hat and cymbals, where Fast and Quality are strong; but it ran with Stickler's onset step and an untuned threshold, not the paper's detector.
  - Noticed 2026-11-16: an adapter's cache key covered only `run.py`, `setup.py` and `pyproject.toml`, not helper modules; fixed in Task 87.
  - Runbook (2026-11-16; runs from the laptop, a cloud session cannot reach a pod over SSH). No config of its own: `config/benchmark.yaml`, `config/enst.yaml` and `config/own.yaml` already hold the candidates (Demucs stem; oracle on MDB and ENST); everything cached is skipped.
    0. Before pulling: `cp -r results results-before-87` (results/ is not in git).
    1. On the laptop, after pulling: `uv run stickler eval --config config/benchmark.yaml`, the same for `config/enst.yaml` and `config/own.yaml`. Eval computes nothing but looks every result up, which renames it to its Task 87 key; without this the pod would rename the uploaded copies and the laptop would keep both. Not `cache-migrate`: it sets aside entries of inputs outside the datasets and reference songs (e.g. `stickler notate` runs).
    2. Task 87's verify: `diff -r results-before-87 results` shows only the new candidates' rows (as errors, "not computed"); every old pipeline's numbers are unchanged.
    3. A RunPod pod (RTX 4090, Secure Cloud in the EU, as for the own songs before) with a driver for CUDA 13.2 (`nvidia-smi` shows the CUDA version): torch 2.15 has CUDA wheels only on cu132 (found 2026-11-16 in the Windows research; the CUDA setup now tries cu132 first); Hugging Face login on the laptop (MuScriptor large is gated; the token goes to the pod over SSH input).
    4. `uv run stickler remote root@<ip> --port <port> --config config/benchmark.yaml`, then the same with `config/enst.yaml --wipe` and `config/own.yaml --pod-id <id> --wipe` (licensed data and the owner's songs are deleted from the pod; the last run stops it). Check the first run's times before starting the others: Separate-and-Detect's speed on the GPU is not measured yet.
    5. Thresholds of `drumsep_onset` and `sad` on MDB and ENST, without the own songs: `uv run stickler tune --transcriber drumsep_onset --inputs demucs --config config/benchmark.yaml --config config/enst.yaml --name drumsep_tuned` (likewise `sad`); the printed `fusions` entry goes into all three configs and is scored from the cached activations (nothing recomputed).
    6. Laptop time budget (SPEC Release 7, method 5): one 4-minute own song with `demucs+muscriptor_l` and `demucs+sad` on the laptop CPU (`meta.json` seconds); above 20 minutes, measure on the pod's GPU (the reference for a Quality that requires a GPU).
    7. `uv run stickler eval` for the three configs and `uv run stickler report`.
    - Lesson (2026-11-17): `--config config/enst.yaml` lets the pod fetch ENST from Zenodo (9.6 GB, about 30 minutes, and it nearly filled the 70 GB disk next to every adapter's CUDA environment). Since 2026-11-17 `stickler remote` uploads the prepared `data/enst` (1.9 GB) itself: the pod's own ffmpeg wrote another version tag into the mixes, so their cache keys differed and the pod recomputed Demucs and wanted to recompute ADT_STR and MuScriptor medium on the Demucs stem (found when the run was stopped for the host's maintenance at 17:00; the pod's partial results were fetched, the pod stopped and terminated). The remaining ENST jobs need a new pod.
  - Risk: `stickler setup --device cuda` builds `.venv-cuda` from each lock's torch version; sad's lock pairs torch 2.15 with torchaudio 2.11.1 (fine on CPU, not checked on CUDA). If its setup fails on the pod, the other candidates still run (a failed adapter is logged, not blocking).
  - `sad` closed (owner, 2026-11-17; SPEC Release 7, method 3, the rule of 9d5ff60): tuned on MDB oracle it stays far behind (mean F1 over 5 classes ≈ 0.60 against drumsep_onset ≈ 0.73 and muscriptor_l 0.81), so its ENST and own-song runs are skipped (`skip` in `config/enst.yaml` and `config/own.yaml`). The pod run left for ENST: `demucs+muscriptor_l` and `demucs+drumsep_onset`, with `--pod-id <id> --wipe`, output into `results/remote-release7-enst.log`; `remote` uploads the prepared `data/enst`.
  - Acceptance: `demucs+drumsep_onset`, `demucs+muscriptor_l`, `demucs+sad` (and a combination like Quality's for a candidate that is strong on some classes) on MDB, ENST and the 25 own songs; every combination gives MIDI or a logged error (SPEC Release 7, criterion 1); `metrics.csv` and `report.html` updated; RunPod pods stopped.
  - Verify: `uv run stickler eval` for the three configs; the time per 4-minute song on the laptop for each candidate in the report
  - Dependencies: 12, 82, 83 · Files: `config/*.yaml`, results (not committed)

- [x] **Task 85: Listening round, only if needed** (S): skipped 2026-11-17, no candidate comes close. Scheme: 5 classes (owner, 2026-11-17). Own songs, measured macro-F1: Quality 0.776, Fast 0.770, `demucs+muscriptor_l` 0.704, `demucs+drumsep_onset` 0.589 (`drumsep_tuned` lower still on the own songs). `muscriptor_l` loses on HH (0.715 vs 0.758) and CY (0.386 vs 0.680); in place of `muscriptor_m` inside Quality it would give 0.771, and large for KD/SD with medium for TT 0.777 (a tie, at twice the time). With 3 classes `muscriptor_l` (0.837) would have been within 0.01 of Fast (0.841); not the rule's scheme.
  - Acceptance: for each candidate within 0.01 of Fast's or Quality's measured macro-F1 on the own songs (or above it): about 40 spots from its own errors, drawn once with a fixed seed, judged blind with `stickler listen`; its corrected score as in release 3. Skipped, with the numbers stated, if no candidate comes close.
  - Verify: `uv run pytest -q tests/test_errors.py tests/test_api.py -k "sample or correct"`; `results/own/corrected.csv`
  - Dependencies: 84 · Files: `src/stickler/{errors,api}.py` if the sample needs a candidate filter, tests

- [x] **Task 86: Decision, report and release 7** (S): done 2026-11-17, release 7 published (bb1e4d6, tag v7, Flatpak and AppImage attached).
  - Prepared 2026-11-17: `docs/adr/0008-modi.md` holds the modes and their history (Checkpoint C closed); the decision per mode goes into its "Release 7" entry.
  - Decision 2026-11-17 (owner): Fast and Quality unchanged. ADR 0008's release 7 entry, `docs/report.md` section 5.6, README, SPEC Release 7 status; release steps of ADR 0006 (no open Dependabot alerts; the owner skipped the hand test before the tag).
  - Acceptance: ADR 0008 with the decision per mode (unchanged or replaced; owner), and the modes' history since the owner chose them (Fast and Quality, 2026-11-13; kept on 2026-11-14 after the correction), which closes Checkpoint C (owner, 2026-11-16); `docs/report.md` section on the new candidates; README candidates and results tables; release steps of ADR 0006 incl. the hand-tried feature list.
  - Verify: SPEC Release 7 success criteria; `scripts/check.sh task`
  - Dependencies: 84, 85 · Files: `docs/adr/0008-*.md`, `docs/report.md`, `README.md`, version files

- [x] **Task 87: Cache keys cover everything that defines an adapter** (M) (owner, 2026-11-16): done 2026-11-16. The digest covers every Python module and `pyproject.toml` of the adapter and `adapters/_common` (before: only `run.py`, `setup.py`, `pyproject.toml`, so a changed helper such as `onsets.py` kept old results valid). Pairs of equivalent digests are listed in `src/stickler/digests.yaml`; `cache_dir_for` renames an entry under an earlier digest to the current key on first use, but only along a chain that ends at the current digest, in the benchmark and the app, so neither the laptop nor installed apps compute anything again. Listed: every adapter unchanged since release 6; not drumsep_onset (its helper changed under the same old digest). A fresh-context review found three problems in the first version, all fixed: a listed digest stayed valid after later real changes (now pairs and chains), `cache-migrate` set listed entries aside (it now knows the pairs, and refuses snapshots of the old definition), and the digest depended on the machine (a `.venv` in the path, stray files; now only imported modules, relative names). The key now also covers `uv.lock` and `.python-version`. Same digests on Python 3.12 and 3.14.
  - Verify: `uv run pytest -q tests/test_cache_keys.py tests/test_runner.py tests/test_cachemigration.py`; on the laptop, the first `stickler run` after the update finds every cached result (nothing computed)

### Checkpoint P
- [x] All success criteria of SPEC.md "Release 7" met; the decision per mode by the owner; release 7 (2026-11-17)

## Phase 17: `legend` (approved 2026-11-17, SPEC.md "Module `legend`"), deferred

Status: deferred by the owner on 2026-11-17 ("maybe later, not needed now"): the code, names and tests stay, but the PDF export does not draw the legend (`ui/window.py`); switching it back on is one line. Task 91's owner check and Checkpoint Q wait with it.

- [x] **Task 88: Positions and the legend's MusicXML** (S): done 2026-11-17. Verovio 6.4.1 sets the legend of eight positions as one system, stemless, the time signature hidden (an empty element with `visibility="hidden"`), the names as lyrics. STAFF also has ride bell, china and splash: Task 89 names them too.
  - Acceptance: `notation.legend_positions(musicxml)` gives the distinct `Staff` values of the sheet's instruments, top to bottom, STAFF's order for ties, `OTHER` included, none for an empty sheet; `notation.legend_musicxml(entries, labels)` writes one stemless measure with each entry's step, octave and notehead and the labels as lyrics, hidden time signature.
  - Verify: `uv run pytest -q tests/test_notation.py -k legend`
  - Dependencies: none · Files: `src/stickler/notation.py`, `tests/test_notation.py`

- [x] **Task 89: The names** (S): done 2026-11-17. 15 names, one per staff position (incl. ride bell, china, splash, side stick, other percussion), as `N_()` in `logic/legend.py`; `legend.entries` and `legend.score` give a sheet's names and the legend's MusicXML. German "Becken" for the cymbal (owner), "Standtom", "Bassdrum", "Hi-Hat mit Fuß"; Spanish "Platillo", "Redoblante", "Tom de piso", "Bombo", for the teacher's review with the rest. msgmerge pre-filled "Open Hi-Hat" with "Open With…"'s translation again; translated by hand.
  - Acceptance: `stickler_gtk/logic/legend.py` with `N_()` names per position (Cymbal, Ride, Hi-Hat, Open Hi-Hat, Pedal Hi-Hat, High Tom, Mid Tom, Floor Tom, Snare, Side Stick, Bass Drum, Other Percussion; the cymbal position A5 is "Cymbal"), the entries of a sheet in the app's language; German ("Becken" for the cymbal) and Spanish complete.
  - Verify: `uv run pytest -q tests/gtk/test_translations.py tests/gtk/test_legend.py`
  - Dependencies: 88 · Files: `src/stickler_gtk/logic/legend.py`, `po/*`, tests

- [x] **Task 90: Room on page 1 and the legend drawn into it** (M)
  - Acceptance: the A4 pages of a sheet with positions get blank right/bottom credits after the band, in memory only; the legend's SVG sits under the band and above the first system (read from page 1's SVG), with and without a band; pages 2 and later start at the same top margin; the stored MusicXML is unchanged; every STAFF entry in the longest language stays one line.
  - Verify: `uv run pytest -q tests/gtk/test_engraving.py -k legend`
  - Dependencies: 88, 89 · Files: `src/stickler_gtk/logic/engraving.py`, tests
  - Done 2026-11-17: `engraving.a4_pages(xml, legend=...)`, `header_bottom`, `legend_box`; the room counts what sits above the first staff (tempo, cymbals), measured with and without blanks. All 15 positions in German are wider than A4 and Verovio squeezed the names into each other, so the legend is engraved at its natural width and drawn smaller only when it does not fit (SPEC point 5). The PDF export passes the legend (`ui/window.py`); its widget test is Task 91.

- [ ] **Task 91: The PDF and the owner's check** (S)
  - Acceptance: the written PDF has the legend on page 1 only (widget test with Poppler); the owner exports two songs (Fast and Quality) and checks names and layout.
  - Verify: `scripts/gtk.sh test`; by hand on the laptop
  - Owner's check on the laptop (planned for the evening of 2026-11-17): `git pull origin claude/gifted-curie-4n4pz4`, `scripts/gtk.sh`, export one song with Fast and one with Quality as PDF. Look for: the legend under title and band, clear of the tempo mark; the right names, each notehead in its place; page 2 without a legend and with its usual top margin. The widget test is written (2026-11-17, `test_the_pdf_has_the_legend_on_page_1_only`: a three-page sheet, the names found by Poppler on page 1 and on no later page; fails without the legend). Left: the owner's check.
  - Dependencies: 90 · Files: tests (`ui/pdf.py` unchanged)

### Checkpoint Q
- [ ] All success criteria of SPEC.md "Module `legend`" met (owner)

## Phase 18: Release 8 (macOS app), module `shared-core` (approved 2026-11-17, SPEC.md "Module `shared-core`")

- [x] **Task 92: Move the app logic and i18n to `stickler_app`** (M): done 2026-11-17. 15 modules and `i18n.py` moved with `git mv`, `APP_ID`, `APP_NAME`, `prefix()` in `stickler_app/__init__.py`; 14 logic test files in `tests/app/` (their own copy of the two XDG and setup fixtures); new boundary test: `stickler_app` imports no `stickler_gtk`, `stickler` no app package (fails on a probe import). `po/`: same texts, only source references and one line wrapped differently in `es.po`. 718 tests and 49 widget tests green.
  - Acceptance: `src/stickler_app/` holds the 15 modules of `stickler_gtk/logic/` (same names), `i18n.py`, and `APP_ID`, `APP_NAME`, `prefix()` in `__init__.py`; `stickler_gtk/logic/` and `stickler_gtk/i18n.py` are gone, no shims; every import updated (`stickler_gtk/ui`, `main.py`, `scripts/demo.py`, tests); `pyproject.toml` packages and coverage; `scripts/i18n.sh` scans both packages; logic tests in `tests/app/`, widget and boundary tests in `tests/gtk/`; boundary tests: `stickler_app` imports no `gi` and no `stickler_gtk`, `stickler` neither `stickler_app` nor Verovio; CONSTRAINTS.md rows name `stickler_app` (same rules). After `scripts/i18n.sh` the pot's `msgid` lines are unchanged.
  - Verify: `scripts/check.sh task`; `scripts/gtk.sh test`; `grep -rn "stickler_gtk.logic\|stickler_gtk/logic\|stickler_gtk.i18n" src tests scripts packaging docs CONSTRAINTS.md pyproject.toml` empty
  - Dependencies: none · Files: `src/stickler_app/*` (moved), `src/stickler_gtk/*`, `tests/app/*` (moved), `tests/gtk/test_boundaries.py`, `pyproject.toml`, `CONSTRAINTS.md`, `scripts/i18n.sh`, `scripts/demo.py`

- [x] **Task 93: Packaging paths, both packages built** (S): done 2026-11-17 (caf4933). The Flatpak (built from a manifest copy pinned to the commit, not installed: the owner's own Stickler Flatpak stays as it is) and the AppImage (pinned Arch image, from `git archive`) both hold `stickler`, `stickler_app` and `stickler_gtk`; inside each, the app and GTK modules import and German loads ("Song öffnen …"). The windows were not opened here; the owner's check (95) covers the running app.
  - Acceptance: the Flatpak manifest and `scripts/appimage.sh` copy `src/stickler_app`; both packages build locally from the commit (pinned, see the local Flatpak note) and start; the app opens the demo song in each.
  - Verify: local Flatpak and AppImage builds; a headless start of each (as for `packaging`)
  - Dependencies: 92 · Files: `packaging/flatpak/ng.tshia.Stickler.yml`, `scripts/appimage.sh`

- [x] **Task 94: `scripts/xcstrings.py`, the String Catalog from `po/`** (M): done 2026-11-17. 14 tests (written first): positional placeholders by name incl. reordering, format specs dropped, `%%` only in texts with placeholders, plurals keyed by the plural form with the count as `%1$lld` (English `one`/`other` too), the errors for two placeholders in a plural and for another plural rule, comments, fuzzy/missing left out, multi-line and escapes, Xcode-shaped stable JSON, `--check`; the committed catalog (156 texts, de, es) is checked by a test, so `scripts/check.sh task` covers it; `scripts/i18n.sh` regenerates it.
  - Acceptance: as SPEC.md "Module `shared-core`", scope 5: positional placeholders by name (reordering kept), plurals as `one`/`other`, an error for another plural rule, `Translators:` comments, missing and fuzzy entries left out, deterministic output, `--check`; `mac/Stickler/Localizable.xcstrings` generated and committed; `scripts/check.sh` runs `--check`.
  - Verify: `uv run pytest -q tests/test_xcstrings.py`; `uv run python scripts/xcstrings.py --check`
  - Dependencies: none (92 only for the source paths in comments) · Files: `scripts/xcstrings.py`, `tests/test_xcstrings.py`, `mac/Stickler/Localizable.xcstrings`, `scripts/check.sh`

- [x] **Task 95: The owner's check** (S): done 2026-11-17 by the owner on the laptop.
  - Acceptance: on the laptop, `scripts/gtk.sh` in German: open a song, analysis, sheet music, playback, corrections, export of MusicXML and PDF behave as before.
  - Verify: by hand (owner)
  - Dependencies: 92, 93

### Checkpoint R
- [x] All success criteria of SPEC.md "Module `shared-core`" met (owner, 2026-11-17); then the next module specs of release 8 (`mac-design`, `mac-core`, in parallel)

## Phase 19: Release 8 (macOS app), module `mac-core` (approved 2026-11-17, SPEC.md "Module `mac-core`")

- [x] **Task 96: Peak RAM in the right unit on macOS** (S): done 2026-11-17. `_peak_rss_mb(platform)` divides by 1024² on `darwin`, 1024 elsewhere; a test fixes both. Every adapter's digest changed (`adapters/_common`); a pair each in `digests.yaml`, the first ones for drumsep_onset and sad. `stickler eval` for MDB, ENST and the own songs: every earlier row identical; ENST gained rows from new results (oracle+drumsep_onset 62 instead of 61 tracks, oracle+sad 1 track from the stopped pod). Two tests adjusted for the edit: the fixture digest (its docstring says a `_common` edit changes it) and the release-6 chain test, which now names the two adapters added after release 6.
  - Acceptance: `stickler_adapter._peak_rss_mb` reads `ru_maxrss` as bytes on `darwin` and KiB elsewhere; a test fixes both (the Linux number unchanged); a `digests.yaml` pair for every adapter (taken with `stickler cache-digests` before and after).
  - Verify: `uv run pytest -q tests/test_adapter_common.py` (or where `_peak_rss_mb` is tested); `stickler eval` for `config/benchmark.yaml` and `config/own.yaml` reads every result (ENST after the pod run)
  - Dependencies: none · Files: `adapters/_common/src/stickler_adapter/__init__.py`, a test, `src/stickler/digests.yaml`

- [x] **Task 97: Demucs and MuScriptor on macOS arm64** (M): done 2026-11-17. `environments` widened for demucs, muscriptor_m and muscriptor_l; relocked (macOS gets its own fork: torch 2.15.0 and torchaudio 2.11.1 from the CPU index without `+cpu`). `scripts/lock_platforms.py` (8 tests; follows dependency markers from the root, a marker only counts as "not Linux" when every `or` clause names another platform): 34, 60 and 60 Linux packages, 0 differences each; `uv sync --dry-run --locked` would change nothing in the three Linux environments. `digests.yaml` pairs; `stickler eval` for MDB, ENST and the own songs byte-identical.
  - Acceptance: `environments` widened by `sys_platform == 'darwin' and platform_machine == 'arm64'` for Demucs, MuScriptor medium and large; new locks; `scripts/lock_platforms.py` shows the Linux packages, versions and hashes identical before and after (its output in the commit message); `digests.yaml` pairs; nothing for Linux moved, else stop and ask.
  - Verify: the comparison script; `uv run pytest -q`; `stickler eval` as in 96
  - Dependencies: 96 · Files: `adapters/separators/demucs/{pyproject.toml,uv.lock}`, `adapters/transcribers/muscriptor_{m,l}/{pyproject.toml,uv.lock}`, `scripts/lock_platforms.py`, its test, `src/stickler/digests.yaml`

- [x] **Task 98: The test suite on a macOS runner** (M): done 2026-11-17 (3c69f0e, all jobs green). Job `macos` in `check.yml`: Python 3.14, Homebrew ffmpeg, `scripts/check.sh task`. The first run passed 737 of 744; the 7: the tests' process helper read `/proc` (now `ps` where there is none) and `fetch enst` gave BSD tar `--wildcards` (now only GNU tar). No test skipped.
  - 2026-11-17: on `macos-15` for now; GitHub did not assign a `macos-26` runner twice (capacity). Back to `macos-26` once it can (owner).
  - Acceptance: a job on `macos-26` (arm64), Python 3.14, Homebrew ffmpeg, runs `scripts/check.sh task` green; every test that cannot hold on macOS is fixed or skipped with `skipif(sys.platform == "darwin", reason=...)`, each named in the commit message; Linux jobs unchanged.
  - Verify: the workflow run on GitHub, all jobs green
  - Dependencies: 97 · Files: `.github/workflows/check.yml` (or `mac.yml`), tests as needed

- [x] **Task 99: The models' smoke tests on the macOS runner** (S): done 2026-11-17. `models-macos.yml` (pushes touching `adapters/` or `src/stickler/`, Mondays, by hand): ADTOF, Beat This! and Demucs set up and their smoke tests green on macos-15 arm64; MuScriptor medium and large install from their locks (run with the adapters' own Python, not the job's `UV_PYTHON`). The smoke tests now assert peak RAM between 10 MB and 32 GB. First numbers on the runner's CPU, 10 s clip: ADTOF 2.8 s / 529 MB, Beat This! 1.2 s / 416 MB, Demucs 44.3 s / 2.0 GB (the laptop: 1.4 s / 406 MB, 1.5 s / 405 MB, 20.7 s / 1.6 GB); the owner's Mac gives the real numbers.
  - Acceptance: `stickler setup` for ADTOF, Beat This! and Demucs and their smoke tests (`pytest -m adapters`) on the runner's CPU, on pushes touching `adapters/` or `src/stickler/` and weekly; MuScriptor's lock checked with `uv sync --locked`; each smoke run's seconds and peak RAM in the job summary, peak RAM plausible.
  - Verify: the workflow run on GitHub; the job summary
  - Dependencies: 98 · Files: the workflow, `tests/test_adapter_smoke.py` only if a model needs a platform note

### Checkpoint S
- [x] All success criteria of SPEC.md "Module `mac-core`" met (owner, 2026-11-18, from the CI results; evidence 2026-11-17: (1) the `macos` job green, 745 tests, coverage ≥ 95 %; (2) the three models' smoke tests green with plausible RAM; (3) Linux unchanged: lock comparison 0 differences, `stickler eval` byte-identical, CI green on 3.12 and 3.14; (4) no test skipped. On macos-15 for now, see Task 98); then `core-bridge`'s spec (and `mac-design` with the owner)

## Phase 20: Release 8 (macOS app), module `core-bridge` (approved 2026-11-18, SPEC.md "Module `core-bridge`")

- [x] **Task 100: The controller, analysis flows** (M): done 2026-11-18. `Controller(post=...)` keeps the state behind a lock and calls `post` with each event in order, from the thread that made the change (`post` must not block): `Changed(state)`, `RecentChanged(songs)` and `Notice(text)` for what the window showed as a toast (recent songs or a correction not saved, a correction that failed). `open`, `retry`, `cancel`, `close`, `forget_recent`, `correct` (the pause before notating is a `threading.Timer` of 0.25 s), `shutdown(seconds)` for quitting; `retry`, `cancel` and `correct` return False when the state does not fit (for the bridge's `not_now`). 16 tests with a fake `stickler.api`, controller coverage 100 %. The owner agreed (2026-11-18): the bridge sends a `Notice` as a `notice` event (SPEC.md, Task 103).
  - Acceptance: `stickler_app.controller.Controller(post=...)` owns the `session.State`; `open`, `cancel`, `retry`, `close`; one job at a time (a new `open` cancels the running one); recent songs updated after a result (`recent.add`, saved) and `forget_recent`; corrections read from the store as the window does, and `correct` (a changed beat notated again, the newest change wins, stored per song) for the GTK app; the Mac app gets that command with `mac-corrections`. No GTK, no GLib.
  - Verify: `uv run pytest -q tests/app/test_controller.py` with the fake adapters: an analysis to `Result`, a cancel during it back to the previous state, an unreadable file, `SetupMissing` to `Consent`, a second `open` while one runs, two quick corrections (only the second one shown)
  - Dependencies: none · Files: `src/stickler_app/controller.py`, `tests/app/test_controller.py`

- [x] **Task 101: The controller, setup and exports** (M): done 2026-11-18. `start` (shipped sources synced, the model check in a thread that `shutdown` does not wait for; a song opened meanwhile is left alone), `agree`, `not_now` (also "Later" after a failed download), `retry_setup`; the download measured every 0.5 s by a thread with a stop event, which ends with the setup; the song opened after it. `export_musicxml`, `drum_track_cost` (a `DrumTrackCost`: minutes, text, whether Demucs comes first), `export_drum_track` (Demucs downloaded first when missing, as the cost said; checked again at the start), `removal_sizes` (walks the folders: for a thread), `remove_models` and `can_remove_models`. A saved file is a `Notice` with `opens` (the toast's "Open" in GTK). 37 controller tests, coverage 100 %. Noticed: the widget test's fake `export_drum_track` returns the byte count instead of the path, so the window's "Saved" toast failed unseen in that test; fixed with the owner's go (a48a62e, not run here: no GTK 4 in the container).
  - Acceptance: `start` (sync of shipped adapters when packaged, `api.mode_ready`, the stored consent → `Empty`, `Consent` or `SettingUp`), `agree`, `not_now`, `retry_setup`, the download meter sampled twice a second by a thread with a stop event, the song opened after the setup; `drum_track_cost` and `export_drum_track`; `export_musicxml`; `removal_sizes` and `remove_models` (consent reset, with everything also the recent list).
  - Verify: `uv run pytest -q tests/app/test_controller.py`: consent and download, a failed step and Try Again, cancel during the setup, the drum track with and without the download, the removal; coverage ≥ 95 %
  - Dependencies: 100 · Files: `src/stickler_app/controller.py`, its tests

- [x] **Task 102: The Mac kind in `paths`** (S): done 2026-11-18. `packaged()` gives `"macos"` with `STICKLER_PACKAGED=macos` (Flatpak and AppImage are checked first); `data_home`, `cache_home` and the new `config_home` give `~/Library/Application Support/Stickler` and `~/Library/Caches/Stickler` there, XDG variables still win. Every store path now comes from `paths` (`recent`, `corrections`, `settings` built their XDG paths themselves). The Mac app's results sit in its data folder (SPEC point 4: macOS may empty Caches), so "Remove Downloaded Models…" takes `results` there too; the list of everything has no duplicate (its settings sit in the data folder). New `tests/app/test_paths.py` (7 tests): the Linux table (checkout, AppImage, Flatpak) passes on the code before this task too; the Linux tests elsewhere unchanged.
  - Acceptance: `packaged()` returns `"macos"` with `STICKLER_PACKAGED=macos`; models, results and settings under `~/Library/Application Support/Stickler`, scores and clicks under `~/Library/Caches/Stickler`, XDG variables still win; Linux results unchanged.
  - Verify: `uv run pytest -q tests/app/test_paths.py` (Linux cases untouched, new Mac cases)
  - Dependencies: none · Files: `src/stickler_app/paths.py` (and `settings.py`, `recent.py`, `corrections.py` if their store paths need it), tests

- [x] **Task 103: The bridge's loop and state** (M): done 2026-11-18. `stickler_app.bridge`, entry point `stickler-bridge` (and `python -m`): `hello` (protocol 1, version from the package, the catalogue's language or `en`), then the empty state and the recent songs; one reply per command; `state`, `recent` and `notice` events (`notice` with `opens`, a saved file) with one `seq` across them, written by one writer thread. `encode` per kind with the translated texts and `can_*` for every command; the queue keeps only the newest 64 unsent states, never drops a reply or notice. Errors `bad_request` (also blank `id`: reply with `id: null`), `unknown_command`, `bad_argument`, `not_now`, translated (de, es; msgmerge pre-filled one German and one Spanish entry with a wrong fuzzy match, removed). `main()` keeps the real stdout for the protocol and points file descriptor 1 at stderr, so a library's or model's output cannot break a line; its test is the process test of 105. The controller's fakes moved to `tests/app/fakes.py`. 31 bridge tests; `bridge.py` 96 % (only `main`). A command handler that raises (a bug) gets `internal` since 104 (owner).
  - Acceptance: `stickler_app.bridge` with entry point `stickler-bridge`: `hello`; commands with exactly one reply; `state` and `notice` events with `seq` from one writer thread; `encode` per state kind with translated texts and the possible commands; `bad_request`, `unknown_command`, `bad_argument`, `not_now`; `quit` and stdin EOF cancel the job, wait at most 2 s, exit 0; logs only on stderr. Commands here: `start`, `agree`, `not_now`, `retry_setup`, `open`, `cancel`, `retry`, `close`, `quit`.
  - Verify: `uv run pytest -q tests/app/test_bridge.py` in process with in-memory streams: each command, each error, `seq` order, cancel, EOF during a job
  - Dependencies: 100, 101 · Files: `src/stickler_app/bridge.py`, `pyproject.toml` (entry point), tests

- [x] **Task 104: The remaining commands and `docs/bridge.md`** (M): done 2026-11-18. `pages {width, zoom}` (zoom defaults to the stored note size, clamped) and `a4_pages` (with the PDF's title): SVG, size and the bars' rectangles (rounded to 0.01 px); `export_musicxml`, `drum_track_cost`, `export_drum_track`, `forget_recent`, `settings` (with the menu's percent), `set_zoom`, `zoom_in`, `zoom_out`, `actual_size` (remembered; unsaved it still holds), `removal_sizes` (bytes and the dialog's text for both choices; `setup.size_text`, was private), `remove_models {everything}`; `internal` for a command that raises (owner). Found on the way: Verovio's Python module sets its fonts' path for toolkits made on the main thread only, so engraving on the bridge's reader thread found no font; `engraving.render` now sets the path itself (a thread test fails without it; the GTK app engraves on the main thread, same path as before). `docs/bridge.md`: lines, errors, events, states (each with its fields), every command with a request and reply taken from real output; `tests/app/test_bridge_doc.py` checks commands, state kinds and their fields, events, error codes and that every example decodes. 45 bridge tests, 13 document tests; `bridge.py` 97 % (only `main`, for 105).
  - Acceptance: `pages {width, zoom}` and `a4_pages` (SVG, size, bar rectangles), `export_musicxml`, `drum_track_cost`, `export_drum_track`, `forget_recent` with `recent` events, `settings`, `set_zoom`, `zoom_in`, `zoom_out`, `actual_size`, `removal_sizes`, `remove_models`; `docs/bridge.md` with every command, reply, event and state field and an example line each; a test compares the document's commands and state kinds with the code and decodes its examples.
  - Verify: `uv run pytest -q tests/app/test_bridge.py`; coverage ≥ 95 %
  - Dependencies: 103 · Files: `src/stickler_app/bridge.py`, `docs/bridge.md`, tests

- [x] **Task 105: The bridge as a process, with the real models** (S): done 2026-11-18. The container's part done 2026-11-18; the run with the real Fast models done 2026-11-18 in the owner's WSL (Ubuntu 26.04): Eye of the Tiger a `result` after 28.4 s (♩ = 109, 4/4), `pages` at 1000 px one page, 43 bars, the line 0.39 MB, the MusicXML identical to the GTK app's. The CI run of 9cb817a green on every job, `macos` included (it runs `scripts/check.sh task`, the bridge's process tests with it). `tests/app/test_bridge_process.py` (4 tests, about 6 s): `python -m stickler_app.bridge` with stand-in models called `adtof` and `beat_this` that run through the real chain (their own uv environment and process group, the results cache): hello, `open` until `result`, `pages`, `quit` with status 0; stdin closed while the stand-in "model" waits ends the bridge (status 0) and the model within 3 s, and no cache entry is left; a `print` and a raw write to file descriptor 1 land on stderr, never in the protocol; `scripts/bridge_demo.py` on the stand-ins. The demo opens a song through the bridge, prints the steps, asks for `pages` (prints the line's size), saves the MusicXML and compares it with what the GTK app's call (`analysis.analyse`, in process, from the cache) writes. The real models could not be set up in the container (its proxy refuses the ADTOF archive on github.com: 403).
  - Owner, on the laptop (or WSL): `uv run stickler setup --adapter adtof`, `uv run stickler setup --adapter beat_this` (if not set up), then `uv run python scripts/bridge_demo.py "<Eye of the Tiger>"`; note the `pages` line's size here.
  - Acceptance: a subprocess test (`hello`, `open` on a fixture song with fake adapters until `result`, `pages`, `quit`; stdin closed during an analysis ends the bridge and the model process within 3 s, no cache entry left); `scripts/bridge_demo.py` drives the bridge on the laptop with the real Fast models and writes the MusicXML, identical to the GTK app's for the same song; the size of Eye of the Tiger's `pages` line noted. Green on the `macos` job.
  - Verify: `uv run pytest -q tests/app/test_bridge_process.py`; `uv run python scripts/bridge_demo.py <song>`; the CI run
  - Dependencies: 102, 104 · Files: the test, `scripts/bridge_demo.py`

- [x] **Task 106: The GTK window onto the controller** (M): done 2026-11-18; the owner's check by hand done 2026-11-19 in WSL (open, analysis, sheet, playback, corrections, exports: nothing differs). The one thing seen, the Save As dialog opening twice with a plain title bar, came from starting the app with `GDK_BACKEND=x11`; on Wayland it opens once with GTK's header. `window.py` (918 → 698 lines) turns clicks into the controller's commands and draws what it reports; `post` is `worker.to_main_loop`: at once on the main thread (a click's change is drawn before its handler returns, as the widget tests expect, e.g. Cancel), else `GLib.idle_add`; a late event draws the controller's newest state and list, not its own. Widget tests unchanged, 49 green (`scripts/gtk.sh test` in the owner's WSL). The fresh-context review of 100–106 found three races in the controller, now fixed with a test each (each fails without its fix): `shutdown` joins every job still cleaning up, replaced ones too; no job starts after `shutdown` (a setup ending as the app quits opened its song); a correction timer that fired while a newer change held the lock started a second run. Also from it: `docs/bridge.md` says which commands make the next ones wait, and that relative paths are read from the bridge's folder. Answered, not changed: "Remove" while a job runs does nothing now (the menu item is greyed then; the old window cancelled the job and removed anyway, reachable only in a race with the alert open); a correction now redraws the panel from the controller's state (same values; worth a look by hand: Back after moving the first beat).
  - Acceptance: `stickler_gtk/ui/window.py` keeps only widgets and dialogs; every flow goes through `stickler_app.controller` with a `post` that draws on the main loop (`worker.to_main_loop`: at once from the main thread, else `GLib.idle_add`); the widget tests unchanged and green; a fresh-context review of 100–106 against SPEC.md, its findings fixed or answered.
  - Verify: `scripts/gtk.sh test`; `scripts/check.sh task`; by hand by the owner (as Task 95: open, analysis, sheet music, playback, corrections, exports, setup, removal)
  - Dependencies: 101, 105 · Files: `src/stickler_gtk/ui/window.py`, `src/stickler_gtk/ui/worker.py`

### Checkpoint T
- [x] All success criteria of SPEC.md "Module `core-bridge`" met (owner, 2026-11-19, after the check of the GTK window by hand, task 106); then `mac-shell`'s spec

## Phase 21: Release 8 (macOS app), module `mac-shell` (approved 2026-11-18, SPEC.md "Module `mac-shell`")

- [x] **Task 107: CI and the Swift quality bar** (M): done 2026-11-18 (9737358, `mac` green on both jobs: `macos-26` assigned at once, Xcode 26.6, Swift 6.4.2; SwiftLint 0 violations; coverage 3/3 lines). In WSL: Swift 6.4.2 through swiftly 1.2.0 (signatures checked, no shell profile changed; the owner installed the toolchain's apt packages), SwiftLint's static Linux build in `~/.local/bin` (on Linux it skips `statement_position`, which needs SourceKit; the macOS job runs it). The skeleton had no executable line, so the coverage script found nothing to measure; instead of loosening it, `BridgeProtocol.speaks(_:)`, which the client of 109 needs, came early.
  - Acceptance: CONSTRAINTS.md covers Swift (SPEC "mac-shell" scope 5); `scripts/floor_guard.py` flags `swiftlint:disable`, `// swiftlint:`, `fatalError("TODO")`, placeholder `preconditionFailure`, `XCTSkip` and disabled tests in a diff (tests for each); `mac/SticklerCore/` a package with one passing test; `.github/workflows/mac.yml`: `ubuntu-26.04` runs `swift test` and SwiftLint 0.65.1 (pinned binary, SHA-256 checked); `macos-26` with Xcode 26.6 selected runs the same plus `swiftlint --strict`.
  - Verify: `uv run pytest -q tests/test_floor_guard.py`; `swift test` in `mac/SticklerCore` (WSL, Swift 6.4 via swiftly); both jobs green
  - Dependencies: none · Files: `CONSTRAINTS.md`, `scripts/floor_guard.py`, its tests, `mac/SticklerCore/`, `.github/workflows/mac.yml`, `.swiftlint.yml`

- [x] **Task 108: The protocol in Swift** (M): done 2026-11-18 (d754bf1, `mac` green on Linux and `macos-26`: 18 tests, coverage 99.16 %, SwiftLint 0 violations). `AppState` (screen enum with the eight kinds, `Abilities` from the `can_*` fields), `Incoming` (hello, events with `seq`, replies with typed payloads via `Reply.payload(_:)`), `BridgeError`, `Command` (22 commands, one line each). The tests read `docs/bridge.md`: every example decodes and encodes back to the same JSON; commands, state kinds, events and error codes match its sections. A newer core's unknown kind, event or error code is kept; a missing `can_*` field means not allowed; a line that is neither event nor reply (or not UTF-8) is refused. SwiftLint: the protocol's names `x`, `y`, `ok`, `id` allowed in `.swiftlint.yml`.
  - Acceptance: `Codable` types for `hello`, `state` (every kind and field of `docs/bridge.md`), `recent`, `notice`, replies and errors; commands encoded as one line each; every example line of `docs/bridge.md` decodes (the test reads the document, as `tests/app/test_bridge_doc.py`), an unknown state kind or field fails loudly in tests and is kept as `unknown` at run time.
  - Verify: `swift test` on Linux and macOS; coverage ≥ 95 %
  - Dependencies: 107 · Files: `mac/SticklerCore/Sources/`, tests

- [x] **Task 109: The process client** (M): done 2026-11-18 (cf4917e, `mac` green on Linux and `macos-26`: 31 tests against the real bridge with the stand-ins and fake cores, coverage 97.76 %). `CoreClient` reads stdout and stderr on threads of its own with `availableData` (`read(upToCount:)` waits for the whole count on Linux, so nothing arrived), matches replies by `id`, reports the end once after the last event (exit status or signal, stderr's last 40 lines, then the newest 5 unreadable lines), ends a core of another protocol version; `quit` sends `quit`, closes stdin, terminates after 3 s. Found on the way: Foundation on Linux does not reset a child's signal mask and the threads of Swift's concurrency pool block signals, so a core started from one ignored SIGTERM (and passed that mask on to the models): the client starts it from a thread with an empty mask (a test checks the child's mask). `uv run` keeps the bridge as its child: SIGTERM to uv reaches it, SIGKILL to uv would orphan it; the test kills the bridge itself, as a crash would. The stand-in models moved to `scripts/bridge_stand_ins.py`, used by the Python process test and the Swift tests; the mac jobs install uv and ffmpeg.
  - Acceptance: starts `uv run stickler-bridge` in a given folder with `STICKLER_PACKAGED=macos` and `STICKLER_ADAPTER_SOURCES`, reads lines with `read(upToCount:)` on its own thread (lines split across reads, long `pages` lines), matches replies to commands by `id` (async `send` returning the reply), delivers events in order, reports the end of the process with its status and stderr's last 40 lines; `quit` waits at most 3 s, then terminates.
  - Verify: `swift test` against the real bridge with the stand-in models of `tests/app/test_bridge_process.py` (`hello`, `open` until `result`, `cancel`, `quit`, a killed core reported), on Linux and macOS
  - Dependencies: 108 · Files: `mac/SticklerCore/`, a helper script for the stand-ins if needed

- [x] **Task 110: The window's model** (M): done 2026-11-18 (998522b, `mac` green on Linux and `macos-26`: 45 tests, coverage 97.66 %). `AppModel` (`@MainActor`, `@Observable`): state, recent songs, the newest notice, the language, the phase (needs a folder, running, stopped with its end). Events come through one `AsyncStream`, so the core's order holds (separate tasks per event would not); a late `seq` is dropped; a core replaced by Start Again is not listened to. Each action sends one command; a refusal shows the core's translated message as a notice. The folder is checked (`pyproject.toml`, `adapters/`) and remembered in `UserDefaults`; `uv` is looked for in `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, then `PATH`. 14 tests with a fake core. SwiftLint: `uv` allowed as a name.
  - Acceptance: an `@Observable` `AppModel`: the latest state, recent songs, the notices (the newest shown, each with `opens`), the stopped core (details, `startAgain()`), the core's folder (checked for `pyproject.toml` and `adapters/`, remembered, `uv` found in `~/.local/bin`, `/opt/homebrew/bin`, `PATH`); every user action forwards one command and nothing decides a flow.
  - Verify: `swift test` with a fake core on Linux and macOS; coverage ≥ 95 %
  - Dependencies: 109 · Files: `mac/SticklerCore/`

- [x] **Task 111: The app, its window and menus** (M): done 2026-11-18 (64e29a9, `mac` green on all three jobs at the first try; screenshots M0 folder, M4 empty, M6 placeholder in light and dark; the ad-hoc signed app as artifact, its catalog compiled to de/es/en). XcodeGen 2.46.0 (2026-07-16; 2.47.0 was a day old) generates the project from `mac/project.yml`. The window: title and subtitle from `AppModel`, Open in the toolbar, drop (sound files only), the folder question with its two problems, M4 with the recent songs (missing ones dimmed with a remove button), the result placeholder; File (Open…, Open Recent with Clear Menu, Choose Stickler Folder…) and Help. `ScriptedCore` plays the core's own lines for the screenshots. The Mac app's texts live in `stickler_app/mac_texts.py` (German and Spanish; msgmerge's four fuzzy guesses per language were wrong). Seen in the screenshots: prominent buttons are grey because the captured window is not key; the dark folder picture has two white circles in the title bar, likely the capture of macOS 26's glass, to be checked against the owner's Mac.
  - Acceptance: `mac/project.yml` (XcodeGen, pinned) with the app target (Swift 6, macOS 26) using `SticklerCore` and the String Catalog; the toolbar with title, subtitle and the Open/Export capsule; the empty window (M4) with drop area, "Open a Song…" and recent songs; the menu bar (M8) incl. Open Recent and "Choose Stickler Folder…"; the first start's folder choice; the result placeholder; minimum 640 × 480; `mac.yml` builds the app, runs its tests with coverage, saves screenshots of M4 (light, dark) and the ad-hoc signed `Stickler.app` as a `ditto` zip.
  - Verify: the `macos-26` job green; the screenshots against the canvas
  - Dependencies: 110 · Files: `mac/project.yml`, `mac/Stickler/`, `mac/SticklerTests/`, `.github/workflows/mac.yml`, `po/*` for new texts

- [x] **Task 112: Analysis, errors, the stopped core** (M): done 2026-11-18 (a631010, fixed in 806c8a1; `mac` green on all jobs: 7 app tests, 50 SticklerCore tests). M5's step list (mark, label, detail, status: Done, Running, Waiting; Cancel) for the analysis ("Takes about 15 seconds") and the drum track; the failed song with Technical Details, Open Another Song… and Try Again; "Stickler Stopped Unexpectedly" with `CoreEnd.summary` and Start Again. Screenshots light and dark. The first run failed on `CoreEnd`'s internal initializer: the Linux tests import SticklerCore `@testable`, the app's do not. The CI prints the app tests' summary from the result bundle.
  - Acceptance: the step list with Cancel (M5), the error page with Technical Details, "Open Another Song…" and "Try Again", the page "Stickler Stopped Unexpectedly" with "Start Again"; drop and open start an analysis; screenshots light and dark.
  - Verify: the app's model tests with a fake core; screenshots
  - Dependencies: 111 · Files: `mac/Stickler/`, tests, `po/*`

- [x] **Task 113: The setup assistant and the removal** (M): done 2026-11-18 (7707315; `mac` green: 12 app tests, 50 SticklerCore tests on Linux and macOS; the first `core-linux` run hung 10 minutes in `apt-get install ffmpeg`, cancelled and run again). Sheets over the empty window from the core's state (closed only by its next state): consent (M1), download (M2) on the step list, a server not answering (M3); Stickler › Remove Downloaded Models… asks the core for the sizes, then an alert whose body follows the checkbox. Every text is the GTK app's from `po/`; placeholders and the consent's plural filled from the catalog (`localized`). The consent shows the app's generic icon: the macOS icon of `mac-design` is not in the app yet.
  - Acceptance: M1–M3 as sheets over the empty window (consent with models, licences and sizes; download with Cancel and the amount; a failed download with server, details, "Try Again", "Later"); "Remove Downloaded Models…" with sizes, the checkbox and a destructive button; screenshots light and dark.
  - Verify: tests with a fake core; screenshots against the canvas
  - Dependencies: 112 · Files: `mac/Stickler/`, tests, `po/*`

- [x] **Task 114: Exports and the saved bar** (M): done 2026-11-18 (602014e; `mac` green: 14 app tests, SticklerCore 97.3 %). The Export menu (M7) in the toolbar and under File, with the GTK menu's second lines; MusicXML… and Drum Track… through `NSSavePanel` with the GTK app's names (`ExportName`, tested on Linux), the drum track's cost asked first; Open With… lets the reader pick a program for the MusicXML; the newest notice in a bar at the bottom with Show in Finder for a saved file, gone after 8 s. Differs from the canvas, for the owner: the MusicXML line keeps "To edit in MuseScore or another notation program" (the canvas said "or Dorico").
  - Acceptance: the Export menu with second lines (M7); MusicXML and the drum track through `NSSavePanel` with the core's names; the drum track's cost alert first; Open With… for the MusicXML; the bar with "Show in Finder" after saving, other notices in it.
  - Verify: tests up to the save panel's answer with a fake core; screenshots
  - Dependencies: 112 · Files: `mac/Stickler/`, tests, `po/*`

- [x] **Task 115: The PDF** (M): done 2026-11-18 (be56403, 26a7978; `mac` green: 16 app tests). Sheet Music (PDF)… writes the core's A4 pages: each SVG drawn by WebKit onto an A4 page (CSS-scaled, as the SVG has no viewBox), joined by PDFKit with the title. The PDF from CI holds `AAAAAD+Leipzig` and the tempo mark's text; Verovio already embeds a Leipzig subset in the SVG, the app's whole font (with its OFL licence) stays as a safeguard. The first run's failure was the test's: the groove fixture has no title.
  - Acceptance: `a4_pages` → each SVG rendered by WebKit, `createPDF`, joined with PDFKit, the title set; a test writes the PDF from a fixed reply: page count, A4 size, the tempo mark's text drawn (the Leipzig font: embedded or registered).
  - Verify: the test on `macos-26`; one PDF as artifact, compared with the GTK app's for the same song
  - Dependencies: 114 · Files: `mac/Stickler/`, tests

- [x] **Task 116: The Mac guide, the review and the owner's check** (S): the guide and the review done 2026-11-18; the owner's check on the Mac done 2026-11-19 ("Found at the owner's check" below, and checkpoint U). `docs/mac-development.md`: Homebrew, `uv`, `ffmpeg`, `git clone`, the artifact `Stickler.zip`, Open Anyway (and `xattr` when it is missing), choosing the folder, what to check. The fresh-context review of 107–115 found, each confirmed and fixed with a test where one fits (bd8ba09): quit was not bounded (a task group waits for its children; `send` ignored cancellation), now one deadline, then SIGTERM, then SIGKILL; Choose Stickler Folder… left the running core running, now it ends first; commands could reach the core out of order, now one sender; SIGPIPE ignored; the setup sheet keeps one identity; every button follows its `can_*` field; WebKit's process dying fails the PDF; an equal notice restarts its timer; CI fails without screenshots.
  - **Asked the owner (noted 2026-11-18); answered 2026-11-18:** 1. "Close Song" in both apps, no back button (done, see below). 2. As recommended: the app target's non-view files gated with `xccov` at 95 % (task 117). 3. The app icon comes with `mac-package`; the MusicXML line keeps the GTK text. 4. Open until the owner's check on the Mac.
    1. **Back to the empty window:** nothing in the app sends `close` (the review). After a result or a failed song, the drop area and the recent songs come back only with a new song or a restart; ⌘W closes the window and so quits the app. A "Close Song" item (File, ⌘W, and ⌘W on the empty window closes it)? The canvas's File menu has "Close Window" only.
    2. **Coverage of the app target:** SPEC scope 5 asks ≥ 95 % for "the app's models"; `SticklerCore` (where `AppModel` lives) is gated at 97.8 %, the app target (views and the AppKit glue: `Exports`, `Removal`, `SheetPDF`, `Panels`) is not measured. Gate its non-view files with `xccov`, or count it as views?
    3. **The canvas, differences:** the Export menu's MusicXML line keeps the GTK text "…or another notation program" (the canvas: "…or Dorico"); the macOS app icon of `mac-design` is not in the app yet (the consent sheet shows the generic icon): in `mac-shell` or with `mac-package`?
    4. **Screenshots:** the dark pictures of the main window show two white circles in the title bar; most likely the capture of macOS 26's glass, to be compared with the app on the Mac.
  - **Found at the owner's check on the Mac (2026-11-19):**
    1. **The core's `PATH`** (fixed 2026-11-19, owner; f7f1408, `mac` green on `claude/mac-shell`: 71 core tests on Linux and macOS, SticklerCore 98.12 %): an app started from the Finder has only the system's folders, so the core found neither `uv` for the models (the download failed) nor ffmpeg and ffprobe. `CoreClient.bridge` now gives the core `uv`'s folder and Homebrew's two prefixes in front of its `PATH` (`toolPath`, two tests; SPEC "Where the core is"). A build from before f7f1408 needs `open --env "PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH" Stickler.app`.
    2. **Mixed languages during the download** (fixed 2026-11-19, owner; 48e5499, `mac` green on `claude/mac-shell`: 72 core tests on Linux and macOS, SticklerCore 98.13 %; the owner saw German throughout in that build): the app's own texts were German, the core's English, for two reasons. The app passed `LANGUAGE=de-DE`, which Python's gettext does not read as `de`: `CoreClient.gettextLanguages` now writes `de_DE` and ends the list with `en` at the first English entry (a later language must not win over English, which has no catalogue). And nothing built `stickler.mo` on the Mac: `scripts/mo.sh` (msgfmt, as `scripts/gtk.sh` does for the GTK environment) builds them into `.venv/share/locale`, and the guide asks for `brew install gettext` and the script after `uv sync` and every `git pull`. Seen on the Mac: the bridge's `hello` says `de` for `de_DE:en` and `en` for the old `de-DE`. How the package gets its catalogues stays `mac-package`'s.
    3. **The PDF's tempo mark** (open, its own entry under "Later"): when a song starts with a multi-bar rest, the tempo mark runs into the rest's count above the staff: the owner's export of Apashe's "Majesty" (22 bars of rest, ♩ = 97) reads "= 9722". It comes from the core's engraving, so the sheet in both apps has it too.
    4. **The toolbar's two buttons** (owner, 2026-11-19: stays as it is): the canvas (M4) draws Open and Export in one capsule; the app has two toolbar items, so macOS gives each its own round glass, the system's default for a button beside a menu. These are also the white circles of the CI's dark screenshots (question 4 above): the capture paints the glass white.
  - Acceptance: `docs/mac-development.md` (Homebrew, `uv`, `ffmpeg`, `git clone`, the artifact, "Open Anyway" and the `xattr` fallback, choosing the folder, what to check); a fresh-context review of 107–115 against SPEC.md, its findings fixed or answered; the owner's check on the Mac.
  - Verify: the owner follows the guide and SPEC "mac-shell" success criteria 1–4
  - Dependencies: 113, 115 · Files: `docs/mac-development.md`
  - Close Song (owner, 2026-11-18), done: `session.shows_song` decides it for both apps; the bridge's `can_close` now holds only while a song is in the window (not on the setup screens). GTK: "Close Song" in the main menu (`win.close-song`), Ctrl+W closes the song, then the window. Mac: File › Close Song ⌘W, "Close Window" on the empty window. Texts in German and Spanish.

- [x] **Task 117: Coverage of the app target** (S) (owner, 2026-11-18: as recommended): done 2026-11-18 (57f1618, d3c2b0a, 20584d2; `mac` green: 31 app tests, the gate at 98.44 %). Everything the app asks the reader through AppKit goes through `Asking` (`mac/Stickler/Asking.swift`): `SystemAsking` with the real panels and alerts, `FakeAsking` in `LogicTests` (15 tests: each export, removal and panel flow up to the command the core gets, `PageLoad`'s failures). `scripts/xccov_gate.py` (Python tests) counts the functions of `Exports`, `Removal`, `Panels`, `SheetPDF` and `PageLoad` in xccov's report, closures included; `SystemAsking` and `RemovalQuestion` stay out, as `stickler_gtk/ui/` does. Uncovered: the missing-font branch of `SheetPDF.fontFace` and one `notDrawn` throw in `make`. The gate failing below 95 % is shown by its own tests with fixed reports, not by a CI run with a test removed. Two CI rounds went to a Swift 6 rule: the tests' wait needs an escaping closure across its awaits.
  - Acceptance: `mac.yml` measures the app target with `xccov` and fails below 95 % for its files that are not pure views (`Exports`, `Removal`, `SheetPDF`, `Panels`, `Commands`' logic); save and open panels and Open With behind a small protocol with a fake; CONSTRAINTS.md "Swift coverage" names the gate.
  - Verify: the `mac` workflow green; a deliberately removed test makes it fail once
  - Dependencies: 116 · Files: `.github/workflows/mac.yml`, `scripts/swift_coverage.py`, `mac/Stickler/`, `mac/SticklerTests/`, CONSTRAINTS.md

- [x] **Task 125: One rule for what each state allows** (S) (owner, 2026-11-18, from the graphify graph): done 2026-11-18. `session.abilities(state, *, installed, removing)` and `session.BUSY` (`controller.BUSY` is the same object); `bridge.can()` sends its fields, `Controller.can_remove_models` and `Window.show()` use it, so the rule for removing the models lives there too (the window had a third copy). The window judges by the state it shows, not the controller's newest one: a widget test that shows a setup state by hand caught the first version, which asked the controller. `tests/app/test_abilities.py`: every state kind against the table, the remove-models rule, the bridge equal to it; `docs/bridge.md` and both apps unchanged (268 app tests, 51 widget tests green).
  - Why: the GTK window decides in `Window.show()` (`src/stickler_gtk/ui/window.py`, the `set_enabled` calls) which actions fit a state; `stickler_app/bridge.py` `can()` holds the same rules a second time for the Mac app ("the GTK window's action rules"). Two copies can drift, and then GTK and the Mac enable different buttons. Only Close Song shares one rule today (`session.shows_song`). SPEC "Release 8": one shared core, two thin interfaces.
  - Acceptance: one function in the shared core (e.g. `session.abilities(state, *, remove_models)`) returns open, cancel, retry, close, export, agree, not now, retry setup and remove models for every state kind; `bridge.can()` encodes its result unchanged (`docs/bridge.md` unchanged); `Window.show()` enables its actions from it (result-only actions such as play and the bar steps follow `export`); a test checks every state kind against the table; no visible change in either app.
  - Verify: `uv run pytest -q tests/app` (the bridge's state tests unchanged and green); `scripts/gtk.sh test` (widget tests unchanged and green); `mac` workflow green
  - Dependencies: none · Files: `src/stickler_app/session.py`, `src/stickler_app/bridge.py`, `src/stickler_gtk/ui/window.py`, `tests/app/`

### Checkpoint U
- [x] All success criteria of SPEC.md "Module `mac-shell`" met (owner, 2026-11-19, checked on the owner's Mac with the CI's app: (1) it opens after "Open Anyway" (the app marked as a browser's download, which Gatekeeper rejected before), finds the checkout, asks for consent, downloads the models and turns a song into a result; Cancel works during the analysis and the download; (2) PDF, MusicXML and the drum track are saved (the MusicXML read with music21: 102 bars, every bar complete; the FLAC listened to), the PDF equals the GTK app's, "Show in Finder" shows the file; (3) the stopped page after `pkill`, "Start Again" works; (4) the screens match the canvas in light and dark, the toolbar's two buttons staying as the system draws them; German follows the system, the check in Spanish is put off by the owner ("Later"); "Remove Downloaded Models…" works and the next start downloads again. Three findings, two fixed: task 116); then `mac-sheet`'s spec

## Phase 22: Website (approved 2026-11-18, SPEC.md "Website")

- [x] **Task 118: The skeleton, the font and the site's test** (S): done 2026-11-18. Figtree 2.0.3 from `erikdkennedy/figtree` (OFL 1.1, commit 032dfa7, active), the variable font cut to 400–700 and Latin with German: one WOFF2 of 16 KB. `site/index.html` (navigation, hero, the later sections' anchors, footer), `site/style.css` (the mockup's tokens, light and dark, focus ring, skip link; the header sticky only from 48 rem, on a phone it took a quarter of the screen). `tests/test_site.py`: links and anchors, nothing loaded from elsewhere (HTML and CSS), only one script file, no inline script or handlers, `lang`, one `h1`, heading levels, skip link first, `alt`, named `nav`, viewport; each check seen failing once on a broken copy. Looked at with Playwright's Chromium (light, dark, 1280 and 390 px, Tab).
  - Acceptance: `site/index.html` with the navigation, an empty `main` with the skip link's target and the footer; `site/style.css` with the tokens of the mockup (light and dark through `prefers-color-scheme`, Apricot), `:focus-visible`, the skip link; Figtree 400/500/700 as WOFF2 subsets in `site/fonts/` with its OFL licence (source and version checked on the web, named in a comment); `tests/test_site.py`: local links and anchors resolve, no request leaves the site, one `h1`, headings do not skip, `lang` set, no `<script>` but the allowed one (`site.js`).
  - Verify: `uv run pytest -q tests/test_site.py`; `python3 -m http.server -d site` looked at light and dark
  - Dependencies: none · Files: `site/index.html`, `site/style.css`, `site/fonts/`, `tests/test_site.py`

- [x] **Task 119: The pictures, light and dark** (M): done 2026-11-18. `scripts/demo.py` takes `--dark`, `--video DIR`, `--stills DIR` and `--no-gif` (argparse; the old call records the README's GIF as before); `tests/test_demo.py` for the options, names and ffmpeg commands. Recorded on the laptop with `data/own/fluffing_a_duck` (Fast, about 30 s a run): `site/images/` holds sheet (bar 5 marked) and corrections in light and dark as PNG and WebP (38–48 KB each as WebP) and the overview as MP4 in both (94–101 KB, H.264, muted, faststart).
  - Acceptance: `scripts/demo.py` takes `--dark` (the app's dark style) and `--stills` (the sheet with a marked bar and the corrections sidebar as PNG, as `docs/screenshots`), and writes the overview also as MP4 (H.264, muted) with a poster frame; from one run each in light and dark: `site/images/` holds sheet, corrections and overview in both schemes, as WebP and PNG, the videos under the budget; `docs/screenshots/` keeps its files.
  - Verify: tests for the new options where they fit (argument handling, file names); the owner looks at the pictures; recording on the laptop with "Fluffing a Duck" (path from the owner) and the Fast models
  - Dependencies: none · Files: `scripts/demo.py`, `scripts/gtk.sh` (if an option passes through), `site/images/`, a test

- [x] **Task 120: The English page** (M): done 2026-11-18. Every section of the mockup with values from the README and `docs/bridge.md`; screenshots as `<picture>` with dark WebP sources; the overview as AV1 WebM and H.264 MP4 in light and dark (open-source Chromium has no H.264: seen in the first browser check, so `scripts/demo.py` writes both); a 20 s clip (Ogg Opus 174 KB, MP3 241 KB) with its CC BY credit and the change named; `site.js`: the copy button (hidden without script) and the video held still under reduced motion. Checked with Playwright's Chromium: light and dark at 1280 and 390 px, the copy button copies and announces it, the tab order follows the page, the video plays and stops under reduced motion (seeking to the sheet needs byte ranges, which GitHub Pages serves and `http.server` does not). The author's text came from the owner on 2026-11-18 (German \"Schlagzeuger, Nerd, Autor\", owner); the photo from the owner's shoot (LM108928, cropped as the owner showed, EXIF removed, 480 px, credited to Demian Pleuler under Thanks and licences); the Mac card has its text steps until `mac-package`.
  - Acceptance: the sections of SPEC "Website" 2–12 as in the mockup, with real values (numbers from the README's results, sizes from `docs/bridge.md`'s setup texts); every screenshot as `<picture>` with its dark source, `width`/`height`, `loading="lazy"` below the first view; the overview as `<video muted loop playsinline controls>` with light and dark sources and posters, not autoplaying under `prefers-reduced-motion`; a 20-second clip of "Fluffing a Duck" (Opus and MP3) in `<audio controls>` with its credit; `site.js` as the only script: the copy button and the video held still under reduced motion (the command stays selectable and the video pausable without it); "About the author" with the owner's text and photo (placeholders until the owner sends them); the Mac card with text steps until `mac-package`.
  - Verify: `tests/test_site.py` extended (every image has `alt`, `width`, `height`; the page under the budget); keyboard-only pass by Claude in the browser
  - Dependencies: 118, 119 · Files: `site/index.html`, `site/style.css`, `site/site.js`, `site/media/`, `tests/test_site.py`

### Checkpoint V
- [x] The English page in the browser, light and dark, phone width and laptop (owner, 2026-11-19, from the local server: nothing to object to)

- [x] **Task 121: German, about, privacy and 404** (M): done 2026-11-18. `site/de/` with the start page, about and privacy in German; `about.html` (the author's words as a placeholder, how it is made, thanks and licences) and `privacy.html` (the app: nothing sent, downloads from the package and model servers only after asking; the site: no cookies, nothing from other servers, GitHub Pages logs IP addresses, from GitHub's docs read 2026-11-18) in English; one `404.html` in both languages with root links, as GitHub Pages serves it for every missing path. The test compares each pair (ids, pictures, downloads, outside links, the links to each other). German texts say "ich" in the author's parts ("Über mich"), as the owner writes them. Seen with Playwright: German on a phone, about in dark.
  - Acceptance: `site/de/index.html` as the English page in German; `about.html` and `privacy.html` in both languages (privacy: the app sends nothing; the site sets no cookies; GitHub Pages logs IP addresses, linked to GitHub's statement); `404.html` in both; the language links with `hreflang` and `lang`; the test compares each pair (anchors, images, downloads, links).
  - Verify: `uv run pytest -q tests/test_site.py`; the owner reads the German text
  - Dependencies: 120 · Files: `site/de/`, `site/about.html`, `site/privacy.html`, `site/404.html`, `tests/test_site.py`

- [x] **Task 122: Meta, icons, policy, sitemap** (S): done 2026-11-18. Every page: the CSP as the first meta after the charset (only `'self'`; `script-src 'self'` covers `site.js` as a file, so no hash), the referrer policy, SVG and 32 px PNG favicons, a 180 px `apple-touch-icon`; every page but 404: a description (120–148 characters), `canonical` and `hreflang` (en, de, x-default) on `https://stickler.tshia.ng/`, Open Graph (`share.png`, 1200×630 from the light sheet, en_GB or de_DE) and a large Twitter card. `robots.txt` and `sitemap.xml` (six pages with their language pairs); 404 is `noindex`. Checked with Playwright: no console message, no failed request, Figtree loaded, on all six pages under the CSP.
  - Acceptance: per page `<title>`, description, `canonical`, `hreflang`, Open Graph title, description and image (a 1200×630 picture from the sheet, light); favicon (SVG and PNG) and `apple-touch-icon` from the app icon; the CSP meta (only `'self'`, the copy script by hash) and the referrer policy; `robots.txt` and `sitemap.xml`; the test checks each.
  - Verify: `uv run pytest -q tests/test_site.py`; the page shared in a messenger shows its card (owner)
  - Dependencies: 121 · Files: the `site/` pages, `site/images/`, `site/robots.txt`, `site/sitemap.xml`, `tests/test_site.py`

- [x] **Task 123: The workflow** (M): done 2026-11-20: `site.yml` green on every push since 2026-11-18 and on `main` and `v8`; the published release 8 deployed the site (run 44700567199). Built 2026-11-18. `scripts/site_release.py` (tested with a fixed release: the three packages found, the zsync not; links, sizes and the Flatpak's name filled in both languages, German sizes with a comma; a missing package keeps the release-page link and warns) and `scripts/site_axe.py` (serves the copy, Playwright 1.65.2's Chromium, axe-core 4.14.1 checked against npm's sha512, WCAG 2.0–2.2 A/AA, every page light and dark). Locally axe found one real issue, the Flatpak command's scrolling box out of a keyboard's reach: the command now wraps; then 0 violations, and a copy without one `alt` failed as it should. `site.yml`: tests, release fill, axe, Pages artifact; deploy only by hand (`deploy: true`) or a published release ≥ 8; actions pinned by SHA, checkout without persisted credentials (zizmor clean).
  - Acceptance: `scripts/site_release.py` fills the download cards (file names and sizes of the newest release, read with `gh` or the API) into a copy of `site/`, tested with a fixed release; `.github/workflows/site.yml`: on a push touching `site/` it runs the test, builds the copy, runs axe-core (pinned, Playwright) on every page in light and dark, uploads the Pages artifact; deploys only on a published release ≥ 8 or by hand (`workflow_dispatch`).
  - Verify: the workflow green on a push; axe-core with no WCAG 2.2 A/AA violation; a deliberate missing `alt` makes it fail once
  - Dependencies: 122 · Files: `scripts/site_release.py`, its test, `.github/workflows/site.yml`

- [x] **Task 124: The DNS guide, the review and the owner's check** (S): done 2026-11-20 (Checkpoint W). the domain set up by the owner 2026-11-20 and checked read-only the same day: `stickler.tshia.ng` is a CNAME to `niklastshiang.github.io`, the account's verification record for `tshia.ng` resolves, no CAA record, Pages builds from Actions with the custom domain `stickler.tshia.ng`, its certificate approved and HTTPS enforced, the `github-pages` environment allows `main` and the tag rule `v*`; the domain answers (HTTP redirects to HTTPS, 404 until the first deploy, which a published release 8 starts). The site went online with release 8 the same day (run 44700567199). Left: the owner's look at the published site (checkpoint W). Before: 2026-11-18, after the review (owner): a legal notice (`imprint.html`, en and de, linked from every footer and the 404 page) and a full privacy statement (controller, the app, the site on GitHub Pages under Art. 6(1)(f) GDPR, mail via mailbox.org under Art. 6(1)(a), rights under Art. 15–21 and 77), both from the owner's texts for tshia.ng, adapted to this host; the Claude sentence left out of "About the author" (owner). the guide and the review done 2026-11-18; left: the owner's check and the domain. `docs/website.md`: looking at and changing the site, recording the pictures, the local axe run, how it is published, the domain in seven steps (verify `tshia.ng`, Pages from Actions, the CNAME, the custom domain, HTTPS and CAA, the `v*` tag rule on the `github-pages` environment, publish). The fresh-context review of 118–123, each finding checked and fixed: the MP3 clip was ignored by `.gitignore` (`*.mp3`) and so missing from git, which would have failed every fresh checkout (now tracked, and a test fails for any file in `site/` git does not know); the Mac and Flatpak uninstall texts left the models behind (now Remove Downloaded Models… first, and the README's `flatpak uninstall --delete-data`); the privacy page did not name Hugging Face (Demucs); a release could not deploy past the environment's branch rule (the guide's step 6); menu and footer links are 44 px tall now; disk space on the page; the example screenshot lazy; German alt texts and every page's weight tested; placeholders stop a deploy; axe prints what it cannot decide. Following that print, the "Your computer" card's labels ran into their values in German: fixed (labels first, stacked on a phone). Not changed: the gallery links open the light picture also in dark (a link cannot follow the scheme without script); no GPU time (the apps run Fast on the CPU; SPEC item 6 says so now); the screenshots show the English app on the German page.
  - Acceptance: `docs/website.md`: verify `tshia.ng` in the GitHub account (TXT), the CNAME `stickler` → `niklastshiang.github.io`, the custom domain in the Pages settings, Enforce HTTPS, CAA if set; how to run and change the site; a fresh-context review of 118–123 against SPEC "Website" and WCAG 2.2 AA, findings fixed or answered.
  - Verify: the owner: keyboard only, a screen reader once (Orca or VoiceOver), phone and laptop, light and dark, both languages
  - Dependencies: 123 · Files: `docs/website.md`

- [x] **Task 130: The page "Installing on a Mac"** (S) (owner, 2026-11-19): done 2026-11-19 without pictures (owner: "can we not point to an official guide instead?"; SPEC "Website" content 9, `mac-package` scope 7 and success criterion 5 changed first): the four placeholders are gone, step 4 links Apple's guide "Open a Mac app from an unknown developer" (`support.apple.com/guide/mac-help/mh40616/mac`, the German page its `de-de` edition; both answered 200 on 2026-11-19), a test keeps one such link per page in the page's language, and nothing on the page stops a deploy any more. The German words are macOS 27's ("Fertig", "Dennoch öffnen": the owner's screenshots in the chat). Before: the page and its texts built 2026-11-19 (`site/install-mac.html`, `site/de/install-mac.html`: in short, five steps, the first start, the Terminal line with its copy button, removing; in the pair test, the sitemap and linked from the Mac card, which keeps one sentence); left: the four pictures (the image's window, the first message, Privacy & Security, the last question), each a placeholder that stops a deploy, to be taken on the owner's Mac with the `.dmg`, light and dark; then the wording of macOS's messages is checked against them (the page describes them and quotes only the buttons). Original entry: a page of its own with pictures on how to allow the installation, linked from the Mac card (SPEC "Website", content 9).
  - Acceptance: `site/install-mac.html` and `site/de/install-mac.html`: the steps from the `.dmg` to the first start, each with its picture in light and dark (`<picture>`, alt texts in both languages), "Open Anyway" in System Settings and the `xattr` line as the fallback; linked from the Mac card and the sitemap; the pair test, the page-weight test and axe cover it.
  - Verify: `uv run pytest -q tests/test_site.py`; `scripts/site_axe.py`; the owner follows it on a Mac
  - Dependencies: `mac-package` (the `.dmg` the pictures show); the page and its texts can be built before, with placeholders that stop a deploy · Files: `site/`, `site/images/`, `tests/test_site.py`, `docs/website.md`

### Checkpoint W
- [x] SPEC "Website" success criteria met (owner, 2026-11-20: checked the published site); 3 and 5 came with release 8 (the `.dmg` and its pictures from `mac-package`)

## Phase 23: Release 8 (macOS app), module `mac-sheet` (approved 2026-11-18, SPEC.md "Module `mac-sheet`")

Task 126 starts at once (owner, 2026-11-18: Linux only, no view); 127–129 after checkpoint U (the owner's check of `mac-shell` on the Mac; met 2026-11-19).

- [x] **Task 126: The sheet's model in SticklerCore** (M): done 2026-11-18. `SheetModel` (owned by `AppModel` as `sheet`): the note size from `settings` at every core start; `pages` without `zoom` (the stored size) when a result's music changes (song, MusicXML or corrections; an export and the `correcting` flag do not), when the width changes (the first at once, later ones after 0.3 s), and after every zoom reply; each request numbered, a reply overtaken by a newer one, another screen or a new core is dropped; refusals go to the window's notice. 12 tests in `SheetModelTests.swift` against `FakeCore`, which can now delay a reply (`queue`); `SheetModel.swift` at 100 %. The reader's-command tests ignore the sheet's `settings`, which runs beside them.
  - Acceptance: the model reads the note size and percent from `settings` at start; asks for `pages` of the shown result at the sheet's width when a result arrives (a song or a correction), when the width has settled for 0.3 s, and after every zoom reply; `zoomIn`, `zoomOut`, `actualSize` and `setZoom` send their commands and keep the reply's size; a reply overtaken by a newer request is dropped; while pages are on their way the old ones stay; a refused `pages` keeps them and shows the core's message as a notice.
  - Verify: `swift test` in `mac/SticklerCore` on Linux (WSL) and in the `mac` workflow, coverage ≥ 95 %; a test sends five widths within 0.3 s and sees one `pages` request
  - Dependencies: none (owner, 2026-11-18) · Files: `mac/SticklerCore/Sources/SticklerCore/` (the model, `Command`), its tests

- [x] **Task 127: The sheet in the window** (M): done 2026-11-19 (4a44b16, `mac` green on all three jobs; the M6 screenshots show the groove with its tempo mark in light and dark); the look at the build on the Mac is part of task 129's check. `SheetHTML` (the pages on the desk with 12 points around them as in GTK, each at its engraved width, the canvas's shadow, the paper inverted in dark mode, no script), `SheetView` with a `WKWebView` (`SheetWebView`: JavaScript off, tells its width, takes no keyboard focus, no context menu, the page loaded again when WebKit's process dies), instead of `ResultPlaceholder`, whose text left `po/`. VoiceOver reads one image, "Sheet music of {title}, {count} page(s)": both texts are in `po/` with German and Spanish already (the plural through `mac_texts.PLURALS`), so task 128 has only the three menu items left. `SheetTests` (10 tests) and the M6 screenshot from `Fixtures/pages.json` (the groove at 876 pixels); `SheetHTML` in `scripts/xccov_gate.py` and CONSTRAINTS.md. The screenshots' wait sleeps instead of turning the run loop, which starved the model's tasks. Checked on the Mac without Xcode: the app module and all test files compile (Swift 6, the two `@State` lines replaced), `SheetTests` and three screenshot tests pass against a stand-in for XCTest, SwiftLint is clean; the owner's "Majesty" renders in light and dark. The scroll position, lost at first when the pages were laid out again, is kept since 81f5f34 (task 128).
  - Acceptance: `SheetHTML` builds the page for the web view from the pages and the appearance (the pages one under the other on M6's grey desk, each white with the canvas's soft shadow `0 1px 3px`, inverted in dark mode, no script); a `WKWebView` (`NSViewRepresentable`, JavaScript off) shows it, scrolling vertically only, and reports its width in points to the model; it replaces `ResultPlaceholder`; VoiceOver reads it as one image labelled with the title and the page count.
  - Verify: `LogicTests` for `SheetHTML` (no `<script>`, inversion only in dark, pages in order) under `scripts/xccov_gate.py` with `SheetHTML` added; screenshots of M6 light and dark from a fixed `pages` reply (the groove of `tests/app/fakes.py`) compared with the canvas
  - Dependencies: 126, checkpoint U · Files: `mac/Stickler/` (the sheet view, `SheetHTML`, `ContentView.swift`, `Pages.swift`), `mac/SticklerTests/`, `scripts/xccov_gate.py`

- [x] **Task 128: Note size from the View menu and a pinch** (S): done 2026-11-19 (feb0111, 5968b56, 81f5f34; `mac` green on all three jobs at the first try each). `ZoomMenu` (three items with ⌘+, ⌘−, ⌘0, enabled with a shown result; counted by `scripts/xccov_gate.py` and named in CONSTRAINTS.md) drawn by `ZoomItems` before the View menu's system items. The pinch: `Pinch` in `SticklerCore` gathers the gesture's steps and gives one scale when the fingers lift, `SheetWebView.magnify` feeds it, `SheetModel.pinched(by:)` sets the shown size times that scale (the core keeps it within 0.5–3). "Actual Size" is new in `po/` (German "Originalgröße", Spanish "Tamaño real", macOS's own words); "Zoom In" and "Zoom Out" were the GTK app's already. Added, as task 127 left it open: `SheetLoad` reads how far down the reader was before a new page is loaded and scrolls the new one as far down (the app's own script through `callAsyncJavaScript`; the page's scripts stay off), tested with a real web view in CI (a page twice as high is scrolled twice as far). Not done: the notes do not follow the fingers during a pinch, as the GTK sheet does by scaling its picture; they change once, when the fingers lift. To be judged on the Mac.
  - Acceptance: View › Zoom In ⌘+, Zoom Out ⌘−, Actual Size ⌘0, enabled only with a result; a trackpad pinch on the sheet sends one `set_zoom` once the fingers rest; "Zoom In", "Zoom Out", "Actual Size" and the VoiceOver label in `po/` with German and Spanish, and in the String Catalog.
  - Verify: tests for the menu's state and the commands with a scripted core; `uv run pytest -q tests/test_xcstrings.py tests/app/test_mac_texts.py`; by hand on the Mac: the size is kept for the next song and start
  - Dependencies: 127 · Files: `mac/Stickler/Commands.swift`, the sheet view, `src/stickler_app/mac_texts.py`, `po/*`, `mac/Stickler/Localizable.xcstrings`

- [x] **Task 129: Review and the owner's check** (S): the review and the guide done 2026-11-19 (9c5980e, `mac` green: 78 core tests, SticklerCore 98.18 %, the app's logic 98.85 %); the owner's check on the Mac done 2026-11-19 ("Found at the owner's check" below, on macOS 27.0.1, and checkpoint X). The fresh-context review of 126–128 found, each confirmed (the first two with a test that failed before) and fixed: the stored note size was dropped at every real start, because the core's first state arrived before the `settings` reply and the guard counted page requests (now it asks whether the core is the same); during a drum track's export the zoom items stayed on and `pages` was asked for, which the core refuses then, leaving the sheet at the old size (now off, and a width changed meanwhile is asked for when the result is back); a song dropped on the sheet would have gone to the web view (suspected by the review, not seen on a Mac: it takes no dropped files now, and shows only the app's own page); the page's Content-Security-Policy lets it fetch nothing (the M6 screenshots still show the embedded font); of two pages asked for while one loads, only the newer is loaded.
  - **Answered, not changed** (minor, for the owner to weigh): the scroll position starts at the top again after a drum track's export (the sheet's view is rebuilt); a pinch right after ⌘+, before the core answered, multiplies the size from before; after a resize during an analysis the next song may be engraved twice (the old width, then the new one after 0.3 s).
  - **Only a Mac can tell:** whether VoiceOver reads the sheet as one picture with its label (the review: if SwiftUI's label does not take on the web view, it reads nothing); the pinch itself; ⌘+ on the owner's keyboard layout; a song dropped on the sheet opens.
  - **Found at the owner's check on the Mac (2026-11-19, the build of `main` 4d9bd55):** a song dropped on the sheet opens; ⌘+, ⌘− and ⌘0 work on the owner's keyboard.
    1. **Scrolling is not fluent** (closed, nothing changed; the owner looked again the same day: "scrolling is fluent"): the Mac was in Low Power Mode (battery 13 %), where WebKit draws a page 30 times a second. Measured with the app's `SheetWeb` in a test program on this Mac (Sunlight, Skyfall and Majesty at 976 points, light): every frame of a scripted scroll took 33.3 ms, with the shadow, without it, as a layer of its own and as an image alike, and also when the whole view was drawn anew for every frame, so drawing the notes is not the limit. The owner looks again without Low Power Mode, and beside Safari on a long page.
    2. **The pinch does not follow the fingers** (owner: "the zoom is not fluent"; SPEC scope 3 changed first; aff2e4f, `mac` green on all four jobs; the owner on the build of 0291ea6, 2026-11-19: the pinch follows the fingers, "passt"): `Pinch.soFar` tells the scale while the fingers move; `SheetWebView` draws the shown pages at that scale around the point the pinch began at (a CSS transform set by the app's own script, limited to 0.2–5; the note size's limits stay the core's) and keeps the picture after the fingers lift until its pages come. New pages now replace the old ones in the loaded document (`SheetHTML.Content`: the styles and the sheets; `SheetLoad` loads the document once) in one script that also ends the picture and scrolls to the reader's place: before, every new size loaded the page again and scrolled afterwards (seen in the test program: `scrollY` 0 for a moment after each load). A picture no pages follow is taken back: at once after a cancelled pinch, one that changed nothing, or the core's answer with the pages already shown; after 1.5 s when the core refused. The document is `document()`'s as before, byte for byte. Checked on this Mac without Xcode: `SticklerCore` 82 tests (`swift test`); the app's sources type-check in Swift 6 but for the two `@State` lines; `SheetTests` and the new `SheetLoadTests` pass against a stand-in for XCTest (19 of their 20 tests, 5 with a real web view in a window; the label's test needs the app's string catalogue), and two of them fail when the picture is not ended with the pages or pages that came during the load are dropped; each step of a pinch's picture is on screen in the next frame with the real sheet music, light and dark. Not done: a second pinch begun before the first one's pages came starts from the picture those pages replace.
    3. **VoiceOver reads nothing on the sheet** (closed, nothing changed; the owner tried again with VoiceOver's own keys and counts it and dark mode as met, 2026-11-19): the running app's accessibility tree, read from outside through the AX API, has one `AXImage` "Noten von Sunlight, 1 Seite" over the whole sheet (640 × 480), and a hit test at three points of the sheet finds it; no web content is below it. The sheet takes no keyboard focus (SPEC scope 4), so Tab does not lead VoiceOver there: the owner tries again with VoiceOver's own keys (⌃⌥→ from the toolbar).
    4. **The Export menu has no name for VoiceOver** (fixed: 0291ea6, `mac` green on all four jobs, and the tree of that build running on the owner's Mac says "Exportieren"; seen in the same tree): its menu button's title was `chevron.pulldown` and its description empty (only the help text "Exportieren"); the Open button beside it is described ("Öffnen …"). Reproduced with a small copy of the toolbar: the name is the arrow's when the program is linked as the app is (SDK 26.5, the CI's Xcode 26.6) and runs on this Mac's macOS 27; linked with the SDK 27.2 it is "Export". `.accessibilityLabel(Text("Export"))` on the menu gives "Export" in both; `Menu("Export", systemImage:)` does not help.
  - Acceptance: a fresh-context review of 126–128 against SPEC "mac-sheet", findings fixed or answered; `docs/mac-development.md` says what to check for the sheet.
  - Verify: the owner on the Mac: Eye of the Tiger at 800 and 1600 points wide, ⌘+/⌘−/⌘0 and a pinch, dark mode, VoiceOver's label (SPEC "mac-sheet" success criteria 1–3)
  - Dependencies: 128 · Files: `docs/mac-development.md`

### Checkpoint X
- [x] All success criteria of SPEC.md "Module `mac-sheet`" met (owner, 2026-11-19, checked on the owner's Mac with the CI's app of 0291ea6: the sheet, ⌘+/⌘−/⌘0 and the pinch that follows the fingers, a dropped song, scrolling, VoiceOver with its own keys and dark mode; "Ja, erfüllt"); `mac-package`'s spec is approved already

## Phase 24: Release 8 (macOS app), module `mac-package` (approved 2026-11-19, SPEC.md "Module `mac-package`")

- [x] **Task 131: The spike** (M): built 2026-11-19 (4aa2b79; the run `mac-spike` 44499521895 green at the first try); the owner's check on the Mac done 2026-11-19 (below), its three answers are in SPEC.md (scope 1): yes to all three. Measured on the runner: the image 66.5 MB (the app 160 MB unpacked: Python 3.14.10 with numpy, Verovio, PyYAML and mido 120 MB, `uv` 27 MB, ffmpeg 3.7 MB, ffprobe 3.5 MB, the adapters' sources and translations 1.2 MB); ffmpeg 9.0.2 builds from source in 91 s (LGPL, audio only) and reads MP3, FLAC, WAV, Ogg Vorbis, Opus, AIFF and M4A clips; the image keeps the helpers' executable bits; the app copied out of the image passes `codesign --verify --strict`, and its core, started as the app starts it (a `PATH` of the bundle and the system only, an empty home), says `hello` in German and answers `settings`, writing nothing into the app. Not tried in CI: a model's setup through the bundled `uv` (the owner's check). Not in the spike's app: the licences of what it ships, the app icon; `msgfmt` comes from the runner's Homebrew (task 132 pins or replaces it); Python's 120 MB are unpruned (pip, tkinter and the test suites are in it).
  - **Newer build (2026-11-19, run 44507367954, with tasks 132 and 133):** the image is 55.9 MB; take this one for the check.
  - **The owner's check (2026-11-19, the image of run 44507367954, on macOS 27.0.1; the guide asks for 26):** "the spike image works", and started straight from the mounted image it "ran too". Seen on the Mac afterwards: the app copied from the image is in `/Applications`, passes `codesign --verify --strict`, and its `uv`, ffmpeg and ffprobe kept their executable bits; at 17:56 a Python 3.14.10 was fetched into `~/Library/Application Support/Stickler/python`, at 17:58 the environments of ADTOF and Beat This! were made anew, at 17:59 a new song had its score. The app started once more for a look at its core: `…/Resources/core/python/bin/python3 -I -B -m stickler_app.bridge` with `PATH=/Applications/Stickler.app/Contents/Resources/core/bin:/usr/bin:/bin:/usr/sbin:/sbin`, so the setup went through the bundled `uv` (no other is on that path). Nothing found that changes the bundle. Not tried: macOS 26.
  - **For the owner:** Actions › mac-spike › the newest run › artifact **Stickler-spike** (a zip with `Stickler-spike.dmg`). Open the image, drag Stickler to Applications, open it, then System Settings › Privacy & Security › Open Anyway. It must not ask "Where Is Stickler?". Then the consent, the download, a song. Also once: open the app straight from the mounted image or from Downloads, without dragging it. If the download of the models fails or "Stickler Stopped Unexpectedly" shows, the technical details are what is needed.
  - Acceptance: a workflow run by hand (`mac-spike.yml`, removed again in 136) builds an ad-hoc signed `Stickler.app` with `bin/uv`, a pinned relocatable Python with the core's wheels, the core, the adapters' sources and ffmpeg/ffprobe built from the pinned source, each helper signed, in a plain `.dmg`; the job's summary gives the image's size, each part's size and the ffmpeg build's minutes; the job mounts the image, copies the app out and has its core answer `hello`. The app in it starts the bundled core (a switch only the spike sets; the folder question stays for everyone else).
  - Verify: the owner on the Mac: download, drag, Open Anyway, the consent, the download, a song to its sheet music; once started straight from Downloads; the technical details show the core's `PATH`
  - Dependencies: none; it runs before checkpoint X (owner, 2026-11-19) · Files: `.github/workflows/mac-spike.yml`, `scripts/mac_bundle.sh`, `mac/SticklerCore/Sources/SticklerCore/CoreClient+Bridge.swift`

### Checkpoint Y
- [x] The spike's three answers are in SPEC.md; the spec is changed where they ask for it; the owner approves going on (owner, 2026-11-19: yes to all three, so the spec stays as it is; "Ja, freigeben")

- [x] **Task 132: The bundle, built by one script** (M): done 2026-11-19: built ahead of checkpoint Y (owner: "we bring 132 and 133 forward"; 4a3d49d and the fix after it; the spike's run 44507367954 green), and the owner's check of the spike found nothing that changes the bundle (task 131). `scripts/mac_bundle_tools.py`, run by `mac_bundle.sh` with the app's own Python: `mo` writes the gettext catalogues without msgfmt (every translated entry of `po/` read back through `gettext`, plurals too; the runner's Homebrew is out), `prune` drops the test suites, IDLE, Tk, pip, headers and numpy's tests (Python 120 → 91 MB; the image 66.5 → 55.9 MB; the core still says `hello` and engraves a page from the image), `licenses` collects each wheel's licence files, Python's, uv's two (fetched at the version, pinned) and ffmpeg's into `core/licenses/` with an index and stops for a package without one, `check` fails the build for a missing part, a helper that cannot run, or an environment, weights, a cache or pip inside. `uv` is 0.13.9 in the AppImage and the Flatpak too (a test keeps the three equal; `release.yml` run by hand: both Linux packages build). Two mistakes of the first run, fixed: the check asked for a file the repository never had (a test now compares its names with the repository), and the spike's step went on after its script had failed (`| tee` without pipefail; the job's shell is `bash` now). Left for 134: the licences linked from the Help menu (SPEC scope 2).
  - Acceptance: `scripts/mac_bundle.sh <app>` fills `Contents/Resources/core/` as SPEC scope 2 says: every download pinned by version and SHA-256, the wheels from `uv.lock` with their hashes, the `.mo` files from `po/`, the licences collected; no environment, weight or cache inside (a test lists the bundle); `uv` at one version in both packages.
  - Verify: the script on the runner; `uv run pytest -q tests/test_mac_bundle.py` (the pins, the file list from a made-up tree)
  - Dependencies: checkpoint Y · Files: `scripts/mac_bundle.sh`, `tests/test_mac_bundle.py`, `scripts/appimage.sh` (uv's version)

- [x] **Task 133: ffmpeg and ffprobe from source** (S): done 2026-11-19 ahead of checkpoint Y (owner; 4a3d49d, `mac` green with the new job `ffmpeg`). `mac.yml` builds ffmpeg 9.0.2 once per version of `scripts/mac_ffmpeg.sh` (and of its test), tries it with `scripts/mac_ffmpeg_test.sh` on a 2 s clip of MP3, M4A, FLAC, WAV, Ogg Vorbis, Opus and AIFF (to FLAC, to raw samples at 22050 Hz, the length and channels by ffprobe, the drum track's WAV and FLAC, a song's tags; nothing but the two programs and the system on the `PATH`) and caches the build only when that passed; the spike takes it from the same cache. 3.7 MB and 3.5 MB, LGPL 2.1 or later, its licence text beside them. Not done: the source's signature (`.asc`) is not checked, only its SHA-256, taken on 2026-11-19 from ffmpeg.org through this machine's proxy.
  - Acceptance: the pinned ffmpeg source built audio-only for arm64 with the decoders and demuxers of `paths.AUDIO_SUFFIXES`, FLAC and WAV out; a test on the runner converts one clip of each promised format and reads its length with ffprobe; the build is cached by the source's checksum and the configuration; the licence text shipped.
  - Verify: the runner's job; the two programs' size in the summary
  - Dependencies: 132 · Files: `scripts/mac_ffmpeg.sh`, `.github/workflows/mac.yml`

- [x] **Task 134: The app starts its own core** (M): done 2026-11-19 (5abbdc1). `mac` green on all four jobs at the second try (run 44579358468; at the first, GitHub found no macOS runner for the job `app` in 15 minutes and cancelled it, nothing of ours had run): the app's tests pass, its logic is covered at 98.88 %, the screenshots are without M0, and `stopped-incomplete` shows the five missing parts with the details unfolded. `mac-spike` green too (run 44579372867, the image 55.9 MB, its core started from the image). Left for the owner on the Mac, with that image: no folder question, Help › Licences opens the folder, a song to its sheet music; and on the bare `Stickler.zip`, folding and unfolding "Technical Details" (no test clicks it). `CoreClient.app` starts the core in `Bundle.main`'s `core` (a `PATH` of the bundle's `bin` and the system's folders); only a build for debugging reads `STICKLER_CHECKOUT` and then runs `uv run stickler-bridge` there with the `PATH` it was started with. Before each start the client looks for the bundle's Python, `uv`, ffmpeg, ffprobe and the adapters' folder: with one missing or not executable, "Stickler Stopped Unexpectedly" names it, its technical details unfolded (the screenshot `stopped-incomplete`). `AppModel` has no folder, no search for `uv` and a phase `launching` before the core starts; the remembered `SticklerFolder` is removed at launch. The folder page, File › "Choose Stickler Folder…" and their five texts are gone from the app and `po/`; Help › "Licences" (new text, German and Spanish) opens `core/licenses`, greyed out in a build without its core. `docs/mac-development.md` is rewritten (the image; a development build with Xcode). A fresh-context review found no blocking finding (the app's sources type-check against the macOS 26.5 SDK of the Command Line Tools, for debugging and for release); its notes are fixed (the screenshot class's length, a test's name and wait, three comments, the spec's sentence on what the client sets). Locally: `swift test` in `mac/SticklerCore` 87 passed (a made-up bundle whose Python is a shell script shows the command line, folder and environment it gets), `scripts/check.sh task` green. Consequences: the bare `Stickler.app` of the `mac` workflow no longer runs from the Finder (it has no core; it says so), so until task 136 the check on the Mac uses the image of `mac-spike`; the owner's Mac has no Xcode, so no development build there. Not done: the page's sentence ("The part of Stickler that listens to the songs has ended …") is the same for a core that never started; `scripts/i18n.sh` does not run on this Mac (bash 3.2 has no `mapfile`, BSD `sed -i`), its steps were run by hand.
  - Acceptance: `CoreClient` starts the bundled core from `Bundle.main` with the environment of SPEC scope 3 (a `PATH` of the bundle's `bin` and the system's folders); "Where Is Stickler?", "Choose Stickler Folder…" and the search for `uv` are gone, their texts leave `po/`; a development build takes the checkout from `STICKLER_CHECKOUT`; a missing or broken bundle shows "Stickler Stopped Unexpectedly" with what is missing.
  - Verify: `swift test` (the command line and environment from a made-up bundle, on Linux and macOS); the app's tests; screenshots without M0
  - Dependencies: 132 · Files: `mac/SticklerCore/`, `mac/Stickler/`, `src/stickler_app/mac_texts.py`, `po/*`, `docs/mac-development.md`

- [x] **Task 135: The icon and the version** (S): done 2026-11-19 (53083b0; `mac` green on all three jobs, the consent sheet's screenshot shows the icon). `scripts/mac_icon.py` puts the GTK icon's four layers on the design board's shape (a rounded square of 824 in 1024, #2f5d8c) as `packaging/icons/ng.tshia.Stickler-macos.svg` and draws the icon set's seven pictures with librsvg (the GTK environment; kept in git, as neither CI nor the Mac build can draw SVG); a test fails when the GTK icon changes without it. The app's version is the project's (7 until release 8 raises both; a test keeps them equal), where `project.yml` said 8 already. Not done: the dark variant of `mac-design` (#1c1c1e). An icon set has no dark slot for a Mac app that the sources found on 2026-11-19 confirm; macOS 26's own format (Icon Composer's `.icon`) holds one but is made with Apple's tool on a Mac. To see on the Mac: whether macOS 26 shows the icon as drawn or inside its own frame.
  - Acceptance: the macOS icon of `mac-design` in the app (the consent sheet and the Dock show it); About shows the release number; a test keeps `mac/project.yml` and `pyproject.toml` at the same version.
  - Verify: the test; the screenshot of the consent sheet
  - Dependencies: none · Files: `mac/Stickler/Assets.xcassets`, `mac/project.yml`, `tests/`

- [x] **Task 136: The image in the release** (M): done 2026-11-20 with release 8 (the tag's run 44699332411 attached the three packages to the draft). Before, left only the draft release with the three packages, which needs the tag `v8` (release 8); the newest manual run is 44610956957 (59bd1a2, green; its image is the one the owner checked at checkpoint Z). Built 2026-11-19 (9f0f8ad); `release` run by hand on `claude/mac-shell` green at the first try (run 44581602607: Flatpak, AppImage and `mac`; the job `mac` took 3 min, ffmpeg built and tried in 78 s; 27 Mach-O files of the core signed one by one, then the app; the core said `hello` in German from the image and from the copied app and engraved a page; the artifact `mac` holds `Stickler-7.dmg`, 55.6 MB). Not yet: the draft release with the three packages (it needs the tag `v8`, release 8) and the owner's look at this image. `release.yml` has a job `mac` on `macos-26`, taken from the spike's workflow: XcodeGen and the Release build, ffmpeg and ffprobe built anew from the pinned source and tried on every format (not from `mac.yml`'s cache: zizmor's `cache-poisoning` on a workflow that publishes; about three minutes more), `scripts/mac_bundle.sh`, then every Mach-O file of the core signed ad hoc on its own (found by `file`; `uv`, ffmpeg, ffprobe and Python verified one by one) and the app last, `codesign --verify --strict`, a plain image `Stickler-<version>.dmg` (the app and the link to `/Applications`), the start test from the mounted image (the core says `hello` in German once straight from the read-only image and once from the app copied out, engraves one page, writes nothing into the app; the helpers keep their executable bits and signatures), the artifact `mac`. The job `attach` waits for it too and uploads the three packages with `gh release upload`. `mac.yml` keeps its Release build as a check but uploads no app; `mac-spike.yml` is removed. Every action in `release.yml` and `mac.yml` is pinned by SHA (checked against the tags on 2026-11-19), every checkout without persisted credentials: zizmor 1.32.0 finds nothing in the two. Afterwards (owner) `check.yml` and `models-macos.yml` pinned the same way: zizmor finds nothing in any workflow. The signing loop tried locally on a made-up folder; the steps' shell passes `bash -n` and shellcheck 0.11.0. `docs/mac-development.md` and SPEC.md (scope 6, the file list) say where the image comes from now. The `mac` workflow for 5abbdc1 (task 134) was still queued when this was built.
  - **For the owner:** Actions › release › Run workflow › the branch `claude/mac-shell`; after about ten minutes the run's artifact **mac** is a zip with `Stickler-7.dmg` (the newest: run 44581602607). The spike's workflow and its artifact are gone.
  - Acceptance: `release.yml` has a `mac` job: build, the bundle, each helper and then the app signed ad hoc, `codesign --verify --strict`, a plain image with the Applications link, the start test from the mounted image (`hello`, one engraved page, no models), `Stickler-<version>.dmg` attached by `gh release upload`; a manual run keeps it as an artifact; `mac.yml` stops uploading the bare app; the spike's workflow is removed; actions pinned by SHA (zizmor clean).
  - Verify: a manual run; a draft release with the three packages
  - Dependencies: 133, 134, 135 · Files: `.github/workflows/release.yml`, `.github/workflows/mac.yml`

- [x] **Task 137: The guide, the review and the owner's check** (S): done 2026-11-20. The guide and the review done 2026-11-19 (2c18f4b, 78c882e, 3b3d510, 2b4edef, 39f41aa, e44f5d9 and the entry's commit), pushed up to 59bd1a2: `mac` green on all four jobs (run 44609834944, after one SwiftLint fix: `CoreClient` was over 250 lines), `site` green (run 44587708865), `release` run by hand green on all three packages (run 44610956957: the image 55.4 MB, numpy's 17 licence files in place); the owner's check on the Mac with that image done 2026-11-20 (macOS 27.2.1; checkpoint Z). Before, left: the owner's check and the pictures. `docs/install-macos.md` (the website page's five steps, the first start, the Terminal line, removing, where the files are) and the README's Mac part; a test keeps the guide's steps and Terminal line equal to `site/install-mac.html`'s. `docs/mac-development.md` leads to it and says what to check at checkpoint Z. The German page's words are macOS 27's ("Fertig", "Dennoch öffnen"; the owner's screenshots, 2026-11-19).
  - **The fresh-context review of 131–136, each finding checked, fixed with a test where one fits:** (1) licence files of the same name replaced each other: the spike's app shipped lapack_lite's text as numpy's `LICENSE.txt` (seen in `/Applications/Stickler.app`); each file keeps its place now, numpy's 17 files in 17 places. (2) The drum track's save panel took any ending while the app's ffmpeg writes FLAC and WAV only: the panel allows these two. (3) Removing left macOS's own files: on the owner's Mac `~/Library/WebKit/ng.tshia.Stickler`, `~/Library/Caches/ng.tshia.Stickler` and `~/Library/Preferences/ng.tshia.Stickler.plist`; the sheet's web view keeps nothing on disk now, the other two are the question below. (4) The packaged core inherited the app's environment: it is started without `UV_*`, `XDG_*`, `STICKLER_*`, `PYTHON*` and `VIRTUAL_ENV`; a proxy stays, a development build keeps everything. (8) The release job verified four of the 27 signed files: each one is verified after it is signed. Words that the code contradicted: the bundle script's note on signatures, SPEC's place of the adapters (`core/python/share/…`).
  - **Answered, not changed:** (5) an app folder with ":" in its path (the Finder's "/") loses the bundle's `bin` from `PATH`, as a `PATH` cannot hold such a folder; the stopped page would not name it. (6) Whether the Python build's own statically linked libraries (OpenSSL, SQLite, xz, libffi) need their licence texts beside Python's, and `uv`'s third-party notices: not looked up; the font's `OFL.txt` is in the app's resources, not under Help › Licences. (7) The release job's start test runs the core by hand with `env -i`, not the app's binary; the app's own start is covered by the Swift tests with a made-up bundle and by the owner. (9) A core that starts but never says `hello` leaves the empty window without the stopped page. `HF_HOME` and `TORCH_HOME` still reach the models when the reader has set them. Task 133's "the spike takes it from the same cache" no longer holds: nothing reads `mac.yml`'s ffmpeg cache since the spike's workflow is gone.
  - **Decided by the owner (2026-11-19: "Ja, sehe ich auch so") and built, not yet checked by the `mac` workflow:** success criterion 3 could not hold as written, as macOS itself keeps `Preferences/ng.tshia.Stickler.plist` (the window's place) and `Caches/ng.tshia.Stickler`. "Remove Downloaded Models…" with everything now removes what macOS keeps for the app by its identifier (`Leftovers`: preferences, caches, WebKit, HTTP storage, saved windows), at once and once more when the app quits; SPEC says so. Only the owner's `find` after quitting can tell whether macOS writes the preferences again after that. Also seen, not changed: `SticklerCore`'s tests leave a `stickler-test-<UUID>.plist` in `~/Library/Preferences` per run (296 on this Mac).
  - Acceptance: `docs/install-macos.md` and the README's install section (download, drag, Open Anyway as Apple's guide has it, the first start, removing); `docs/mac-development.md` for the development build; a fresh-context review of 131–136 against SPEC.md, its findings fixed or answered; the pictures for the guide and the website taken by the owner (task 130).
  - Verify: the owner: SPEC "mac-package" success criteria 1–5
  - Dependencies: 136 · Files: `docs/install-macos.md`, `README.md`, `docs/mac-development.md`

### Checkpoint Z
- [x] All success criteria of SPEC.md "Module `mac-package`" met (owner, 2026-11-20: "Checkpoint Z ist erfüllt"; checked on the owner's Mac, macOS 27.2.1, with `Stickler-7.dmg` of the manual release run 44610956957, put into Downloads with the quarantine mark a browser sets); then release 8

### Release 8
- [x] Prepared and committed as "Release 8" (2026-11-20; ADR 0006): no open Dependabot alerts; version 8 in `pyproject.toml`, `src/stickler/__init__.py`, `mac/project.yml` and `uv.lock`; the MetaInfo's `<release>` and `CITATION.cff` dated 2026-11-20 (change both if the tag comes on another day); README, `docs/requirements.md` and `docs/bridge.md` name the Mac app; SPEC's statuses of release 7, release 8 and the five Mac modules are done.
- [x] **Two figures that only the owner's Linux computer has** (both done; the Mac's token counts recorded 2026-11-20, used 2026-11-22) (owner, 2026-11-20: committed without them, kept as a todo):
  - [x] The AI cost (2026-11-20, owner: costs only): the README's table and the badge `origin-ai-cost` say about 447 USD, this computer's logs up to the release (347 USD) plus the Mac's (100 USD, by cost only). Left: the badge `origin-tokens` and the Mac rows' token columns, which need `uv run python scripts/ai_usage.py` on the Mac. Before: `uv run python scripts/ai_usage.py` there (the sessions of 17–19 November) together with this Mac's logs (from 19 November 05:42, about 100 USD: Fable 5.2 86.53, Opus 5.5 13.60 on 2026-11-20). `scripts/badges.py` on one machine alone counts only its own logs: on the Mac it gave about 100 USD instead of 245, so those two badges were set back.
  - [x] The README's `app_widget_tests`: 51 (2026-11-20, `scripts/gtk.sh test` on the owner's Fedora computer: 51 passed; 49 at `v7`).
  - [x] The Mac's token counts (done 2026-11-22: this computer recorded as `linux`, the README's table, the badges `origin-ai-cost` and `origin-tokens` from `--summary`; `scripts/badges.py` takes the sum of `docs/usage/` now): recorded on 2026-11-20 in `docs/usage/mac.json` (`scripts/ai_usage.py --record mac`: 19–20 November, 4.7 h active, 804 responses, 217 M tokens, 112 USD at API prices on 2026-11-20, the README's 100 USD being the Mac's cost up to the release). Left: the Linux computer's own record (`--record <device>`, CLAUDE.md), then the badge `origin-tokens` and the README's Mac rows from `--summary`.
- [x] Released 2026-11-20 (owner: "if green, merge to main and set the tag v8", then "release it"): `claude/mac-shell` merged into `main` as 7311aaf (check, mac, site and models-macos green on it), the tag `v8` on it, the release run 44699332411 green, the draft held `Stickler-8.dmg`, `Stickler-8.flatpak`, `Stickler-8-x86_64.AppImage` and its `.zsync`; release notes in English with the website named (owner), published 08:11 UTC; the site's run 44700567199 deployed it: `https://stickler.tshia.ng/`, `/de/` and `/install-mac.html` answer 200, a missing page shows Stickler's own 404, the download cards link the three v8 files (55, 33 and 136 MB). Planned before: the workflow makes the draft release with the Flatpak, the AppImage and `Stickler-8.dmg` (task 136's last step); the owner checks that all three are there and publishes it. The website goes online with a published release ≥ 8 (task 124: the domain first).

## Phase 25: Release 9, module `linux-packages` (approved 2026-11-20, SPEC.md "Module `linux-packages`")

- [x] **Task 138: Python 3.15 for the app** (S): done 2026-11-20. The relock only added cp315 wheels (no version changed). On 3.15 two cache-key tests failed: 3.15's lazy imports give every import an `is_lazy` field in `ast.dump`; `runner._canonical` drops it for ordinary imports, so every adapter's digest is identical on 3.12 and 3.15 and unchanged by the fix (`stickler cache-digests` on both). The full suite passes on 3.15 (1085).
  - Acceptance: `requires-python = ">=3.12,<3.16"`, `uv.lock` relocked (no adapter cache key changes: adapters have their own locks); CI's matrix tests the ends 3.12 and 3.15; the full test suite passes on 3.15 locally.
  - Verify: `UV_PYTHON=3.15 uv run pytest -q`; `scripts/check.sh task`
  - Dependencies: none · Files: `pyproject.toml`, `uv.lock`, `.github/workflows/check.yml`

- [x] **Task 139: The app installed by the system** (S): done 2026-11-20. `paths.packaged()` gives `"system"` for `STICKLER_PACKAGED=system`, with the AppImage's folders and uv settings; the prefix is the system Python's (`/usr`). The launcher `packaging/linux/stickler-gtk` runs `python3 -I` (no user site-packages), puts `/usr/lib/stickler` and `python3.<minor>` on the path, `/usr/lib/stickler/bin` (uv) first on `PATH` (no empty entry), and names the supported versions when the running Python has no folder.
  - Acceptance: `paths.packaged()` gives `"system"` when the launcher set `STICKLER_PACKAGED=system`; folders and `packaged_env()` as for the AppImage (uv's own Python 3.14, downloads in Stickler's folders, the adapters' sources from `/usr/share/stickler/adapters`); the launcher `packaging/linux/stickler-gtk` puts `/usr/lib/stickler` and the wheels' folder of the running Python minor version on the path, says clearly when there is none, and starts the app.
  - Verify: `uv run pytest -q tests/test_paths.py tests/test_linux_launcher.py` (names as they turn out)
  - Dependencies: none · Files: `src/stickler_app/paths.py`, `src/stickler_app/__init__.py`, `packaging/linux/stickler-gtk`, tests

- [x] **Task 140: Building the packages** (M): done 2026-11-20. `scripts/linux_packages.py build` (Python instead of the planned shell script, so its parts are tested): the wheels of numpy, mido, packaging and verovio per 3.14 and 3.15 (`flatpak_deps.pick` takes the Python tag now), uv 0.13.9 and nFPM 2.49.0 pinned by SHA-256, the adapters' tracked files only. 68.7 MB `.deb`, 71.7 MB `.rpm` (numpy and verovio twice, 30 MB each; uv 43 MB unpacked). The first build owned `/usr/share/fonts`, the icon theme's and the locale folders through one tree of `/usr`; now trees only for Stickler's own folders and single files elsewhere, tested.
  - Acceptance: `scripts/linux_packages.py build` stages the tree (the three packages, the wheels of `uv.lock` unpacked per Python 3.14 and 3.15 with their hashes checked, `uv` and nFPM pinned with SHA-256, adapters' sources without environments or weights, icons, desktop file, MetaInfo, `.mo` files, Leipzig font) and builds `dist/Stickler-<v>_amd64.deb` and `dist/Stickler-<v>.x86_64.rpm` from `packaging/nfpm.yaml` with the dependencies per family; a test checks the staged tree (every file in place, no `.venv`, weights or `__pycache__`).
  - Verify: `uv run python scripts/linux_packages.py build`; `uv run pytest -q tests/test_linux_packages.py`
  - Dependencies: 138, 139 · Files: `scripts/linux_packages.py`, `packaging/nfpm.yaml`, tests

- [x] **Task 141: The packages in clean containers** (M): done 2026-11-20, all three green at the first run. `packaging/linux/container-test.sh` in `ubuntu:26.04`, `fedora:44` and `fedora:45` (podman, `--pull=newer`): the package manager installs the file with its dependencies, ffmpeg and GStreamer (`uridecodebin`, as the playback) decode an MP3 and an AAC clip (made in the Ubuntu container; Fedora's `ffmpeg-free` 8.1 and 9.0 decode both), the app runs 25 s as a user on Xvfb in its own D-Bus session without a traceback, and after removing nothing named `*stickler*` or `ng.tshia.*` is left under `/usr`, `/etc` or `/opt`. The app runs as a user because Python run as root would write `__pycache__` into `/usr/lib/stickler`.
  - Acceptance: `uv run python scripts/linux_packages.py test` installs each file into a clean `ubuntu:26.04`, `fedora:44` and `fedora:45` container with the system's package manager, starts the app on an invisible screen (the window opens, no exception), checks that ffmpeg and GStreamer decode an MP3 and an AAC clip, removes the package and finds nothing of it left under `/usr`. A failed decode is reported to the owner before anything changes.
  - Verify: `uv run python scripts/linux_packages.py test`
  - Dependencies: 140 · Files: `scripts/linux_packages.py`, `packaging/linux/`

- [x] **Task 142: The release workflow** (S): done 2026-11-20, the manual run 44708663463 green (flatpak, appimage, mac, linux-packages; attach skipped without a tag). Job `linux-packages` on `ubuntu-26.04` (gettext and podman from apt, then `python3 scripts/linux_packages.py test`), its two files an artifact, `attach` needs it; zizmor clean.
  - Acceptance: `release.yml` builds and container-tests both files on every tag and by hand, and `attach` adds them to the draft release; actions pinned by SHA, zizmor clean.
  - Verify: a manual run green; `scripts/check.sh task`
  - Dependencies: 141 · Files: `.github/workflows/release.yml`

- [x] **Task 143: Install texts** (S): done 2026-11-20. README (`> INSTALL THE APP`, the system row, removing), `docs/requirements.md`, the website in English and German: one Linux card instead of three (owner, 2026-11-20: "mach Linux alles zu einer Karte"), leading by system, the Flatpak and the AppImage as secondary buttons, the three terminal lines under a `<details>`; the short Mac card no longer stretched to the Linux card's height; uninstalling for Ubuntu and Fedora. `site_release.py` fills `.deb` and `.rpm`; axe 0 violations, looked at in light and dark, desktop and phone. There is no release-note template in the repository; the notes of release 9 name both files when written.
  - Acceptance: the README's `> INSTALL THE APP`, `docs/requirements.md`, the website's download cards in English and German (filled by `scripts/site_release.py`) and the release-note template name `.deb` (Ubuntu 26.04+) and `.rpm` (Fedora 44+), the terminal lines, uninstalling, and to use one package, not the Flatpak as well.
  - Verify: `uv run pytest -q tests/test_site.py`; `scripts/site_axe.py`
  - Dependencies: 142 · Files: `README.md`, `docs/requirements.md`, `site/`, `scripts/site_release.py`, tests

- [x] **Task 144: Review and the owner's check** (S): done 2026-11-22. The review done 2026-11-20 (fresh context, each finding checked): fixed: the Linux card overflowed the page between about 640 and 900 px (it stacks by the card's own width now, a container query; measured at 11 widths from 320 to 1280 px in both languages, no overflow); the container test now waits for the app's window (`xwininfo`), fails on `CRITICAL` too and runs the bundled uv; the launcher writes no bytecode (a start as root would leave `__pycache__` no package owns) and falls back to the system's default `PATH`; the `.deb` recommends a GStreamer audio output (PipeWire or PulseAudio) and both packages bound Python to 3.14–3.15; the three copy buttons have their own names; file modes no longer depend on the builder's umask. Not changed: no bytecode is shipped (about 0.3 s more at each start). The owner's check (2026-11-22): set up, analysed, played and exported on Ubuntu 26.04 and on Fedora, both installed by Claude with apt and dnf in the owner's Distroboxes (the owner's Bluefin is an atomic Fedora, where the Software app cannot install a local `.rpm` as on Fedora Workstation). The Software apps checked without their windows instead (owner: fine): Ubuntu 26.04's App Center (stable snap) claims `.deb` files and installs through PackageKit, GNOME Software 51 on Fedora 44 and 45 claims `.rpm` files and installs through dnf5daemon; `container-test.sh` now installs each package a second time that way (PackageKit first refuses the unsigned file with `need-untrusted`, as the App Center's first try, then installs it), all three containers green. Under PackageKit, x11-common's maintainer script fails in a container without an init system (also alone, without Stickler), so that second install runs while the dependencies are still there.
  - Acceptance: a fresh-context review of 138–143, each finding checked; the owner installs the `.rpm` on their Fedora and the `.deb` on Ubuntu 26.04 (a VM is fine), through the software centre, and sets up, analyses, plays and exports a song.
  - Verify: the owner
  - Dependencies: 143

- Prepared for release 9 (2026-11-20): the release notes' draft in `tasks/release-9-notes.md`; the MetaInfo's branding colours are the Mac icon's orange `#e8894a` and `#6b3816` in dark (owner, from three rendered banners; before the sticks' `#cdab8f` / `#865e3c`).

### Checkpoint AA
- [x] All success criteria of SPEC.md "Module `linux-packages`" met (owner, 2026-11-22: the packages run on Ubuntu and Fedora, the Software apps' check without their windows "passt"; that the tag attaches both files is seen at release 9, the manual run 44708663463 built them); then release 9

### Release 9
- [x] Prepared and committed as "Release 9" (2026-11-22; ADR 0006): no open Dependabot alerts; version 9 in `pyproject.toml`, `src/stickler/__init__.py`, `mac/project.yml` and `uv.lock`; the MetaInfo's `<release>` and `CITATION.cff` dated 2026-11-22 (change both if the tag comes on another day); README (intro, install lines, roadmap, key figures: 1103 tests), the website's Flatpak line, `docs/bridge.md`; badges version 9, python 3.12 · 3.15, AI cost about 478 USD and 1,348 M tokens from `scripts/ai_usage.py --summary` (this computer recorded as `linux`: 365 USD, 26.2 h; the Mac's record of 19–20 November: 113 USD, 4.7 h; no Mac sessions since, owner). SPEC's release 9 status done. The release notes' draft `tasks/release-9-notes.md` checked against v8..HEAD.
- [x] Released 2026-11-22 (owner: push and tag when green, then "ja" to publishing): `check` had been red on `main` since 2026-11-20 (gettext missing in CI, fixed in 525941c), the tag `v9` on 525941c with check, mac, site and models-macos green; the release run 45025800069 green, the draft held `Stickler-9_amd64.deb`, `Stickler-9.x86_64.rpm` (SPEC success criterion 1), `Stickler-9.flatpak`, `Stickler-9-x86_64.AppImage` with its `.zsync` and `Stickler-9.dmg`; published 13:13 UTC with the notes of `tasks/release-9-notes.md` (deleted); the site's run 45026355645 deployed it: `https://stickler.tshia.ng/` and `/de/` answer 200 and link the five v9 files.

## Phase 26: Website, How it works as a story (approved 2026-11-22, SPEC.md "Website", "Change 2026-11-22")

- [x] **Task 145: The story's data and pictures** (M): done 2026-11-22. `scripts/site_story.py analyse` ran the app's Fast analysis of `Fluffing a Duck.mp3` (13 s): 45 hits in the first 20 s (34 snare and toms, 10 kick, 1 cymbal: the first bars have almost no hi-hat), 9 bars in the first two systems; `notes.svg` keeps those two systems (Verovio's inner scale cut by the same share, the tempo mark dropped: its note is a glyph of Leipzig, which the site does not load), 99 kB. `draw` makes the waveform with the hits' dots and the bar marks, each with its part of the scroll in `--from`/`--to`; the pages get their places in 146 (the test that they hold the drawing moves there). SPEC adjusted: the clicks' three groups instead of four, the waveform from the song, the notes as an `<img>`.
  - Acceptance: `scripts/site_story.py analyse` runs the Fast analysis of the example song once and stores what the pictures need in `site/story/*.json` (the clip's waveform envelope, the hits of its first 20 s by class, the engraved first systems as SVG); `scripts/site_story.py draw` writes the four pictures' SVGs from that data only, in the site's colours through CSS custom properties (light and dark).
  - Verify: `uv run pytest -q tests/test_site_story.py` (the stored SVGs equal what `draw` makes of the stored data; the hits are those of `site_clip.py`'s clip)
  - Dependencies: none · Files: `scripts/site_story.py`, `site/story/`, `tests/test_site_story.py`

- [x] **Task 146: The section without motion** (S): done 2026-11-22. `#how` in both languages is an `<ol class="story">` of four steps (number, heading, sentence) with a picture each (`aria-hidden`): the file card over the drop area, the waveform with the hits' dots in three lanes and their legend and the three stages ticked, the engraved bars with bar 1 marked and a play bar, the three files. Text beside the picture from 48rem, picture above it below; on a phone the sheet music is shown 170 % wide, cut at the card's edge, so its notes stay readable; in dark the snare's dots are the text colour (the ink and the accent are both orange there) and the notes are inverted. The four cards, their icons and their CSS are gone. axe 0 violations (its eight "to check by eye" as before); looked at 320, 390, 900 and 1280 px, light and dark, both languages, no overflow.
  - Acceptance: `#how` in English and German is an `<ol>` of the four steps (heading and sentence of SPEC), each with its picture (`aria-hidden`); wide: text and sticky picture side by side, phone: picture above text; each picture shows its end state; the four cards and their icons are gone.
  - Verify: `uv run pytest -q tests/test_site.py`; axe; screenshots at 320, 390, 900 and 1280 px, light and dark, both languages, no overflow
  - Dependencies: 145 · Files: `site/index.html`, `site/de/index.html`, `site/style.css`, `tests/test_site.py`

- [x] **Task 147: The motion** (S): done 2026-11-22. One block `@media (prefers-reduced-motion: no-preference) { @supports (animation-timeline: view()) { … } }` in `style.css`: each step is a view timeline (`--story-step`); from 48rem a step is 90vh tall and its text and picture stick at 22vh while it passes; the file drops in, the hits pop up left to right, the stages' ticks appear one after the other (their text stays at full contrast: dimmed text failed axe), the bar mark goes from bar to bar and the last stays, the play bar fills, the files fan out; only `opacity` and `transform`. Found on the way: the site's Content-Security-Policy (`style-src 'self'`) drops style attributes, so the hits' and bars' ranges are not `--from`/`--to` on the elements but rules in `site/story/story.css`, written by `site_story.py draw` (a test keeps it equal to the data, another that no picture has a style attribute). Checked in Chromium (Playwright): the scroll recorded at 1280 and 390 px, frames looked at; with reduced motion 146's end states; axe 0 violations.
  - Acceptance: each picture moves on its own step's `view()` timeline as SPEC scope 1 describes (the file slides in, the dots and ticks appear, the bar mark moves, the cards fan out), only `opacity` and `transform`; with `prefers-reduced-motion` and without support the end states of 146 show.
  - Verify: a scroll recording in Chromium (Playwright) at 1280 and 390 px; the same page with reduced motion shows 146's screenshots
  - Dependencies: 146 · Files: `site/style.css`

- [x] **Task 148: Review** (S): done 2026-11-22. A fresh-context review of 145–147, each finding checked against the code. Fixed, each with a test that failed before: at exactly 48rem (768 px, an iPad upright) the one-column rule and the motion's sticky two columns both applied, so the text covered the picture (one column now below 47.99rem); the last hit's dot was cut in half at the picture's edge (the dots keep their radius from both edges); `notes.svg` carried Verovio's embedded music font, 58 kB nothing used (dropped: 99 → 39 kB); `draw` wrote the CSS and the first page before a missing place on the second failed (now all made first); sheet music without bars fails with a reason; the `<img>`'s width and height are tested against the SVG's; the big step number is `aria-hidden` (the `<ol>` numbers the steps for a screen reader); the site's workflow runs `tests/test_site_story.py` too. Not changed (minor): on a phone the last hits and bar marks appear while the picture already leaves the top (the timeline is the whole step's; it still ends complete); the dots are about 2 px on a 320 px screen; bar 1's mark covers the clef (Verovio's bar box includes it); `story.css` sets `animation-range` outside the motion block (harmless without a timeline). SPEC scope 2 says why the font and the CSS file.
  - Dependencies: 147

- [x] **Task 149: The owner's check and going online** (S): done 2026-11-22. The owner saw the scroll recordings at 1280 and 390 px ("passt, geh online damit"); `claude/site-story` fast-forwarded into `main`, the site's workflow run by hand with `deploy: true`.
  - Dependencies: 148

## Phase 6: Later (noted by the user, 2026-11-12)

- [x] **A website for Stickler** (owner, 2026-11-18; online 2026-11-20, Phase 22): interviewed 2026-11-18 (`docs/intent/website.md`), spec approved 2026-11-18 (SPEC.md "Website"): plain HTML/CSS in English and German, GitHub Pages at `stickler.tshia.ng`, a look of its own matching the app, built now and online with release 8. Figtree and Apricot chosen, light and dark follow the browser (pictures and video too), WCAG 2.2 AA, "About the author" instead of "How it's made" (owner). Mockup on the private canvas "Stickler website" (https://claude.ai/artifact/UwYfekTuMnMWTVhWb5xk4s). Open: the hero's line, the author text and photo, an imprint (legal, owner). Example song: "Fluffing a Duck" (owner). First noted from tuxtalk.app; the older "GitHub Pages site" idea is dropped in its favour.
- [x] **Later release: click volume follows the song** (done in module `polish`) (owner, 2026-11-15): songs differ in loudness; the clicks suit Eye of the Tiger but are too loud on Amaranthe's "Fearless". Measure the song's loudness where the hits are and set the clicks relative to it.
- [x] **Later release: "Remove Downloaded Models…" in the app** (done in module `polish`) (owner, 2026-11-15): a menu entry that deletes the models, their environments and the results after asking, so an AppImage user need not know the folders.
- [x] **Later release: the band's name in the PDF** (done in module `polish`) (owner, 2026-11-15): the engraved page shows the title but not the artist.
- [x] **Screenshots in the README** (owner, 2026-11-16; done 2026-11-17: `docs/screenshots/overview.gif` recorded with an empty results cache so the analysis is seen, checked by the owner, at the README's top): a few telling screenshots of the app in the README; today it has none (only the `how-it-works.svg` diagram). Start from the three AppStream screenshots in `docs/screenshots/` (sheet, corrections, dark; "Fluffing a Duck", CC BY 4.0) and decide with the owner which screens show Stickler best.
  - 2026-11-16 (owner, after GymMane's README): an animated overview at the very top, the app icon under it, single screenshots further down; the ASCII banner goes (it suits a CLI-only project, noted in the owner's skill template). Done: the README's top (the sheet screenshot stands in for the overview until it is recorded), a section `> THE APP` with the three screenshots, `scripts/gtk.sh demo` with `scripts/demo.py` to record the overview. Open: record `docs/screenshots/overview.gif` on the laptop (`scripts/gtk.sh demo <Fluffing a Duck>`), check it, and point the README's top image at it.
- [x] **Lessons learned, once most of the project is done** (owner, 2026-11-15; first noted for after release 5): write down what building the app taught us (mistakes, detours, what worked), so a comparable project starts faster and more directly. Done 2026-11-16 as the portable skill `owner-led-projects` in [niklastshiang/claude-skills](https://github.com/niklastshiang/claude-skills) (MIT, owner): general working rules only, each with its reason from Stickler, built on addyosmani/agent-skills, plus a README template (to be improved by comparing with successful projects, owner). Its rules came from this file, the ADRs, SPEC.md and the git history; a fresh-context subagent reviewed it.

Not planned yet, just recorded. Before starting each one, extend SPEC.md and break it into tasks.

- [x] **Release 3 published on 2026-11-14** (tag v3, GitHub release): error analysis and honest numbers (Phase 7). Owner, 2026-11-14: Quality stays as a mode for now, although Fast is ahead after the correction.
- [x] **Release 2 published on 2026-11-13** (tag v2, GitHub release): readable sheet music (similar bars simplified, repeat signs). Release 3 (owner, 2026-11-13): the error analysis on the own songs (see Phase 5c).
- [x] **Release 1 published on 2026-11-13** (tag v1, GitHub release, repository public; private vulnerability reporting and Dependabot alerts on, pull requests and wiki off).
- [x] **Release plan (owner, 2026-11-13):** the repository goes public with release 1; the old music folder names in the git history may stay. Release 1 = the command line tool (`notate --mode fast|quality` once the 25-song results are in, docs in `docs/`); the GTK application is the next release after it, whatever its number is (ADR 0006: every release counts, fixes to the command line tool in between included; owner, 2026-11-13). With the application, add the GitHub topics `gtk4`, `libadwaita`, `flatpak` (18 of 20 are set since 2026-11-13). Owner, 2026-11-13: release 2 is another command line release; the application comes after it.
- [x] **README picture of `stickler notate`** (owner, 2026-11-13; checked 2026-11-17: the footer already gives the 25-song numbers, Fast 0.77 · Quality 0.78, as report section 1): `docs/images/how-it-works.svg` is drawn (song → Fast/Quality → notation → MusicXML/PDF/drum track); in the README since 2026-11-13; `notate --mode fast|quality` exists (note removed); still update the accuracy line in its footer from the 25-song results.
- [ ] **Contributions (owner, 2026-11-13):** no outside pull requests (CONTRIBUTING.md, issue forms for bugs and model suggestions, no code of conduct). Pull requests are switched off in the repository settings (owner, 2026-11-13; GitHub setting since 2026-02). If issues become too many: restrict issue creation to collaborators (GitHub setting since 2026-06). SECURITY.md asks for private reports; owner enables private vulnerability reporting and Dependabot alerts (not security/version updates: they need pull requests, and model versions are pinned on purpose). Before every release: go through open Dependabot alerts.
- [x] **Dependabot alerts (2026-11-13):** torch 2.15 for Demucs (the lock was held at 2.2.2 by demucs's Intel-macOS pin; now resolved for Linux only), Beat This! and ADT_STR; outputs compared before/after on three MDB songs (Beat This! identical, ADT_STR 2 of 246 notes 9 ms apart, Demucs differs as much as two runs of the same version, because of its random shift) and the cache rekeyed (snapshot `data/archive/digests-before-torch-2.15.json`, needed again for results from pods that ran the old versions). YourMT3+ removed (transformers could not be updated); its results stay in the report. New smoke test: ADTOF on a real mix (Fast mode).
- [x] **GitHub Pages site (owner, 2026-11-13: idea for later):** dropped 2026-11-18 (owner): replaced by the website (SPEC.md "Website"); no documentation site, no generator.
- [ ] **`.deb` and `.rpm` packages (owner, 2026-11-18):** for Debian/Ubuntu and Fedora, next to the Flatpak and the AppImage; not before the Mac release (release 8).
- [ ] **Windows and macOS packages (owner, 2026-11-16: idea):** `.msi` and `.exe` for Windows, the fitting format for macOS (a `.dmg` with the `.app`; see the macOS note below). To check first, before a spec: GTK 4 and libadwaita on Windows (MSYS2 or gvsbuild, as other GTK apps ship them) and on macOS; `uv` and the models' PyTorch wheels per platform (CPU everywhere, CUDA on Windows, MPS on Apple Silicon), and which adapter locks are resolved for Linux only (Demucs, MuScriptor); ffmpeg, GStreamer and the Leipzig font in the package; the installer tools (WiX for `.msi`, Inno Setup or NSIS for `.exe`) and code signing (unsigned installers warn on both systems); CI runners for both. Stickler never ships model weights, so the setup assistant downloads them on every platform, as today.
- [ ] **Interfaces for Windows and macOS, effort (2026-11-16):** the owner has access to a Mac and a Windows computer for testing at checkpoints. Measured on today's app: `ui/` about 2,100 lines, `logic/` about 1,400 (GTK-free on purpose), widget tests about 2,500, built over releases 4–6. Options: (1) GTK everywhere, only packaging and the POSIX spots, looks like GNOME on both; (2) Qt (PySide6 6.12, LGPL, wheels for macOS universal2 and Windows x64/ARM; native menu bar and dialogs on the Mac, Windows 11 style) for Mac and Windows: `ui/` once more in Python, `logic/` and the engine reused, two interfaces to maintain (GTK on Linux, Qt elsewhere); (3) fully native (SwiftUI, WinUI): two interfaces in two new languages, `logic/` ported or put behind a new bridge to the Python core, sheet view in a web view, system playback instead of GStreamer, two more translation formats; about three to four times option 2, and every later feature built three times. Claude's suggestion was GTK first, Qt later; the owner does not like Qt's look (2026-11-16), so option 2 is out. Left: GTK everywhere (looks like GNOME on Mac and Windows; native window buttons on the Mac since libadwaita 1.8, no global menu bar) or fully native. **Decided (owner, 2026-11-16): GTK on Windows and macOS to start with**; a native interface stays possible later. Windows and macOS come as a release of their own after release 7 (owner, 2026-11-16); its spec starts from the research notes below. **Changed for macOS (owner, 2026-11-17): a native SwiftUI app over a shared Python core, macOS only, release 8 (SPEC.md "Release 8: macOS app")**; Windows gets its own spec later.
- [ ] **Windows research (2026-11-16, at the owner's request; two research subagents, key facts checked):**
  - Models: all four app models resolve for win_amd64 (trial locks in copies; Demucs and MuScriptor need `sys_platform == 'win32'` in `environments`; torch 2.15.0+cpu and torchaudio 2.11.1 have win_amd64 wheels). CUDA on Windows works through cu132; AMD and Intel GPUs on Windows: CPU (DirectML is stale, ROCm for Windows does not cover the Radeon 840M).
  - Harness, POSIX-only spots: `os.killpg`/`SIGKILL` and `start_new_session` for cancelling (adapters.py, about lines 177 and 193; on Windows a Job Object or `taskkill /T`), `import resource` for peak RAM in `adapters/_common` (the adapter would not start; `GetProcessMemoryInfo` via ctypes keeps it stdlib-only), `bin/python` vs `Scripts\python.exe` (adapters.py, doctor.py); ffmpeg, ffprobe and MuseScore paths.
  - Interface and installer: GTK 4 on Windows ships in Gaphor (PyInstaller, GTK from gvsbuild), libadwaita 1.9 on Windows untested; `.exe` with Inno Setup (free, per-user install without admin), `.msi` with WiX v7 (free below 10,000 USD a year of use); GStreamer must match GTK's C runtime (MSVC vs MinGW); Verovio 6.4.1 has a `win_amd64` wheel; GitHub's Windows runners are free for a public repository.
  - Signing: unsigned installers show SmartScreen's "Windows protected your PC" (More info → Run anyway), and Windows 11's Smart App Control may block them. Free route: SignPath Foundation signs open-source projects for free (OSI licence for all components without commercial dual licensing, malware-free, a code signing policy with a credit line, SignPath Foundation shown as publisher; Stickler is GPL-3.0-or-later, the NC model weights are not shipped). Paid: an OV certificate (about 220–440 USD a year) or Azure Artifact Signing (individuals possibly limited to the USA and Canada, unconfirmed). winget and Scoop take installers without a certificate requirement found (unconfirmed).
- [ ] **macOS research (2026-11-16, at the owner's request; two research subagents, key facts checked):**
  - Models: all four app models resolve for macOS arm64. ADTOF's and Beat This!'s locks already hold torch 2.15 `macosx_14_0_arm64` wheels; Demucs and MuScriptor need their `environments` widened by `sys_platform == 'darwin' and platform_machine == 'arm64'` (the Linux-only restriction exists for an old torch on Intel Macs; a trial lock in a copy resolved). macOS 14 or newer. MPS (Metal) is untested for these models: ship CPU first, measure Demucs and MuScriptor on a Mac against the CPU (identical notes) before using it; the harness's device choice only knows CUDA today (`stickler_adapter.choose_device`), and `PYTORCH_ENABLE_MPS_FALLBACK=1` would be needed. Widening a pyproject changes its digest: add a `digests.yaml` pair for Linux (behaviour unchanged there).
  - Interface: GTK 4 + libadwaita on macOS works and ships in Gaphor (`.dmg` built with Homebrew + PyInstaller), with libadwaita drawing its own style (native window buttons since 1.8, no global menu bar); a native SwiftUI interface would rewrite the sheet view, playback, corrections and setup assistant over the Python core (as a subprocess). The research recommends GTK first, the owner's note of 2026-11-13 prefers native: open.
  - Without paying (owner, 2026-11-16: a free route first): (1) a `.dmg` that is only ad-hoc signed (Apple Silicon requires a signature; ad-hoc is enough), built on GitHub's free macOS runners. macOS 15 and later block it on first start; the user opens it with System Settings → Privacy & Security → "Open Anyway" and the admin password (the Control-click shortcut is gone since Sequoia), so the install guide shows that step with pictures. (2) Later, for technical users, a Homebrew formula in an own tap that builds Stickler on GTK 4, libadwaita and PyGObject from Homebrew: what Homebrew builds is not quarantined, so no Gatekeeper prompt, but it is installed and started from the terminal. Not a cask: Homebrew announced in 5.0.0 that casks failing Gatekeeper are disabled from September 2026 (whether that happened was not confirmed). The Developer Program does not require selling anything; it is only a fee, worth reconsidering if the Mac version finds users.
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

- [x] **The tempo mark runs into a multi-bar rest's count** (owner, 2026-11-19, at the check on the Mac): fixed 2026-11-19. Reproduced with 22 empty bars at ♩ = 97: Verovio centres the count over the rest, which is narrow, right behind the mark. Of two ways shown to the owner (a wider rest through Verovio's `measureMinWidth`, or bar 1 as a rest of its own), the owner chose the second: `notation.engrave` never starts a multi-measure rest at bar 1, so Majesty reads ♩ = 97 over a whole-bar rest, then a rest of 21 (two empty bars at the start are two whole-bar rests). Seen in the window's layout and on A4. A song already analysed shows it when it is opened again. SPEC `engine-api`, success criterion 4, says so.
  - Seen: the PDF of Apashe's "Majesty" starts with 22 bars of rest; the tempo mark (♩ = 97) and the rest's count stand side by side above the staff and read "= 9722".
  - It comes from the core's engraving, so the GTK app and the sheet in both windows have it too.

- [ ] **The Mac app in Spanish, checked by the owner** (put off by the owner, 2026-11-19)
  - German was checked at checkpoint U; the bridge answers `es` for `es_ES:en` (seen on the Mac), the app itself was not looked at in Spanish.

- [ ] **A rock or metal song as the example instead of "Fluffing a Duck" (owner, 2026-11-20: idea for later)**: an openly licensed song (e.g. CC BY, as Kevin MacLeod's) in the owner's genres for the screenshots, the website's clip and the README picture; licence and attribution checked on the web first, then the pictures recorded again (`docs/website.md`, `scripts/gtk.sh demo`).

- [ ] **Mac screenshots in the website's "A look around" (owner, 2026-11-20: idea for later)**: the gallery (`site/index.html` `#look`, and `/de/`) shows only the GTK app; add the Mac app's windows, light and dark, e.g. from the `mac` workflow's screenshot artifacts. Best done together with the new example song (above), so all pictures are recorded once.

- [ ] **Back up settings and analysed songs (owner, 2026-11-20: idea for later)** (specified 2026-11-22 as a draft: SPEC.md "Release 10 (proposed): keep and remove"): one way in the app to save and restore what a user would miss after a new computer or a reinstall: the settings (`settings.json`), recent songs and corrections (`recent.json`, `corrections.json`), and the analyses (sheet music and hits under the cache folder, the models' results), without the models themselves (downloaded again). To work out first: one archive file or a folder, what an analysis needs to be found again (the song's path or its content's digest, as songs move), the same on Linux and the Mac (its folders differ), and whether the Flatpak's sandbox needs a file chooser portal for it.
  - Seen at TuxTalk (ronb1964/TuxTalk, MIT; owner, 2026-11-22: "ja"): Preferences, Updates & Backup saves the settings, the user's words, corrections and stats to one file and loads it on a new computer; besides, the app keeps its last 10 settings by itself, so a change or an update that went wrong can be taken back. For Stickler the analysed songs with their corrections belong in it too; the last few settings kept by themselves would fit `settings.json`. A spec could take this together with "Uninstall Stickler…" (below): both concern the same folders.

- [ ] **A dark-mode icon for the Mac app (owner, 2026-11-20)**: decided by the owner: the light icon's design (`#e8894a`, sticks as they are) with the paper and the notes' colours swapped (paper `#241f31` with its shadows `#3d3846`/`#5e5c64`, notes and rests `#ffffff`), the staff lines grey as before (`#9a9996`), the orange background kept (draft 2 of three rendered). How: since macOS 26 the appearances (default, dark, clear, tinted) come from an Icon Composer `.icon` file that Xcode builds into the app, also making the images for older systems; an `.appiconset` has no dark variant (Apple developer forums, checked 2026-11-20). So `scripts/mac_icon.py` writes a `Stickler.icon` bundle (background as the fill, the layers, a dark specialisation) instead of the PNGs; Icon Composer itself needs macOS 26.4, so the format is written by script and checked by the `mac` workflow's build and on the owner's Mac. macOS then adds its own shape and glass, so the icon looks a little different from today's flat one; the owner checks both appearances.

- [ ] **Own package repositories for the `.deb` and `.rpm` (owner, 2026-11-20: idea for later)**: an apt repository (e.g. on GitHub Pages) and a Fedora COPR or an own dnf repository, so updates come with the system's. Needs a signing key in GitHub's secrets, its care, and a guide to add the repository. The first `.deb`/`.rpm` release ships the files on the release page only (owner, 2026-11-20).

- [ ] **"Uninstall Stickler…" in the app (owner, 2026-11-20: idea for later)** (specified 2026-11-22 as a draft: SPEC.md "Release 10 (proposed): keep and remove")
  - Seen at TuxTalk: one entry in the preferences removes the program and everything it set up (its downloads, starting at login, the menu entry, …), may ask for the password once; models in a folder other apps share go only with a ticked box, settings and the word list stay unless a second box is ticked.
  - Stickler today: "Remove Downloaded Models…" (`stickler_app/removal.py`) deletes the models, their environments, uv's Python and downloads and the saved analyses; "everything" also the data, cache and settings folders. The program itself stays: the Flatpak needs `flatpak uninstall --delete-data`, the AppImage file and the Mac's `.app` are deleted by hand (the uninstall texts on the website and in the README).
  - **Only if it makes sense on every system (owner, 2026-11-20)**: Flatpak, AppImage and Mac; otherwise not at all. The Flatpak is the likely blocker: removing itself from the sandbox needs `flatpak-spawn --host`, i.e. a hole in the sandbox.
  - To work out first: what an uninstall can remove from inside each package (the Flatpak cannot uninstall itself from the sandbox; the AppImage knows its own path through `$APPIMAGE`, and a desktop entry only if an integration tool made one; the Mac app can move itself to the Bin after quitting); which boxes make sense (models, settings, recent songs and corrections); the texts in English, German and Spanish, in both apps.

- [ ] **Look for a new release, on request only (owner, 2026-11-22: idea for later)**: seen at TuxTalk, whose "Check for Updates" asks GitHub and shows the command or download for the way the app was installed. For Stickler only as an option the user turns on (off by default), or a menu entry that asks once when clicked: an automatic request would break the "100% local" promise (badge, website, privacy page). To work out first: GitHub's releases API without a token (rate limit), what each package does with the answer (the Flatpak and the `.deb`/`.rpm` get updates elsewhere, the AppImage has its `.zsync`, the Mac app needs the new `.dmg`), the privacy page's text, and that no request leaves before the user's click.

- [ ] **A test icon for builds that are not a release (owner, 2026-11-22: idea for later)**: the owner installs the `mac` and release workflows' apps from branches on the Mac; they look like the released app in the Dock and Finder. Seen at MustafaNatur/blueprint (MIT, Swift, macOS only): a blueprint version of the icon with a badge such as "DEV" for debug builds. For Stickler: `scripts/mac_icon.py` draws a second bundle (e.g. the drawing on blue or with a "TEST" badge), and builds that are not from a tag use it through `ASSETCATALOG_COMPILER_APPICON_NAME`; the same could hold for the GTK app's development builds. Not the tool itself (it would need Homebrew in the workflow).

- [ ] **French as a fourth language (owner, 2026-11-22)**: the apps in French, as Spanish came in Task 70. To decide with the owner first: only the apps or the website too (today English and German only: `site/` would get `/fr/` with every page, and `tests/test_site.py` compares the languages pairwise); France's French or a neutral one; "tu" or "vous" (the other languages say "du" and "tú"). What it touches: `po/fr.po` (the GTK app, 181 strings in `po/stickler.pot`) with `po/LINGUAS`, the Mac app's `Localizable.xcstrings` (`scripts/xcstrings.py`; the Mac texts come from the GTK catalogue), the MetaInfo's translated texts, the tests that check every catalogue (complete, placeholders kept, the width test measures French: it runs long), a look at the windows in French on Linux and the Mac, and SPEC.md's list of languages. The sheet's "Drumset" stays English, as in every language.

- [x] **The website's "how it works" as a story that follows the scroll, without JavaScript (owner, 2026-11-22: idea for later)** (specified 2026-11-22: SPEC "Website", "Change 2026-11-22"; Phase 26): seen at tuxtalk.app: four steps scroll by next to a sticky picture that changes with the step in view (there `site.js` picks the step and sets `data-step`; the pictures change by CSS). For Stickler in CSS only (SPEC "Website": JavaScript only where HTML and CSS cannot): scroll-driven animations (`view-timeline`/`animation-timeline: view()`; Baseline since October 2026: Chrome and Edge 115, Safari 26, Firefox 159, per web.dev). A sticky stage animated by the steps' timelines needs `timeline-scope`, whose support was not confirmed on 2026-11-22; the safe form gives each step its own sticky picture that fades with `view()`. Without support the steps simply stand one under the other; `prefers-reduced-motion` turns it off. Steps, for example: drop a song in → the models listen → the sheet music appears → play along and export. Pictures from the app (light and dark), in English and German; axe and the site's checks as for every page.

- [x] **The app icon's background in orange, like the website (owner, 2026-11-20: later)**: done 2026-11-20. The Mac icon's background is `#e8894a` (owner chose it over the website's `#f4a26b`, among rendered variants: "mac-e8894a"); the sticks keep their light wood in both icons (a first try with dark sticks in both was taken back, owner); the GNOME icon is unchanged and stays free-standing. `scripts/mac_icon.py` wrote the master and the seven pictures. Not changed: the design board copies in `docs/design/` (history) and the MetaInfo's branding colours.
  - The website's orange is `--accent: #f4a26b` (`site/style.css`). Icons: `packaging/icons/ng.tshia.Stickler.svg` (also `site/images/icon.svg`, the same file) and `ng.tshia.Stickler-macos.svg`; the symbolic icon has no colour. Check the contrast of the drawing on the new background, and rebuild what is made from the icons (the Mac icon via `scripts/mac_icon.py`; the site and the README use the SVG directly).

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
- [x] **M4A: the README and the spec disagree** (seen 2026-11-19 while writing `mac-package`): checked 2026-11-19, the README is right. Since 331c9c4 (2026-11-13) ffmpeg converts what the models cannot read to FLAC first; `stickler notate` on a 30 s AAC clip of Eye of the Tiger gave 59 hits and a MusicXML. SPEC `packaging`, assumption 9 ("M4A/AAC are not promised"), is older than that; `mac-package`'s decision 3 says so. Then named (owner, 2026-11-19: "mention that M4A works"): the empty window of both apps and the website's first step say "MP3, M4A, FLAC, WAV or OGG", with German and Spanish. Left open: whether the GTK app plays an `.m4a` (GStreamer's AAC decoder in the Flatpak and the AppImage).

