# Spec: Stickler

> Benchmark for automatic drum transcription (audio → sheet music) using open-source models only.
> As of: 2026-11-11 · Status: **approved** (with additions: GPU + later GTK interface)

## Assumptions
1. The only user is the project owner; use is private. Weights under NC license (ADTOF, MuScriptor) are allowed.
2. Everything runs locally: Ryzen AI 5 340, 30 GB RAM, iGPU Radeon 840M (**gfx1152**, RDNA 3.5, shares system memory). **The GPU is used wherever possible** (PyTorch ROCm wheels from AMD). Every adapter must also run on the CPU as a fallback.
3. Runtime is secondary; accuracy matters. A complete benchmark run may take overnight, because results are cached.
4. In v1, operation is via the command line. The report is a local HTML file. **A GTK interface comes later** (GTK 4 + libadwaita via PyGObject, fitting GNOME/Bluefin). That is why the logic lives in a library API, and the CLI is only a thin layer on top of it.
5. Drums only at first. Other instruments will be added later as new adapters, without restructuring the core.

## Objective
**End goal:** a finished desktop application (GTK 4 + libadwaita, distributed as Flatpak and AppImage) that generates drum sheet music from a song. The benchmark is the first step toward it; it determines the pipeline in the application's core.

Find out **which combination of drum-stem separation and transcription model produces the best drum sheet music**, on public test data and on your own songs (metal/electro, e.g. Electric Callboy). The best pipeline ultimately produces MusicXML or PDF sheet music.

User stories:
- As a drummer, I want to feed in a song and get sheet music that I only need to correct in MuseScore.
- As a developer, I want to add a new model to the comparison with an adapter folder and a config entry.
- As a developer, I want to see in a table which pipeline performs best per instrument class (kick, snare, toms, hi-hat, cymbals).

### Candidates
| Stage | ID | Project | License |
|---|---|---|---|
| Separation | `none` | Original mix | – |
| Separation | `demucs` | adefossez/demucs (maintained fork), `htdemucs_ft` | MIT |
| Separation | `roformer` | nomadkaraoke/python-audio-separator + BS-/Mel-RoFormer checkpoint with drum stem | MIT, checkpoint to be verified |
| Transcription | `adtof` | ADTOF-pytorch (Zehren), 5 classes | CC BY-NC-SA |
| Transcription | `adt_str` | pier-maker92/ADT_STR (2026), `setting-tau-0.8`, 26 classes | CC BY-SA |
| Transcription | `muscriptor_s`, `muscriptor_m` | muscriptor/muscriptor (2026), small/medium | MIT / weights CC BY-NC |
| ~~Transcription~~ | ~~`yourmt3`~~ | YourMT3+, removed 2026-11-13 (last on the own songs; transformers with known vulnerabilities could not be updated) | – |
| Transcription | `drumsep_onset` | DrumSep MDX23C 6-stem + librosa onsets per stem | Community |
| Beats | `beat_this` | CPJKU/beat_this | MIT |

## Tech Stack
- Python **3.12** and `uv` ≥ 0.13 (Homebrew). Every environment is managed with `uv`.
- Harness: `mir_eval`, `pretty_midi`, `music21`, `librosa`, `pandas`, `pyyaml`, `jinja2`, `typer`.
- Dev: `pytest`, `ruff`.
- Every adapter has its **own** `pyproject.toml` with its own environment (Torch CPU wheels). The harness never imports model code; it calls adapters as subprocesses.
- Optional: MuseScore 4 (Flatpak) for PDF export.

### GPU (AMD ROCm)
- PyTorch wheels from AMD for `gfx1152` with a bundled ROCm runtime; no system ROCm needed. Index `https://repo.amd.com/rocm/whl-multi-arch/` (ROCm 7.14.x) or `https://stable.repo.amd.com/rocm/whl-next/` (ROCm 10.x), package `torch[device-gfx1152]`. Which channel runs stably is decided via ADR.
- `/dev/kfd` and `/dev/dri/renderD128` are present and accessible to the user; the kernel is 7.2 (amdgpu).
- Every adapter environment exists in two variants: `cpu` (standard Torch CPU wheels) and `rocm`. The variant is selected via `stickler setup --device rocm`.
- Adapters accept `--device auto|cpu|gpu`. `auto` uses the GPU if `torch.cuda.is_available()`, otherwise the CPU. The device actually used is recorded in `meta.json`.
- Non-Torch models (e.g. ONNX) run on the CPU as long as there is no working ROCm/MIGraphX provider.

