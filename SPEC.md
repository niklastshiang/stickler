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
- Python **3.12** and `uv` ≥ 0.13 (Homebrew). Every environment is managed with `uv`. The harness also runs on 3.13 and 3.14 (since 2026-11-14, for the GTK app, whose bindings use the system's or the GNOME runtime's Python); `.python-version` keeps 3.12 the default for development, and the adapters stay on 3.12.
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
> Now specified module by module under [GTK application](#gtk-application); the notes below are the original wishes.

- GTK 4 + libadwaita via PyGObject, separate package `stickler-gtk` that only uses `stickler.api`.
- For this to work, v1 needs: a public API in `stickler/api.py` (`run_benchmark`, `evaluate`, `transcribe_song`, `notate`) with progress callbacks and cancellation support, no `print`s in the logic (logging instead), and results as data objects, not only as files.
- **Design together first:** before any GTK code, the owner and Claude design the interface together, following current design principles, above all the GNOME Human Interface Guidelines (libadwaita patterns, adaptive layout, accessibility). Mockups first, then implementation.
- Features requested by the owner:
  - **Two modes instead of a model choice:** "Fast" and "Quality" (pipelines decided after the benchmark).
  - **Readable sheet music:** fold repeated bars and passages into repeat signs (done in the command line tool for release 2: `notate` simplifies nearly equal bars and writes repeat signs; `--no-simplify`, `--no-repeats`).
  - **Beams in the MusicXML (owner, 2026-11-14):** `notate` writes beams itself, one group per beat and voice, for every reader of the file. Verovio, the candidate for showing the sheet inside the app (`docs/ideas/gtk-music-stand.md`), does not beam on its own; MuseScore follows the written beams.
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

## GTK application

> Status: capability map **approved** by the owner on 2026-11-14. Module specs are written and
> approved one at a time, in build order. Idea and Verovio test:
> [docs/ideas/gtk-music-stand.md](docs/ideas/gtk-music-stand.md).

A single-window GTK 4 + libadwaita app for drummers who are not technical: drop a song, read the
sheet music in the app, hear the detected hits over the song, correct lightly, export. Fast mode
only in its first version.

### Capability map

| Module id | Responsibility | Depends on | Spec |
|---|---|---|---|
| `engine-api` | Additions to `stickler.api`, no GTK: progress and cancellation for `transcribe_song`, `notate` and `setup_adapters`; song bar → written bar map; correction parameters; audio of the detected hits | – | approved, below |
| `design` | Mockups of every screen, made with the owner, following the GNOME HIG; no code | – | approved, below |
| `app-shell` | Window, open or drop a song, analysis with a step display, export (MusicXML, drum track; PDF with `sheet-view`), recent songs | `engine-api`, `design` | done, below |
| `sheet-view` | Sheet music in the app (Verovio → SVG → librsvg), bar marker, tempo and artist in the window; PDF export through Verovio | `app-shell` | done, below |
| `playback` | Play the song: original / detected / both; the position drives the marker | `sheet-view`, `engine-api` | approved, below |
| `corrections` | Side panel with the light corrections; re-engraves | `sheet-view`, `engine-api` | – |
| `setup-assistant` | Consent, download of the Fast models with progress, resumable | `app-shell`, `engine-api` | – |
| `packaging` | Flatpak and AppImage with every release | all | – |

Build order: `engine-api`, `design` (in parallel) → `app-shell` → `sheet-view` → `playback`,
`corrections` → `setup-assistant` → `packaging`.

Out of order on purpose: the Flatpak sandbox trial (can `uv` build a model environment inside
the sandbox?) belongs to `packaging` but runs early, because a failure changes `setup-assistant`.

### Decisions for all modules (owner, 2026-11-14)

- **No GTK code before `design` is approved.** `engine-api` is library work and may run in
  parallel.
- **Languages:** English and German in the first version; strings are translatable from the
  start. How translations are contributed and kept up to date later needs its own answer (no
  outside pull requests today); it is specified in `app-shell`.
- **Coverage:** the app's logic is kept apart from its widgets and falls under the 95% rule;
  pure widget code is excluded like `cli.py`. CONSTRAINTS.md is extended accordingly when
  `app-shell` fixes the paths.
- **Scope:** everything under "Not Doing" in the idea one-pager stays out (Quality mode, editing
  single hits, practice tools, a song library, doubtful-bar marks, developer commands, macOS,
  Flathub).

### Module `engine-api`

> Status: **done**, released as release 4 on 2026-11-14 (approved by the owner on
> 2026-11-14). Plan: `tasks/plan.md` ("GTK application:
> `engine-api`"), tasks 31–40 in `tasks/todo.md`.

#### Assumptions

1. The app calls `stickler.api` in a worker thread of its own process. Callbacks are called on
   that thread; handing them to the GTK main loop is the app's job.
2. The harness can run on the Python the GTK bindings use. Today it is pinned to 3.12, while
   PyGObject on the development machine exists for the system Python 3.14 only, and the GNOME
   Flatpak runtime brings its own Python. The harness pin is widened to 3.12–3.14: a trial
   run of the test suite on 3.14 passed (2026-11-14; 461 of 462, the one failure came from the
   trial not installing the package). The adapters stay on 3.12 in their own environments:
   they run as subprocesses, so the app's Python does not matter to them, and raising them
   would change every cache key and require the benchmark to be recomputed.
3. Nothing in `adapters/*/run.py`, `setup.py` or `pyproject.toml` changes, so no cache key
   changes and no rekeying is needed.
4. Corrections are parameters of notation only. They never rerun a model: the transcription is
   cached, so every correction costs well under a second.
5. The detected hits are heard as clicks (three pitches: kick, snare/toms, cymbals, as in
   `align`'s click track). Drum samples are a later decision.
6. Where an installed app keeps environments, weights and cache (today: inside the checkout) is
   not part of this module; it is specified in `setup-assistant` and `packaging`.

#### Objective

Give the app everything it needs from the library, so that no GTK module has to reach around
`stickler.api`. Each addition is usable and testable from Python without a display.

1. **Progress.** `transcribe_song`, `notate` and `setup_adapters` accept a `progress` callback.
   The steps of a call are announced up front, then each step reports `started` and `done`
   (with `cached` when nothing had to be computed). Step ids are stable and not translated:
   `separate`, `transcribe`, `beats`, `engrave`, `pdf`; for setup `environment:<adapter>` and
   `weights:<adapter>`.
2. **Cancellation.** The same three functions accept a `cancel` token. Setting it ends the
   running adapter or setup process with its whole process group and raises `Cancelled`. A
   cancelled step leaves no cache entry behind that a later run would take for a result.
3. **Readiness.** `mode_ready("fast")` returns the adapters of a mode that are not set up yet
   (empty: ready), so the app knows when to show the setup assistant. A model missing at
   analysis time raises `SetupMissing` naming those adapters, instead of a failed subprocess.
4. **Bar map.** `notate` also returns, for every bar of the song in played order, its start and
   end in seconds and the number of the written bar it is engraved as (several song bars share
   one written bar inside repeat signs; a multi-bar rest maps to its first written bar).
5. **Corrections.** `notate` accepts `Corrections`: `tempo` (`half`, `normal`, `double`),
   `beats_per_bar` (override of the detected meter), `first_downbeat` (which beat is "one",
   which also sets the pickup), next to today's `simplify` and `repeats`.
6. **Detected hits as audio.** `render_hits(transcription, dest)` writes a mono WAV as long as
   the song with one click per detected hit. The app mixes it with the song.

Not part of this module: byte-exact download progress, any change to models or pipelines,
persistence of a song's corrections, Verovio, audio playback.

#### Commands

```bash
uv run pytest -q tests/test_api.py tests/test_notation.py tests/test_adapters.py   # this module's tests
uv run --python 3.14 pytest -q          # the harness on the GTK bindings' Python
scripts/check.sh fast                   # after changes
scripts/check.sh task                   # before every commit
uv run stickler notate song.flac        # unchanged for the user; prints the steps as they run
```

#### Project structure (additions)

```
src/stickler/api.py        # Step, Progress, CancelToken, Cancelled, SetupMissing, Corrections,
                           # BarTime; mode_ready, render_hits; new parameters on the three functions
src/stickler/notation.py   # bar map next to the MusicXML; tempo, meter and downbeat corrections
src/stickler/adapters.py   # process groups end on cancel (today: on timeout only)
src/stickler/cli.py        # notate and setup print the steps (still no logic)
tests/test_api.py, test_notation.py, test_adapters.py
```

#### Code style

As the rest of the harness: frozen dataclasses for results, keyword-only options, no `print` in
the library. The shape the app will use:

```python
cancel = api.CancelToken()


def on_step(step: api.Step) -> None:  # called on the worker thread
    log.info("%s %d/%d %s", step.id, step.index, step.total, step.state)


result = api.notate(
    song,
    pdf=False,
    corrections=api.Corrections(tempo="half", first_downbeat=2),
    progress=on_step,
    cancel=cancel,
)
bar = next(b for b in result.bars if b.start <= position < b.end)
marker.show(bar.written)
```

#### Testing strategy

- Test first, without models or network, with the dummy adapters the existing tests use.
- Progress: the announced steps equal the reported ones, in order, for Fast, for a pipeline with
  a separator and for a fully cached song.
- Cancellation: a dummy adapter that sleeps is cancelled; the call raises `Cancelled` within a
  second, no process of its group survives, and a second run computes the step again.
- Bar map: built for the songs the notation tests already use (with and without repeats, with a
  pickup, with a multi-bar rest); expanding the written bars along the map gives back every
  song bar.
- Corrections: `half` then `double` returns the original grid; an overridden meter and downbeat
  produce the expected bars; the hits themselves never change.
- `render_hits`: length equals the song's, energy sits at the hit times.
- Coverage stays ≥ 95% for `src/stickler` (CONSTRAINTS.md unchanged by this module).

#### Boundaries

- **Always:** keep `stickler.api` the only entry point; keep every existing call working without
  the new parameters; SPEC before code; one commit per task.
- **Ask first:** widening the Python pin if anything but the version line has to change; new
  harness dependencies; any edit to an adapter's `run.py`, `setup.py` or `pyproject.toml`.
- **Never:** import GTK, Verovio or an audio player in `src/stickler`; change what a model
  computes or how results are cached; weaken a test or CONSTRAINTS.md.

#### Success criteria

1. `notate` on a cached own song with a `progress` callback reports the announced steps in
   order, each `started` then `done`, all marked `cached`; the CLI prints them.
2. Cancelling a running dummy adapter raises `Cancelled` within 1 s, leaves no process behind
   and no cache entry; the next run succeeds.
3. `mode_ready("fast")` lists `adtof` and `beat_this` in a checkout without environments and
   is empty after `stickler setup --adapter adtof` and `--adapter beat_this`.
4. For Eye of the Tiger the bar map has one entry per song bar (110), its times rise without
   gaps, and its written bars are exactly the bars the score shows: the MusicXML has 46
   `<measure>` elements, of which the first four are one multi-measure rest, so 43 bars
   (Verovio's MEI has the same 43; checked 2026-11-14, Task 37). Collapsing the rest's four
   entries into one gives Verovio's expanded timemap in the same order (107 entries).
5. Each correction changes the notation of a cached song in under 1 s on the development
   laptop, without starting an adapter (verified by a test that fails if one is started).
6. `render_hits` for a cached own song yields a WAV whose clicks, played with the song, sit on
   the drums (checked by ear by the owner on one song).
7. The harness test suite passes on Python 3.12 and 3.14, and the pin in `pyproject.toml` says
   so.
8. Every existing test passes unchanged; `scripts/check.sh task` is green.

#### Resolved questions (owner, 2026-11-14)

1. **Setup progress in bytes:** this module reports steps only. `setup-assistant` later shows
   bytes on disk against the sizes in `docs/requirements.md`.
2. **Resuming an interrupted setup:** measured on 2026-11-14 (Task 32) on a copy of
   `beat_this` with its own empty uv cache, killed with SIGKILL (the worst case: power cut, or
   cancelling as Task 34 will):
   - **`uv sync`** (fresh: 13 s here, 0.86 GB, of which the PyTorch CPU wheel is 0.75 GB).
     Killed after 3 s and after 7 s, a second `setup` succeeds (7–8 s) and leaves a working
     environment and a clean uv cache. Packages finished before the kill are reused; a package
     being downloaded starts over, so on a slow line an interruption can cost the whole
     PyTorch download again. Acceptable; no fix needed.
   - **Weights via `torch.hub`** (`beat_this`; ADTOF's weights ship in its package). The JKU
     server was down during the test (HTTP 500 on every file, share page up), so the download
     was rerun against a throttled local server with the same `torch.hub` call: a kill leaves
     `<file>.<id>.partial` behind, which is never removed, and a second run downloads the whole
     file again. Acceptable for 80 MB; the stray file is cleaned up by `setup`.
   - **Readiness is misjudged** after an interruption. `doctor` calls an adapter ready when
     `.venv` exists and `weights/` is not empty. A killed `uv sync` leaves a `.venv` without
     packages, and a failed or killed download leaves `weights/hub/checkpoints/` with no
     checkpoint or only a `.partial`, both of which pass. `uv sync --check --offline` tells a
     broken environment from a complete one (exit 1 / 0, 16 ms). Weights count only when
     `setup.py` has finished: the harness writes a marker after it succeeds. Both go into
     Task 35, and `doctor` uses the same check.
   - **The weights' host can be down.** First-run setup depends on third-party servers
     (`cloud.cp.jku.at` for Beat This!, Hugging Face for others). `setup-assistant` must say
     which server failed and offer to retry; whether to mirror the Beat This! checkpoint
     depends on its licence (not checked).
3. **Python:** the harness is widened to 3.12–3.14 now. Raising the adapters is planned for the
   future (`tasks/todo.md`, "Later"), together with a benchmark rerun, because it changes every
   cache key.

#### Open questions

- Which Python the GNOME runtime ships at the time of `packaging` is not checked yet; the
  3.12–3.14 range covers the development machine and is widened again if needed.

### Module `design`

> Status: **approved** by the owner on 2026-11-14. Mockups: [docs/design/](docs/design/README.md)
> (sources of the design canvas; the owner's canvas is the live copy).

Mockups of every screen, made with the owner in two rounds. No code. The GTK modules build what
is drawn here; a change of a screen is agreed on the canvas first and copied to `docs/design/`.

#### Screens

| # | Screen | Module |
|---|---|---|
| 1 | First start: consent (what is downloaded, sizes, ADTOF's non-commercial licence) | `setup-assistant` |
| 2 | First start: download with the setup steps | `setup-assistant` |
| 3 | First start: a server is not answering (names the server, keeps what is done, retry) | `setup-assistant` |
| 4 | Empty window: drop area, "Open a Song…", recent songs | `app-shell` |
| 5 | Analysis: the steps of Fast, cancel | `app-shell` |
| 6 | Sheet music with the bar marker; playback bar with position, bar number, Song / Hits / Both, volume | `sheet-view`, `playback` |
| 7 | Corrections in a sidebar | `corrections` |
| 8 | Export menu and the "saved" toast | `app-shell` |
| 9 | Main menu with the appearance switch | `app-shell` |
| 10, 11 | Narrow window (400 px): sheet music; corrections as a bottom sheet | all of the above |

#### Decisions (owner, 2026-11-14)

- **Look:** GNOME HIG with libadwaita widgets and colours (accent blue, boxed lists, pill
  buttons, toggle groups); no colours or styles of our own.
- **Appearance:** follows the system by default; the main menu has the three-way switch
  (follow system, light, dark), as GNOME's own apps do. No preferences window for it.
- **App icon (owner, 2026-11-15):** draft B, a page of drum notation with two drumsticks crossed
  over it, drawn to the GNOME HIG (128 px, a darker bottom profile, palette colours, a symbolic
  variant): `packaging/icons/`. Its parts are separate layers (paper, staff, notes, sticks), so a
  macOS icon (square layers on a background, masked to a rounded rectangle by the system) can
  reuse them; other platforms' variants are made when a release for them comes.
- **Note size (owner, 2026-11-15):** a "−  100 %  +" row under the appearance switch in the
  main menu, as in GNOME Text Editor; the percentage resets to the window's width. The size
  holds for every song and is remembered. Still no preferences window.
- **Sheet music in dark mode is inverted** (light notes on a dark page, the bar marker stays
  blue), as music readers such as forScore do it; in light mode the page is white.
- **Tempo and time signature stand in the window title**, not on the page (librsvg cannot draw
  Verovio's tempo glyph, see the idea one-pager).
- **Corrections are a sidebar** next to the sheet (a bottom sheet in a narrow window), grouped
  "Beat" (tempo half / as detected / double, beats per bar, first "one") and "Easier to Read"
  (simplify, repeat signs), with "Back to Detected".
- **Playback:** what to hear is Song / Hits / Both; a volume button opens one slider for the song
  and one for the detected hits.
- **Export menu (owner, 2026-11-15):** MusicXML keeps a line on what it is for; the drum track's
  line names only the format ("As FLAC or WAV"), its name says the rest.
- **Export of the drum track announces its cost** before it starts: Fast does not separate the
  drums, so the export runs Demucs (CPU: about 1.84× the song's length) and downloads it once
  (about 1.2 GB).
- **Narrow windows** are part of v1: the header keeps icon buttons only, the playback bar takes
  two rows, the corrections become a bottom sheet.
- **One step list** for setup and analysis: done, running, waiting, each with a short line of
  what it does; model names appear only in setup.
- **Copy:** English source strings, written for drummers, not for developers; German comes
  through translation (`app-shell`).

#### Open questions

- Keyboard shortcuts (play/pause, next/previous bar, open, export) are listed in the main menu
  but not designed; `app-shell` defines them.
- The app icon (GNOME style, `tasks/todo.md`) is not part of these screens.

### Module `app-shell`

> Status: **approved** by the owner on 2026-11-14. Plan: `tasks/plan.md` ("GTK application:
> `app-shell`"), tasks 41–48 in `tasks/todo.md`.

#### Assumptions

1. **App ID `ng.tshia.Stickler`** (the owner's domain `tshia.ng`, owner's choice 2026-11-14). It
   names the desktop file, the settings and later the Flatpak. Flathub would ask to verify the
   domain (a token under `https://tshia.ng/.well-known/`); our own Flatpak does not.
2. **Same repository, own package:** `src/stickler_gtk/` next to `src/stickler/`, started with
   `stickler-gtk`. It calls only `stickler.api`; `src/stickler` stays free of GTK.
3. **GTK comes from the system, not from PyPI.** PyGObject, GTK 4 and libadwaita need the
   system libraries and typelibs. In development the app runs on the system Python 3.14
   (GTK 4.22, libadwaita 1.9, GStreamer 1.28, librsvg, pycairo, checked 2026-11-14) in its own
   environment `.venv-gtk`, made with `--system-site-packages`; in the Flatpak the GNOME
   runtime provides them (runtime 51: Python 3.14.9, libadwaita 1.10). Minimum libadwaita: 1.8
   (the shortcuts dialog, which replaces the deprecated `Gtk.ShortcutsWindow`; toggle groups
   are 1.7, the bottom sheet 1.6).
4. **Logic apart from widgets:** `stickler_gtk/logic/` imports no GTK (window states, steps →
   labels, recent songs, export names and costs, settings) and falls under the 95% coverage
   rule; `stickler_gtk/ui/` holds the widgets and is excluded like `cli.py`. Widgets are built
   in Python (no Blueprint or `.ui` files, so no build step and one string extractor).
5. **Analyses run in a worker thread**; `progress` callbacks reach the window through
   `GLib.idle_add`. The main loop never waits for a model.
6. **The sheet music is not part of this module.** After an analysis the window shows the
   result page with title, artist, tempo and meter in the header and the export menu; the page
   body is a placeholder until `sheet-view`. The PDF export comes with `sheet-view`, made with
   Verovio (owner's decision 2026-11-14), so it needs no MuseScore.
7. **Where models and the cache live** is not decided here: `app-shell` reads both from one
   function (today: the checkout's folders), which `setup-assistant` and `packaging` change.
8. **Before `setup-assistant` exists**, a missing model (`api.SetupMissing`) shows a page that
   names the models and the `stickler setup` command.

#### Objective

The window around everything else: open or drop a song, watch the analysis, export the
results, come back to recent songs. For drummers who are not technical, in English and German,
in light and dark, wide and narrow (screens 4, 5, 8 and 9 of `design`).

1. **Open a song** by dropping it on the window or with "Open a Song…" (file chooser filtered
   to audio). Anything else dropped gives a toast ("Not an audio file").
2. **Analysis** in Fast mode with the step list (done, running, waiting) and "Cancel"; cancel
   returns to where the user came from. A cached song skips straight to the result.
3. **Errors** as pages, in the user's words: a model not set up, an analysis that failed
   (with "Try Again" and the technical message folded away), a file that cannot be read.
4. **Export** from the header's menu: MusicXML, and the drum track. The drum track names its
   cost first (about 1.84× the song's length on the CPU and a one-time download of about
   1.2 GB, as long as Demucs is not set up) and then runs as a step list with "Cancel". A toast
   says where the file went and offers "Open".
5. **Recent songs:** the last ten, newest first, on the empty window. A song whose file is gone
   is shown as missing and can be removed.
6. **Appearance:** follow the system, light or dark, chosen in the main menu and remembered.
7. **Languages:** every string goes through gettext; German is complete in the first version.
   The app follows the system's language, as GNOME apps do; there is no switch inside the app
   (owner, 2026-11-15). Starting it with `LANGUAGE=en` (or `flatpak run --env=LANGUAGE=en …`)
   overrides it.
   Translations come in through Weblate later (owner's decision 2026-11-14): Weblate commits
   `po/*.po` to the repository, so outside pull requests stay off.
8. **Keyboard:** every action is reachable by keyboard, and the shortcuts window lists them.
   GNOME HIG standard shortcuts (checked 2026-11-14): Ctrl+O open, Ctrl+W close the window,
   Ctrl+Q quit, Ctrl+? shortcuts, F10 main menu. Not in the HIG but common: Escape cancels an
   analysis or export, Ctrl+E opens the export menu (as in GIMP). Later modules use F9 for the
   corrections sidebar (HIG "side pane") and Space for play/pause.
9. **As few sandbox permissions as possible** (owner, 2026-11-14), so the code never needs more
   than the Flatpak grants:

   | Permission | Why | Module |
   |---|---|---|
   | `--socket=wayland`, `--socket=fallback-x11`, `--share=ipc` | Show a window (X11 only where there is no Wayland) | `app-shell` |
   | `--device=dri` | Drawing on the GPU; without it GTK draws on the CPU, slower | `app-shell` |
   | `--share=network` | Downloading the models on first start and Demucs for the drum track; the analysis itself runs offline | `setup-assistant` |
   | `--socket=pulseaudio` | Playback (PipeWire through its PulseAudio interface) | `playback` |

   No file system access: songs come in through the file chooser and drag and drop, which
   go through the document portal; exports go out through the save dialog; "Open" in a toast
   and opening a file in another app use the OpenURI portal. Models, environments and the
   cache stay in the app's own folder (`~/.var/app/ng.tshia.Stickler/`). No GPU compute
   (ROCm/CUDA would need `--device=all`): Fast takes about 15 s on the CPU. No access to other
   programs (no `flatpak-spawn --host`).

Not part of this module: the sheet music and the bar marker (`sheet-view`), playback and volume
(`playback`), the corrections sidebar (`corrections`), the setup assistant (`setup-assistant`),
the PDF export (with `sheet-view`), the app icon, Flatpak and AppImage (`packaging`).

#### Commands

```bash
scripts/gtk.sh                          # build .venv-gtk on the system Python if needed, start the app
LANGUAGE=de scripts/gtk.sh              # the app in German
scripts/gtk.sh test                     # widget smoke tests (pytest -m gtk) on the system Python
uv run pytest -q tests/gtk              # logic tests, no GTK needed (part of check.sh)
scripts/i18n.sh                         # strings → po/stickler.pot, merged into po/de.po
scripts/check.sh task                   # before every commit
```

#### Project structure (additions)

```
src/stickler_gtk/__init__.py
src/stickler_gtk/main.py           # Adw.Application ng.tshia.Stickler; entry point stickler-gtk
src/stickler_gtk/logic/            # no GTK: session.py (states), steps.py (labels), recent.py,
                                   # exports.py (names, costs), settings.py, paths.py
src/stickler_gtk/ui/               # window.py, pages (empty, analysing, result, error),
                                   # export_menu.py, shortcuts.py
po/stickler.pot, po/de.po            # scripts/i18n.sh finds the sources itself (git ls-files)
packaging/ng.tshia.Stickler.desktop   # later also metainfo, icon, Flatpak manifest
scripts/gtk.sh, scripts/i18n.sh
tests/gtk/                         # logic tests; test_widgets.py marked `gtk`
```

Recent songs and settings are JSON files under the XDG folders (`GLib.get_user_data_dir()` and
`get_user_config_dir()`, `stickler/`), which the Flatpak maps into its sandbox by itself.

#### Code style

As the harness: frozen dataclasses for state, no `print`, English identifiers and comments,
user-facing strings only through `_()`. The logic decides, the widgets show:

```python
# logic/session.py: no GTK import
@dataclass(frozen=True)
class Analysing:
    song: Path
    steps: tuple[StepRow, ...]  # label, detail, state: "done" | "running" | "waiting"


def on_step(state: Analysing, step: api.Step) -> Analysing:
    """The next state after a progress report; pure, tested without GTK."""


# ui/window.py
def _on_progress(self, step: api.Step) -> None:  # called on the worker thread
    GLib.idle_add(self._show, session.on_step(self._state, step))
```

#### Testing strategy

- Logic first and without GTK: state changes from `api.Step`, cancel and errors; labels for
  every step id; recent songs (order, limit, missing files, a damaged JSON file); export names
  and the drum track's cost from the song's length; settings. These run on Python 3.12 and 3.14
  in `check.sh` and count for coverage.
- Widgets: a few smoke tests marked `gtk` on the system Python (the window opens, each page
  shows, a fake `stickler.api` drives an analysis to the result); not part of the default run,
  like the `adapters` tests, because CI has no display.
- Translations: a test fails if a `.py` file under `stickler_gtk` has a string literal shown to
  the user without `_()`, or if `po/de.po` misses a string from `po/stickler.pot`.
- By hand on the development laptop: drop a cached and an uncached own song, cancel, export,
  German, dark, a 400 px window.

#### Boundaries

- **Always:** only `stickler.api` from the app; models only in the worker thread; every user
  string through `_()`; screens as in `design`, or agree the change on the canvas first.
- **Ask first:** any sandbox permission beyond the table in Objective 9; a new dependency
  (Blueprint, a GTK test library); changing the mockups; the
  CONSTRAINTS.md lines for `stickler_gtk` (proposed: logic in the 95% rule, `ui/` excluded).
- **Never:** import GTK in `src/stickler` or in `stickler_gtk/logic`; block the main loop;
  logic in widget code; strings shown to the user without translation; read or write a file
  outside the app's folder except through a portal (file chooser, drag and drop, save dialog).

#### Success criteria

1. `scripts/gtk.sh` opens the empty window (screen 4) on the development laptop; dropping or
   opening an uncached own song shows the analysis (screen 5) and ends on the result page; a
   cached song reaches it in under 1 s.
2. "Cancel" during an analysis returns to the previous page within 1 s, and no model process
   is left (as `engine-api` criterion 2).
3. Export of MusicXML and of the drum track writes the files; the drum track names its cost
   before it starts and can be cancelled.
4. Recent songs survive a restart, keep the newest ten, and a missing file can be removed.
5. The appearance switch works and is remembered; dark mode follows the system by default.
6. With `LANGUAGE=de` every visible string is German; the translation test passes.
7. At 400 px width every page of this module is usable without horizontal scrolling.
8. Every action works by keyboard; the shortcuts window lists them.
9. `scripts/check.sh task` is green, with `stickler_gtk/logic` at ≥ 95% coverage; no GTK
   import in `src/stickler` or `stickler_gtk/logic` (a test checks it).

#### Open questions

- The Weblate project is set up by the owner (account, access to the repository) when the
  first outside language is wanted; until then only German, translated in the repository.
- Whether recent songs can be reopened after a restart inside the Flatpak depends on the
  document portal keeping the access granted through the file chooser or drag and drop; to be
  checked in the early Flatpak sandbox trial (`packaging`). If it does not, a recent song
  whose result is cached still opens (the cache is the app's own), and only a new analysis
  asks for the file again.

#### Resolved questions (owner, 2026-11-14)

- "Open in MuseScore" (screen 8) moves to `sheet-view`, next to the PDF. It becomes "Open
  With…", the system's own app chooser (OpenURI portal) on the MusicXML file, which needs no
  permission; starting MuseScore directly from the sandbox would need access to the host.

### Module `sheet-view`

> Status: **approved** by the owner on 2026-11-15 (Verovio as a new dependency of the app
> included). Plan: `tasks/plan.md` ("GTK application: `sheet-view`"), tasks 49–54 in
> `tasks/todo.md`.

#### Assumptions

1. **Verovio 6.4.1** (PyPI, 2026-11-03; LGPL-3.0; actively maintained, last push 2026-11-12;
   `cp310-abi3` wheels, so one wheel serves Python 3.12 to 3.14) engraves the app's MusicXML
   into SVG pages. It is a dependency of the app only: a uv dependency group `app`, synced by
   default (so the logic tests run in CI) and by `scripts/gtk.sh`; `src/stickler` never imports
   it. Used unmodified through its Python module, as the LGPL allows; the About dialog names it.
2. **Drawing:** librsvg renders each SVG page into a widget; the bar marker is drawn on top with
   cairo. Bar rectangles come from the staff lines in Verovio's SVG, not from librsvg, whose
   rectangles are wrong for bars with dotted notes (Verovio test, idea one-pager).
3. **The marker follows song time:** a position in seconds → the song bar (`Notation.bars`) →
   its written bar number → that bar's measure in Verovio's output (a multi-measure rest is one
   measure, as the bar map already says). `playback` will drive it; in this module a click on a
   bar marks it, and the window exposes the position call for `playback` and the tests.
4. **The Leipzig font ships with the app** (owner, 2026-11-15), so librsvg draws Verovio's
   tempo mark: `Leipzig.ttf` from Verovio's tag `version-6.4.1` (SIL Open Font License) in
   `packaging/fonts/` with its licence. librsvg finds fonts through fontconfig only (checked
   2026-11-15: loading it into Pango's font map did not reach librsvg, nor did the WOFF2 inside
   Verovio's `Leipzig.css`; a font folder in fontconfig did). Development: `scripts/gtk.sh`
   copies it into `.venv-gtk/share/fonts` and points `FONTCONFIG_FILE` at a config that adds
   that folder; the Flatpak installs it to `/app/share/fonts`.
5. **Layout** (owner, 2026-11-15): pages one under the other, the page as wide as the window;
   Ctrl+plus, Ctrl+minus, Ctrl+scroll zoom, Ctrl+0 back to the window's width. Verovio lays the
   bars out anew for the width (a short pause after resizing, not on every pixel).
6. **Dark style:** the page is inverted (light notes on a dark page); the marker stays blue.
7. **PDF export** comes here (owner, 2026-11-14): Verovio's pages at A4, drawn with librsvg into
   a cairo PDF; no MuseScore. "Open With…" offers the system's app chooser for the MusicXML
   (OpenURI portal, no permission).

#### Objective

The result page shows the sheet music (design screen 6, without the playback bar, which is
`playback`): readable at any window width, in light and dark, with the bar marker, and exports
it as PDF.

1. After an analysis (or a correction, later) the page shows the engraved song; title, artist,
   tempo and meter stay in the header.
2. Width and zoom as in assumption 5; scrolling is vertical only.
3. A click on a bar marks it; the position call marks the bar sounding at a time and scrolls it
   into view when it is off screen.
4. The export menu gains "Sheet Music (PDF)…" and "Open With…" (design screen 8).

Not part of this module: playback and the volume (`playback`), the corrections (`corrections`),
printing directly (the PDF covers it).

#### Commands

```bash
scripts/gtk.sh                          # the app; now also installs the Leipzig font for it
uv run pytest -q tests/gtk              # logic tests, Verovio included, no GTK
scripts/gtk.sh test                     # widget tests (pytest -m gtk)
scripts/check.sh task                   # before every commit
```

#### Project structure (additions)

```
src/stickler_gtk/logic/engraving.py   # Verovio: MusicXML → SVG pages at a width and zoom;
                                      # the measure of each written bar; its rectangle from
                                      # the staff lines
src/stickler_gtk/logic/marker.py      # song time → song bar → written bar → measure
src/stickler_gtk/ui/sheet.py          # the pages (librsvg) and the marker (cairo)
src/stickler_gtk/ui/pdf.py            # Verovio's A4 pages → PDF with librsvg and cairo
packaging/fonts/Leipzig.ttf, packaging/fonts/OFL.txt
tests/gtk/test_engraving.py, test_marker.py
```

#### Testing strategy

- Logic first, with Verovio and without GTK, on MusicXML that `notation.engrave` writes for
  the notation tests' songs (with repeats, a pickup, a multi-measure rest): every written bar has
  one rectangle inside its page; the rectangles of a system follow left to right; every song
  time inside the song maps to a bar, and the marked measure is the bar map's written bar.
- Eye of the Tiger once by hand and in a slow test: 43 measures, each with a rectangle; the 8
  bars with dotted notes get rectangles as tall as their staff (where librsvg failed).
- Widgets: the page appears after a fake analysis; zoom changes the layout; a click marks a bar.
- PDF: a test renders a short song to PDF and finds one PDF page per Verovio page; by hand the
  tempo mark shows as "♩ = 109", not a box.

#### Boundaries

- **Always:** Verovio only in `stickler_gtk`; layout and bar rectangles in `logic/`; the font
  only through fontconfig.
- **Ask first:** another Verovio version or another music font; changing Verovio's engraving
  options beyond page size, scale and breaks.
- **Never:** Verovio in `src/stickler`; MuseScore for the app's PDF; a sideways scroll bar.

#### Success criteria

1. Eye of the Tiger appears on the result page within 1 s of the result (Verovio and librsvg
   together), as wide as the window, at 360 px and at 1000 px.
2. Zoom works with the keyboard and Ctrl+scroll; Ctrl+0 returns to the window's width.
3. Every one of the 43 written bars of Eye of the Tiger can be marked by a click; marking song
   bar 3 (inside the first multi-measure rest) marks written bar 1.
4. The position call marks the right bar for every song bar of Eye of the Tiger (110, checked
   against the bar map) and scrolls it into view.
5. In dark style the page is inverted and the marker blue.
6. The PDF export writes A4 pages with the tempo mark drawn correctly; "Open With…" opens the
   system's app chooser for the MusicXML.
7. `scripts/check.sh task` is green, `stickler_gtk/logic` stays at ≥ 95% coverage, and no
   Verovio import exists in `src/stickler`.

#### Open questions

- Whether Verovio's default engraving options read well for drums at small widths (system
  breaks, spacing) is only seen on screen; the owner looks at it in this module's checkpoint.

### Module `playback`

> Status: **approved** by the owner on 2026-11-15. Plan: `tasks/plan.md` ("GTK application:
> `playback`"), tasks 55–59 in `tasks/todo.md`.

#### Assumptions

1. **GStreamer through PyGObject** (1.28 on the development machine and in the GNOME runtime 51;
   every element and decoder needed checked 2026-11-15: `uridecodebin`, `audioconvert`,
   `audioresample`, `volume`, `audiomixer`, `autoaudiosink`, decoders for FLAC, MP3, Ogg Vorbis,
   Opus, WAV and AAC). One pipeline mixes two sources: the song and the detected hits as clicks.
   Because it is one pipeline, play, pause and seek always move both together.
2. **The clicks** are `api.render_hits` (engine-api): a mono WAV as long as the song, written
   into the app's cache when a result appears (0.18 s for Eye of the Tiger). Drum samples instead
   of clicks stay a later decision.
3. **Song / Hits / Both** mute one source or none; the volume button holds one slider per source
   (design screen 6). The two volumes are remembered for every song (owner, 2026-11-15), like
   the note size; what to hear starts at "Both".
4. **The position drives the marker:** while playing, the window asks the pipeline for its
   position about 20 times a second and calls `show_position` (sheet-view), which marks the
   bar and scrolls it into view.
5. **A click on a bar jumps there** (owner, 2026-11-15): to the start of that written bar's next
   occurrence after the current position; after its last occurrence, back to its first. When
   stopped, the click jumps the same way and does not start playing.
6. **The logic is apart from GStreamer:** `logic/playback.py` holds what to hear and how loud,
   which song bar a jump goes to, and the texts of the bar ("0:06", "Bar 2 of 110"); the
   GStreamer pipeline is a thin wrapper in `ui/player.py`.
7. **Sound in the Flatpak** needs `--socket=pulseaudio` (PipeWire through its PulseAudio
   interface), already listed in `app-shell`'s permission table for this module.

#### Objective

Hear whether the notes are right (design screen 6, narrow screen 10): the song, the detected
hits as clicks, or both, while the marker follows bar by bar.

1. The playback bar under the sheet: play/pause, the time, a position slider to seek, the
   song's length, "Bar n of N", the volume button, and Song / Hits / Both. In a narrow window it
   takes two rows.
2. Song / Hits / Both and the volumes change what is heard at once, without restarting.
3. The marker follows the bar that sounds; a click on a bar jumps there (assumption 5).
4. Keyboard: Space plays and pauses, Left and Right go one bar back or on, Home goes to the start.
5. At the end of the song playback stops; Space plays it from the start again. Opening another
   song, closing the window or quitting stops the pipeline.

Not part of this module: loops, slower playback, muting single drums (practice tools, "Not
Doing"), drum samples.

#### Commands

```bash
scripts/gtk.sh                          # the app with playback
uv run pytest -q tests/gtk              # logic tests, no GStreamer needed
scripts/gtk.sh test                     # widget tests and one real pipeline (fake sink)
scripts/check.sh task                   # before every commit
```

#### Project structure (additions)

```
src/stickler_gtk/logic/playback.py    # hear mode and volumes, bar jumps, bar and time texts
src/stickler_gtk/logic/paths.py       # + where the clicks WAV of a song goes
src/stickler_gtk/logic/settings.py    # + the two volumes
src/stickler_gtk/ui/player.py         # the GStreamer pipeline: two sources, a mixer, a sink
src/stickler_gtk/ui/playbar.py        # the playback bar and the volume popover
tests/gtk/test_playback.py
```

#### Testing strategy

- Logic without GStreamer: the volumes of each source for Song / Hits / Both; the jump target
  for a written bar from any position, across repeats and after the last occurrence; the bar
  and time texts; remembered volumes (missing or bad values fall back).
- A real pipeline in a widget test, with a fake audio sink and a generated song: it plays, its
  position advances, a seek lands within 50 ms, and setting it to NULL leaves nothing running.
- Widgets: the bar's controls drive a fake player; a click on a bar seeks to the expected time.
- By hand: Eye of the Tiger with clicks, by ear; Space, arrows, Home; the narrow window.

#### Boundaries

- **Always:** one pipeline for both sources; GStreamer only in `ui/player.py`; the pipeline set to
  NULL on stop, close and quit.
- **Ask first:** drum samples instead of clicks; any practice feature (loop, speed); another
  audio library.
- **Never:** decode or mix audio in the main loop by hand; leave a pipeline playing after the
  window closed.

#### Success criteria

1. Eye of the Tiger plays with its clicks in time with the drums (owner, by ear); pause, resume
   and seeking with the slider work.
2. Song / Hits / Both and both volume sliders change what is heard without a gap or restart.
3. The marker follows the sounding bar within 0.1 s and keeps it in view.
4. A click on a bar inside repeat signs jumps to its next pass; after the last pass to the first.
5. The volumes are the same after a restart.
6. Space, Left, Right and Home work; the narrow window shows the bar in two rows.
7. Closing the window or quitting during playback stops the sound at once; nothing keeps running.
8. `scripts/check.sh task` is green, `stickler_gtk/logic` at ≥ 95% coverage.

#### Open questions

- None.

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