### Rented GPU for the development phase (NVIDIA CUDA, RunPod)
Only to speed up benchmark runs during development; the app itself runs locally. Decided with the owner on 2026-11-12: RunPod, RTX 4090 (24 GB), Community Cloud for public data (MDB), Secure Cloud in the EU for the owner's songs. Laptop runtimes stay the reference for the app's "Fast"/"Quality" modes.
- **CUDA environment:** `stickler setup --device cuda` builds `.venv-cuda` per adapter like the ROCm variant, but generically in the harness: direct dependencies, with `torch`/`torchaudio` replaced by the version pinned in the adapter's `uv.lock` from the PyTorch CUDA index. Adapter files stay untouched.
- **Device-independent cache:** results computed on a GPU count as cache hits on the laptop. The device is recorded in `meta.json` instead of the cache key. Together with comment-insensitive adapter digests this is one cache migration after the running MDB benchmark has finished; existing entries are moved to their new keys, nothing is recomputed.
- **`stickler remote`:** copies code, the needed audio and the cache to the pod via rsync over SSH, sets up the CUDA environments, runs a config, copies new cache entries back and, if a `RUNPOD_API_KEY` is set, stops the pod. Secrets (Hugging Face token, API key) are passed as environment variables only and never written to disk or the repo. No new harness dependencies (rsync, ssh, urllib).

### Later: GTK interface (not part of v1)
- GTK 4 + libadwaita via PyGObject, separate package `stickler-gtk` that only uses `stickler.api`.
- For this to work, v1 needs: a public API in `stickler/api.py` (`run_benchmark`, `evaluate`, `transcribe_song`, `notate`) with progress callbacks and cancellation support, no `print`s in the logic (logging instead), and results as data objects, not only as files.
- **Design together first:** before any GTK code, the owner and Claude design the interface together, following current design principles, above all the GNOME Human Interface Guidelines (libadwaita patterns, adaptive layout, accessibility). Mockups first, then implementation.
- Features requested by the owner:
  - **Two modes instead of a model choice:** "Fast" and "Quality" (pipelines decided after the benchmark).
  - **Readable sheet music:** fold repeated bars and passages into repeat signs (done in the command line tool for release 2: `notate` simplifies nearly equal bars and writes repeat signs; `--no-simplify`, `--no-repeats`).
  - **Export drum track:** a button that saves the separated drum stem (the pipeline produces it anyway) as WAV or FLAC, next to the sheet music export. The API returns the stem path as part of the result, e.g. `transcribe_song(...).stem`.

## Commands
```bash
uv sync                                         # harness environment
uv run pytest -q                                # tests
uv run ruff check --fix . && uv run ruff format .   # lint/format
uv run stickler setup --adapter adt_str --device rocm   # build adapter env (cpu|rocm) + load weights; without --adapter: all
uv run stickler doctor                          # checks GPU, envs, weights, HF login, MuseScore
uv run stickler fetch mdb                       # fetch MDB Drums into data/mdb/
uv run stickler run   --config config/benchmark.yaml --device auto   # compute matrix (cached)
uv run stickler eval  --config config/benchmark.yaml        # metrics → results/metrics.csv
uv run stickler report                                       # → results/report.html
uv run stickler align [song]                                 # check own references, verify + click.wav
uv run stickler notate song.mp3 --pipeline demucs+adtof --drums drums.flac   # → MusicXML (+ PDF via MuseScore), drum track
```

## Project Structure
```
SPEC.md, CONSTRAINTS.md, README.md
pyproject.toml                 # harness package "stickler"
src/stickler/
  api.py                       # public API (for CLI and later GTK app)
  cli.py                       # thin typer CLI on top of api.py
  adapters.py                  # subprocess call + adapter contract
  classes.py                   # GM pitch → class mapping (5/3 classes)
  datasets/mdb.py, own.py      # loaders → unified reference (onsets per class)
  align.py                     # score beats → audio beats
  evaluate.py                  # mir_eval metrics
  report.py                    # CSV + HTML
  notation.py                  # quantization + MusicXML
config/benchmark.yaml          # active separators/transcribers/datasets
config/classes.yaml            # mapping table
adapters/separators/<id>/      # pyproject.toml + run.py + README.md (source, license, version)
adapters/transcribers/<id>/
adapters/beats/beat_this/
adapters/_common/             # shared helpers: device selection, meta.json, timing
references/own/<song>.yaml                 # title, path to recording, manual exclusions
data/own/<song>/score.mid, aligned.json, click.wav   # score (musescore.com) and alignment, not in the repo
tests/                         # pytest, mirrors src/stickler/
docs/adr/                      # Architecture Decision Records
data/ cache/ results/          # gitignored
```

**Adapter contract** (binding):
```bash
uv run --project adapters/<stage>/<id> python adapters/<stage>/<id>/run.py --in <audio> --out <dir>
```
- Separator → `<dir>/drums.wav`
- Transcriber → `<dir>/drums.mid` (GM drum pitches, channel 10)
- Beats → `<dir>/beats.json` (`{"beats": [...], "downbeats": [...]}`)
- All → `<dir>/meta.json` (`{"adapter", "version", "device", "seconds", "peak_rss_mb"}`)
- Options: `--device auto|cpu|gpu`
- Exit code ≠ 0 means error. The harness logs it and keeps going.
- Optional in the adapter `pyproject.toml`:
  - `[tool.stickler] input = "stem"`: The transcriber only accepts separated drum stems and is not combined with `none` (e.g. ADT_STR).
  - `[tool.stickler.rocm]`: GPU variant (ADR 0003).
- `config/benchmark.yaml` → `timeout`: time limit per adapter call. Exceeding it counts as a "time limit" error.
  Per stage, either fixed seconds (`separators: 1800`) or relative to the audio duration
  (`transcribers: {factor: 10, min: 120}` = 10 × song length, at least 120 s; duration via `ffprobe`).

**Own songs (reference and quality criteria):**
- Score as MIDI from musescore.com (repeats written out); `stickler align` lays it onto the recording via Beat This! and the rhythm patterns of the Demucs stem, using DTW (`src/stickler/align.py`).
- Not scored: audio with no counterpart in the notes, gaps in the score where the audio contains playing (≥ 1 bar), manual exclusions from the YAML. Notes in these areas count neither for the reference nor for the models.
- A song only enters the benchmark if it meets all criteria (user requirement: only at least good references). Checked without a transcription model, using onsets from the spectral flux of the Demucs stem (detector lead of 11 ms, measured on MDB and corrected):

| Criterion | Threshold | Calibration on MDB (correct references, Demucs stem) |
|---|---|---|
| Paired note beats that sit within ±70 ms of a Beat This! beat | ≥ 95% | – |
| Note hits with an onset in the stem (±50 ms) | ≥ 85% | median 98%, worst 88.5% |
| Clear onsets (strongest 20%) with a note hit (±50 ms) | ≥ 90% | median 100%, worst 92% |
| Evaluated music: first to last reference note, minus excluded regions | ≥ 120 s | – |

Score passages without a counterpart in the recording (e.g. repeats the transcriber added) are dropped from the reference and reported for information only. They are no reason to fail (owner's rule, 2026-11-12). The share of clear onsets in excluded regions is also info only. If the automatic checks are fooled (e.g. bass bleeding into the Demucs stem of a ballad), the owner may approve a song after listening to its `click.wav`: `approved_by_ear: "<reason>"` in the song's YAML. Failed checks stay visible in `aligned.json`.

## Code Style
ruff with default rules and line length 100. Type hints throughout, `dataclass`es instead of dicts for domain objects, no global state. Code, comments, docstrings, user-facing messages and documentation in English (since 2026-11-12); the project owner is addressed in German.
```python
@dataclass(frozen=True)
class Onsets:
    """Onset times in seconds per instrument class."""

    by_class: dict[str, np.ndarray]


def score(ref: Onsets, est: Onsets, window: float = 0.05) -> dict[str, PRF]:
    """Precision/recall/F1 per class according to mir_eval.onset (default: ±50 ms)."""
    return {
        cls: PRF(
            *mir_eval.onset.f_measure(ref.by_class[cls], est.by_class.get(cls, EMPTY), window)
        )[::-1]
        for cls in ref.by_class
    }
```

## Testing Strategy
- **pytest**, tests under `tests/`, test first (red → green → refactor).
- Unit tests without models or network: `classes`, `evaluate`, `align`, `notation`, dataset loaders (with mini fixtures in `tests/fixtures/`).
- Adapter smoke tests (`pytest -m adapters`, not in the default run): 10 s test audio; checks for valid MIDI and `meta.json`.
- Coverage ≥ 95% for `src/stickler/` except `cli.py`.

## Boundaries
- **Always:** number releases sequentially (1, 2, 3 …, tag `vN`, ADR 0006); tests before every commit; one commit per task; the source (official README/paper, version/commit hash) in the adapter README; document the license of every model.
- **Ask first:** new harness dependencies; adding or removing a model candidate; changing scoring parameters (tolerance window, class mapping); larger downloads (> 2 GB).
- **Never:** commit audio, datasets or model weights; use proprietary or closed-source services; weaken or skip tests to make them pass; use the archived facebookresearch/demucs.

## Success Criteria
1. `evaluate`: a reference compared against itself yields F1 = 1.0. An onset shifted by 60 ms counts as an error; one shifted by 40 ms counts as a hit.
2. For all 23 MDB Drums tracks, every active separator × transcriber combination yields a MIDI file or a logged error with its cause.
3. `results/metrics.csv` and `results/report.html` contain, per combination and dataset: P/R/F1 per class (5- and 3-class), micro and macro F1, runtime, RTF and peak RAM, plus a ranking.
4. At least one own song passes the quality criteria (click-check WAV present, checked by ear by the user) and is included in the report.
5. `stickler notate` produces MusicXML for an own song that opens in MuseScore 4 without errors and contains the time signature and drum notation.
6. A dummy adapter can be integrated with a new folder and a config entry without changes to `src/` (verified by a test).
7. A second `run` without changes recomputes nothing (cache hits).
8. `stickler doctor` detects the Radeon 840M. At least the Torch adapters (Demucs, RoFormer, ADT_STR, MuScriptor) run with `--device gpu`. Results deviate from CPU runs by at most 0.01 F1. CPU vs. GPU runtimes are shown in the report.
9. The CLI contains no logic beyond argument parsing and output. Everything runs through `stickler.api` (verified by a test), so the GTK interface can build on it later.

## Release 3: Error analysis (honest numbers)

> Status: **done**, released as release 3 on 2026-11-14 (approved by the owner on 2026-11-14,
> blind judgement included).

### Objective
**Honest numbers for Fast and Quality.** The F1 values on the own songs count every
disagreement with the reference as a model error, but the references are third-party
transcriptions, aligned automatically. Release 3 estimates how much of the measured error is
really the reference's, and reports Fast and Quality with that taken into account.

User stories:
- As the owner, I want to know how good Fast and Quality really are on my music, not only how
  well they agree with musescore.com transcriptions.
- As the owner, I want to see what kind of errors the models make per drum (missed, invented,
  confused with another drum, slightly off time), so the numbers can be read correctly.
- As the owner, I want to judge a sample of error spots by ear in about an hour, without
  knowing whether the reference or the model claims the hit.

Scope: the 25 own songs, Fast (`none+adtof`) and Quality (`combo+quality`). Not in scope:
changing references or the scoring (±50 ms, 5 classes), new models, MDB/ENST (they have
studio-exact references).

### Method
1. **Error breakdown per song, pipeline and class.** Every false negative (reference hit
   without a match) and false positive (estimated hit without a match) from `evaluate.score`
   gets exactly one category, in this order:
   - *confused*: a false negative of class A and a false positive of class B ≠ A within ±50 ms
     (one-to-one, like mir_eval's matching); counted as a pair A → B;
   - *off time*: a false negative and a false positive of the same class 50–100 ms apart;
   - *missed* (remaining false negatives) and *invented* (remaining false positives).
   The categories add up exactly to fn and fp of `evaluate.score`.
2. **Sample of spots, drawn once before listening.** A spot is (song, time, class, side):
   side `ref` = the reference claims a hit the pipeline did not find, `est` = the pipeline
   claims a hit the reference does not have. Spots come from the union of the Fast and
   Quality errors (they share hi-hat and cymbals). 100 spots: per class 10 `ref` and
   10 `est`, uniform at random, fixed seed, random order. The sample is never redrawn after
   listening.
3. **Blind judgement.** For each spot the owner hears a ~4 s snippet (drum stem and mix around
   the spot, once plain and once with a click at the moment in question) and, as often as
   needed, a 1.25 s loop of just the spot, also at half speed. The music is on the left
   channel, the click alone on the right, as in `align`'s click.wav (trial on 2026-11-14: a soft
   marker mixed into the music was inaudible; the loop at half speed made the spot judgeable).
   Owner's wish after the trial: every spot starts right away as the half-speed loop and runs
   until the answer; the passage (r) and normal speed (l) stay available.
   The owner answers one question: "Is there a <class> hit at the marker?" — *yes*, *no* or
   *unclear*. The owner is not told whether reference or model claims it.
4. **Correction.** A `ref` spot judged *no* and an `est` spot judged *yes* are reference
   errors. Per class, the shares of reference errors among `ref` and `est` spots
   (r_ref, r_est) correct the counts of each pipeline: fn' = fn · (1 − r_ref),
   tp' = tp + fp · r_est, fp' = fp · (1 − r_est). Reported: measured F1, corrected F1 with a
   95 % bootstrap interval over the verdicts, and the share of *unclear* (not counted; bounds
   with *unclear* counted either way). Shares come only from the spots in a pipeline's own
   error set.
5. **Known limit, stated in the report:** hits where reference and model are wrong in the same
   way (both claim a hit that is not there) are invisible to this method; with ~10 spots per
   class and side, per-class intervals are wide (about ±30 points), the pooled estimate is
   about ±10 points.

### Commands
```bash
uv run stickler errors --config config/own.yaml   # breakdown → results/own/errors.csv + table
uv run stickler listen                            # draw the sample once, then judge spot by spot
                                                  # (each spot loops at half speed until the
                                                  #  answer y / n / u; r = whole passage,
                                                  #  l = normal speed, s = half speed again,
                                                  #  q = quit; resumes where it stopped)
uv run stickler eval --config config/own.yaml     # also writes the corrected scores once
                                                  # verdicts exist → results/own/corrected.csv
uv run stickler report                            # report.html shows breakdown and corrected F1
```
Snippets are played with `ffplay` (part of ffmpeg, already required); no new dependencies.

### Project structure (additions)
```
src/stickler/errors.py         # categorise errors, draw the sample, correct the counts
src/stickler/listen.py         # snippets (drum stem + mix + marker) and the judging loop state
src/stickler/api.py            # error_breakdown(), draw_sample(), record_verdict(), corrected_scores()
src/stickler/cli.py            # `errors`, `listen` (thin, as always)
tests/test_errors.py, tests/test_listen.py
data/own/_listening/sample.csv    # the drawn spots (gitignored, never redrawn)
data/own/_listening/verdicts.csv  # the owner's answers (gitignored)
data/own/_listening/*.wav         # snippets of commercial recordings (gitignored, never published)
docs/report.md                    # new section "Errors and reference quality"
```

### Code style
As in the rest of the harness, e.g.:
```python
@dataclass(frozen=True)
class Spot:
    """One error spot to judge by ear: does `cls` have a hit at `time` in `song`?"""

    song: str
    time: float
    cls: str
    side: Literal["ref", "est"]  # who claims the hit: the reference or a pipeline
    pipelines: frozenset[str]  # pipelines whose error set contains this spot
```

### Testing strategy
- Unit tests with synthetic onsets: every category, the one-to-one pairing of confusions, the
  categories summing to fn/fp of `evaluate.score`, the seeded sample (same seed → same spots,
  10/10 per class and side, union of pipelines), the correction formula on hand-computed
  counts, resuming a half-judged sample.
- `listen`: snippet cutting and marker placement tested on a generated WAV; the playback
  command is injected, so tests never play sound.
- Coverage stays ≥ 95 % (CONSTRAINTS.md).

### Boundaries
- **Always:** draw the sample before listening and keep it; judge blind; report measured and
  corrected F1 side by side, never the corrected value alone; state the limits.
- **Ask first:** changing the sample size or the categories after listening has started; using
  verdicts for anything beyond the estimate (e.g. as exclusions, which would change the
  scoring).
- **Never:** commit snippets, verdicts or reference data; change references or metrics.csv
  because of verdicts.

### Success criteria
1. `stickler errors` writes `results/own/errors.csv` for Fast and Quality; per song and class,
   confused + off time + missed = fn and confused + off time + invented = fp (test and a check
   over all 25 songs).
2. `stickler listen` draws 100 spots (10 `ref` + 10 `est` per class), reproducibly, and resumes
   after quitting; the owner has judged all of them.
3. `results/own/corrected.csv` and the report show, for Fast and Quality: measured and corrected
   macro-F1 and per-class F1 with 95 % intervals, and the share of *unclear*.
4. `docs/report.md` has a section with the breakdown (largest error sources, top confusions)
   and the corrected numbers; section 1 ("In short") quotes measured and corrected values.
5. Existing results are unchanged: `results/own/summary.csv` is identical before and after.

### Gamification of `stickler listen` (owner's wish, 2026-11-14)

> Status: **approved** by the owner on 2026-11-14; part of release 3. The owner starts listening only once the badges are in (Task 29).

**Objective.** Judging 100 spots takes about an hour; badges and a finale make it fun to keep
going. Owner's choice: badges and a big finale, in drummer humour like the README's nonsense
badges (no ranks, sets or streaks).

**Rule above all: the game must not bias the verdicts.**
- Rewards depend only on *that* spots were judged, on time of day, sessions and replays chosen
  on purpose (r, l, s), never on *what* was answered (yes, no, unclear), never on speed.
- Built so by construction: the reward code reads an events log that records "spot n judged",
  "spot replayed on purpose", "session started" with a timestamp, but no answer.
- No feedback per spot (nobody knows the truth, and it would reveal who claims the hit) and no
  interim results; numbers only in the finale, after spot 100.

**Badges** (English, like all messages; shown as a small ASCII banner when earned; `q` and the
end list the collection, e.g. "7 of 11 badges"):

| Badge | Earned when |
|---|---|
| `first hit` | the first spot is judged |
| `warmed up` | 10 spots |
| `quarter note` | 25 spots |
| `neighbours: annoyed` | 50 spots |
| `three-quarter time` | 75 spots |
| `encore` | all 100 spots |
| `night shift` | a spot judged between 0:00 and 5:00 |
| `early bird` | a spot judged between 5:00 and 7:00 |
| `second opinion` | the first spot replayed on purpose (r, l or s) |
| `loop pedal` | 10 replays on purpose in total |
| `comeback tour` | a session on a later day than the previous one |

**Big finale** (after spot 100, and on every later `stickler listen`): a "showdown" of Fast
against Quality with measured and corrected macro-F1 and the per-class winners (needs Task 27),
followed by the full badge collection. After the finale the README's nonsense row gets the badge
`ears: certified` (scripts/badges.py).

**Files.** `src/stickler/rewards.py` (pure: events → earned badges, banner texts),
`data/own/_listening/events.csv` (gitignored), `api.py` (record events, earned badges, finale
data), `cli.py` (banners and finale output only), `tests/test_rewards.py`.

**Testing.** Unit tests for every badge rule with synthetic events (times, days, counts); a test
that `rewards` cannot see verdict values (it only receives events, and events have no answer
field); CliRunner tests for a banner and the finale with a fake API.

**Boundaries.**
- Always: the rule above; badges are earned once and never lost.
- Ask first: any reward that depends on answers, speed or results.
- Never: interim results or per-spot feedback; publishing events or verdicts.

**Success criteria.**
1. Each of the 11 badges is earned exactly at its trigger (tests) and shown once.
2. Nothing in `rewards.py` or `events.csv` can depend on a verdict (test and code review).
3. After spot 100, `stickler listen` shows the showdown with measured and corrected values and
   the collection; the README carries `ears: certified`.

### Resolved questions
1. **Blind judgement** (step 3) instead of hearing reference and model clicks side by side:
   approved by the owner on 2026-11-14. It keeps the owner from favouring either side and lets
   one verdict serve both pipelines.

## Decisions (ADRs)
- [0001 Demucs via the fork adefossez/demucs](docs/adr/0001-demucs-fork.md)
- [0002 NC licenses allowed](docs/adr/0002-nc-lizenzen.md)
- [0003 GPU via AMD ROCm wheels](docs/adr/0003-rocm-kanal.md)
- [0004 RoFormer checkpoint BS-Roformer-SW](docs/adr/0004-roformer-checkpoint.md)
- [0005 YourMT3+ variant PS](docs/adr/0005-yourmt3-variante.md)
- [0006 Sequential version numbers](docs/adr/0006-versionierung.md)

## Resolved Questions
1. MuScriptor: the user accepts the license on Hugging Face and logs in with `uvx hf auth login`.
2. ENST Drums: I draft the application, the user submits it. Until the data is available, MDB and the own songs are used.
3. RoFormer checkpoint: chosen while building the adapter, recorded as an ADR.
4. Report: local HTML file.

## Open Questions
- none
