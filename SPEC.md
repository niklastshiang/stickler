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
| Transcription | `drumsep_onset` | DrumSep MDX23C 6-stem (via python-audio-separator 0.48.0) + onsets per stem (release 7) | Code MIT, weights without a formal licence (community model) |
| Transcription | `muscriptor_l` | muscriptor/muscriptor large (release 7) | MIT / weights CC BY-NC |
| Transcription | `sad` | Separate-and-Detect (ddman1101, 2026), 5 drum stems by latent diffusion + onsets per stem (release 7; owner's exception: research code) | MIT |
| Beats | `beat_this` | CPJKU/beat_this | MIT |

## Tech Stack
- Python **3.12** and `uv` ≥ 0.13 (Homebrew). Every environment is managed with `uv`. The harness also runs on 3.13 and 3.14 (since 2026-11-14, for the GTK app, whose bindings use the system's or the GNOME runtime's Python); `.python-version` keeps 3.12 the default for development. The app's models (ADTOF, Beat This!, Demucs) run on 3.14 since 2026-11-15 (`packaging`); the benchmark-only models stay on 3.12.
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
- **Device-independent cache:** results computed on a GPU count as cache hits on the laptop. Since 2026-11-16 (owner, Task 87) the code digest covers `run.py`, `setup.py`, the adapter's modules they import, `pyproject.toml`, `uv.lock`, `.python-version` and `adapters/_common`; pairs of equivalent digests in `src/stickler/digests.yaml` let an entry under an earlier digest be renamed on first use, but only along a chain that ends at the current digest, so edits that do not change behaviour never cost a recomputation and a real change never inherits old results. The device is recorded in `meta.json` instead of the cache key. Together with comment-insensitive adapter digests this is one cache migration after the running MDB benchmark has finished; existing entries are moved to their new keys, nothing is recomputed.
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
src/stickler/classes.yaml      # mapping table (in the package, so the installed app has it)
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
| `playback` | Play the song: original / detected / both; the position drives the marker | `sheet-view`, `engine-api` | done, below |
| `corrections` | Side panel with the light corrections; re-engraves | `sheet-view`, `engine-api` | done, below |
| `setup-assistant` | Consent, download of the Fast models with progress, resumable | `app-shell`, `engine-api` | done, below |
| `packaging` | Flatpak and AppImage with every release | all | done, below |

Build order: `engine-api`, `design` (in parallel) → `app-shell` → `sheet-view` → `playback`,
`corrections` → `setup-assistant` → `packaging`.

Out of order on purpose: the Flatpak sandbox trial (can `uv` build a model environment inside
the sandbox?) belongs to `packaging` but runs early, because a failure changes `setup-assistant`.
**Done 2026-11-15, passed** (details in `setup-assistant`, assumption 1): in `org.gnome.Platform//51`
with only the network and one folder, a static `uv` 0.13.8 fetched Python 3.12 itself and built
ADTOF's and Beat This!'s environments; both ran on a clip. ADTOF needs its git dependency as a
GitHub archive, because the runtime has no git.

### Decisions for all modules (owner, 2026-11-14)

- **No GTK code before `design` is approved.** `engine-api` is library work and may run in
  parallel.
- **Languages:** English and German in the first version; strings are translatable from the
  start. How translations are contributed and kept up to date later needs its own answer (no
  outside pull requests today); it is specified in `app-shell`.
  **Spanish is the third language** (owner, 2026-11-15, for the owner's drum teacher from Peru):
  neutral Latin American Spanish, informal "tú" as German "du", drum words as used there
  (bombo, redoblante, platillos). `po/LINGUAS` lists the languages; the tests check every one
  for completeness, kept placeholders and the 360 px width.
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
   trial not installing the package). The adapters run in their own environments as
   subprocesses, so the app's Python does not matter to them. (Update 2026-11-15, `packaging`:
   the app's three models moved to 3.14 with identical results, their cache rekeyed.)
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
     depends on its licence (not checked). (Update 2026-11-15: MIT; the mirror release
     `beat-this-final0` exists, see `setup-assistant`.)
3. **Python:** the harness is widened to 3.12–3.14 now. Raising the adapters is planned for the
   future (`tasks/todo.md`, "Later"), together with a benchmark rerun, because it changes every
   cache key. (Update 2026-11-15: the app's three models moved to 3.14 in `packaging` without a
   rerun, their results identical and the cache rekeyed; the other four stay on 3.12.)

#### Open questions

- Which Python the GNOME runtime ships at the time of `packaging` is not checked yet; the
  3.12–3.14 range covers the development machine and is widened again if needed. (Answered
  2026-11-15: GNOME 51 ships Python 3.14.)

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

> Status: **done** (Checkpoint I). Approved by the owner on 2026-11-14. Plan: `tasks/plan.md`
> ("GTK application: `app-shell`"), tasks 41–48 in `tasks/todo.md`.

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
   GNOME HIG standard shortcuts (checked 2026-11-14): Ctrl+O open, Ctrl+W close the window
   (since 2026-11-18, owner: first the song, back to the empty window, as "Close Song" in the
   main menu; then the window),
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

> Status: **done** (Checkpoint J). Approved by the owner on 2026-11-15 (Verovio as a new
> dependency of the app included). Plan: `tasks/plan.md` ("GTK application: `sheet-view`"), tasks 49–54 in
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

> Status: **done** (Checkpoint K, 2026-11-15). Approved by the owner on 2026-11-15. Plan:
> `tasks/plan.md` ("GTK application: `playback`"), tasks 55–59 in `tasks/todo.md`.

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
   (design screen 6). The song starts at 70 %, the clicks at 100 %, and the clicks are fuller
   than the CLI's listening clicks: the first ones sat about 3 dB under the song and were too
   quiet (owner, 2026-11-15). The two volumes are remembered for every song (owner, 2026-11-15), like
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

### Module `corrections`

> Status: **done** (Checkpoint L, 2026-11-15). Approved by the owner on 2026-11-15. Plan:
> `tasks/plan.md` ("GTK application: `corrections`"), tasks 60–64 in `tasks/todo.md`.

#### Assumptions

1. **Corrections are parameters of `notate`** (`api.Corrections`, engine-api): tempo half / as
   detected / double, beats per bar, the first "one", simplify, repeat signs. The transcription
   is cached, so no model runs: measured on Eye of the Tiger 2026-11-15, `notate` takes
   0.17–0.2 s with any correction; Verovio's engraving follows.
2. **Every change applies at once**, without an "Apply" button: the window notates anew in the
   worker thread after a short pause (250 ms, so a few quick clicks on a stepper make one run),
   then engraves. The sheet stays shown meanwhile; a newer change makes an older run's result
   stale (job numbers, as in `app-shell`). A failed run keeps the last sheet and shows a toast.
3. **What follows a correction:** the window title (tempo and meter), the bar map, so the marker
   and the bar clicks of `playback` fit the new bars, and every export (they use the current
   notation). Playback keeps running at the same time; the clicks do not change, because the
   hits do not.
4. **Remembered per song** (owner, 2026-11-15): `$XDG_DATA_HOME/stickler/corrections.json`, next
   to the recent songs, keyed by the song's path. Opening a song notates it with its stored
   corrections; "Back to Detected" removes them. Values that are no longer valid are dropped
   one by one, as in the settings.
5. **The controls** (design screens 7 and 11):
   - Tempo: Half / As Detected / Double (`Adw.ToggleGroup`).
   - Beats per bar: a stepper from 1 to 12, showing the detected number until it is changed.
   - The first "one": a stepper over the beats of the first bar ("Beat 1" … "Beat n", n the
     beats per bar), with the line "Beats before it are a pickup".
   - Simplify ("Nearly equal bars get one pattern") and Repeat signs ("Equal bars are written
     once") as switches.
   - "Back to Detected", insensitive while nothing is corrected.
6. **Where it sits:** a sidebar at the end of the window (`Adw.OverlaySplitView`), opened and
   closed with a header button and F9 (HIG "side pane"), closed at first; below the narrow
   breakpoint a bottom sheet (`Adw.BottomSheet`) instead (design screen 11).
7. **The logic is apart from GTK:** `logic/corrections.py` holds the corrections of a song, the
   changes the controls make (ranges, the first "one" kept within the bar), whether anything is
   corrected, and the store.

#### Objective

Fix what the analysis got wrong about the beat, and make the sheet easier to read, in a second,
without running anything again (design screens 7 and 11).

1. The sidebar (or bottom sheet) shows the controls of assumption 5 with the current values.
2. A change shows the corrected sheet within about a second; title, marker, bar clicks and the
   exports follow it.
3. A song opened again shows its corrections; "Back to Detected" restores the detected sheet.

Not part of this module: a tempo other than half or double, undo beyond "Back to Detected",
changes to the models. Correcting single notes or hits is not part of the app at all (owner,
2026-11-15).

#### Commands

```bash
scripts/gtk.sh                          # the app with the corrections
uv run pytest -q tests/gtk              # logic tests
scripts/gtk.sh test                     # widget tests
scripts/check.sh task                   # before every commit
```

#### Project structure (additions)

```
src/stickler_gtk/logic/corrections.py   # a song's corrections, the controls' changes, the store
src/stickler_gtk/logic/analysis.py      # + notate with corrections; a re-notate job
src/stickler_gtk/logic/session.py       # + a correction in flight on a Result
src/stickler_gtk/ui/corrections.py      # the sidebar's controls
src/stickler_gtk/ui/window.py           # split view, bottom sheet, F9, applying a change
tests/gtk/test_corrections.py
```

#### Testing strategy

- Logic: each control's change and its range; the first "one" kept within the bar when the
  beats per bar shrink; "corrected or not"; the store (round trip, per song, bad values dropped,
  a missing file).
- The job: `analyse` passes the stored corrections to `notate`; a re-notate passes the new ones.
- Session: a change's result is shown; an older change finishing late is ignored.
- Widgets with the fake analysis: a change re-engraves and updates the title; "Back to Detected"
  is insensitive until something changes; F9 opens the sidebar; a narrow window shows the
  bottom sheet; the corrections are back after reopening the song.
- By hand: Eye of the Tiger at half tempo and with the first "one" moved, by eye and by ear.

#### Boundaries

- **Always:** corrections only through `api.Corrections`; the transcription never rerun; the
  notation in the worker thread.
- **Ask first:** more correction kinds (single notes, other tempo factors); storing corrections
  next to the song file instead of in the app's data.
- **Never:** block the main loop on `notate` or Verovio longer than one engraving; lose a
  stored correction because another song's entry is broken.

#### Success criteria

1. Each control changes the sheet within about a second on Eye of the Tiger (owner).
2. Half and Double change tempo and bars as expected; the title shows the new tempo and meter.
3. Beats per bar and the first "one" give the expected meter and pickup.
4. Simplify and Repeat signs switch on and off as on the CLI (`stickler notate`).
5. The marker, bar clicks and exports use the corrected bars.
6. Corrections come back after closing and reopening the song; "Back to Detected" clears them.
7. F9 and the header button open and close the sidebar; the narrow window shows a bottom sheet.
8. German complete; `scripts/check.sh task` green, `stickler_gtk/logic` at ≥ 95% coverage.

#### Open questions

- None.

### Module `setup-assistant`

> Status: **done** (Checkpoint M, 2026-11-15). Approved by the owner on 2026-11-15. Plan:
> `tasks/plan.md` ("GTK application: `setup-assistant`"), tasks 65–69 in `tasks/todo.md`.

#### Assumptions

1. **The sandbox trial passed** (2026-11-15, `org.gnome.Platform//51`, only `--share=network`
   and the trial folder, the static `uv` 0.13.8 from the uv release, checksum checked):
   - `uv` downloads Python 3.12 itself (113 MB); neither the runtime's Python 3.14 nor a
     compiler is needed (the runtime has neither git nor gcc).
   - ADTOF fetches `adtof-pytorch` with git, which the runtime lacks. The same commit as a
     GitHub archive (`.../archive/<commit>.tar.gz`) installs without git or a compiler, with the
     same 42 package versions as today's lock; `uv sync` 18 s, 30 s of music in 3 s.
   - Beat This! runs (4 s on the clip). Its checkpoint server answered HTTP 500 from the
     sandbox and from the host alike: down again, not the sandbox.
2. **ADTOF's git source becomes the archive URL** of the same commit. Results cannot change, so
   its cached results are rekeyed (`stickler cache-digests` before, `cache-migrate
   --rekey-from` after, CLAUDE.md).
3. **A mirror for Beat This!'s checkpoint** (owner, 2026-11-15): its code and weights are MIT
   ([CPJKU/beat_this](https://github.com/CPJKU/beat_this) README, checked 2026-11-15), and its
   only host, `cloud.cp.jku.at`, was down on 2026-11-14 and 2026-11-15. A copy of `final0.ckpt`
   with the MIT licence goes into a GitHub release of Stickler; Beat This!'s `setup.py` tries
   JKU first and the copy only when JKU fails, and checks the file's SHA-256 either way. Its
   cached results are rekeyed as in assumption 2. Publishing the release is the owner's step
   (or mine with the owner's go at that moment).
4. **When the assistant shows** (owner, 2026-11-15): at start, if Fast is not set up
   (`api.mode_ready`, checked in the worker), the window opens on the consent page (design
   screen 1). "Not Now" shows the empty window; opening a song then asks again instead of
   analysing. Once agreed, the consent is remembered (settings), so an interrupted download goes
   on by itself at the next start, as screen 2 promises.
5. **The download** (design screen 2) runs `api.setup_adapters` for each missing Fast adapter
   in the worker, with the step list of `app-shell` (programs and model per adapter: done,
   running, waiting). A running step also shows its bytes: what has grown on disk (the adapter's
   folder and uv's cache) against the sizes in `docs/requirements.md`, never past 99 % before
   the step ends. Cancel stops it at once (`CancelToken`); what is done stays.
6. **A failed step** (design screen 3) names its server: the Python package servers (pypi.org,
   download.pytorch.org, github.com) for the programs, JKU Linz and Stickler's copy for Beat
   This!'s model; it keeps what is done, shows the technical details (the error's last lines),
   and offers "Try Again" and "Later" (the empty window).
7. **Where the models live** does not change here: the app uses `api.ADAPTERS_ROOT` as today.
   `packaging` moves it into the app's data folder and ships `uv`; the trial shows both work.
8. **The page for missing models** of `app-shell` (the `stickler setup` commands) goes: a
   missing model now leads to the consent page.
9. **The drum track's Demucs** stays with the export (its cost dialog and steps, `app-shell`).

#### Objective

A drummer who never used a terminal starts Stickler, agrees once, waits a few minutes, and can
analyse songs (design screens 1–3).

1. First start: the consent page names both models, what each does, its size and licence
   (ADTOF's model non-commercial only), the total on disk, and "Not Now" / "Download 2.2 GB".
2. The download shows each step and its progress; it can be cancelled and resumes later.
3. A server that does not answer is named; "Try Again" goes on from where it failed.
4. Afterwards the empty window appears and a song can be opened.

Not part of this module: Quality mode's models (the app runs Fast), GPU environments,
moving the models' folder and shipping `uv` (`packaging`).

#### Commands

```bash
scripts/gtk.sh                          # the app; STICKLER_ADAPTERS=<copy> for a fresh setup
uv run pytest -q tests/gtk              # logic tests
scripts/gtk.sh test                     # widget tests (headless)
scripts/check.sh task                   # before every commit
```

#### Project structure (additions)

```
src/stickler_gtk/logic/setup.py         # when to ask, the steps, bytes against sizes, servers
src/stickler_gtk/logic/settings.py      # + the consent
src/stickler_gtk/ui/setup.py            # consent, download and error pages
adapters/transcribers/adtof/            # git source → archive URL (same commit), lock
adapters/beats/beat_this/setup.py       # JKU first, then Stickler's copy, SHA-256 checked
tests/gtk/test_setup.py
```

#### Testing strategy

- Logic: when to show consent, download or the empty window (ready, not agreed, agreed but
  unfinished); the steps for what is missing; bytes against sizes (capped); which server a
  failed step names.
- Beat This!'s download: JKU answering, JKU failing with the copy answering, a wrong checksum
  (rejected), both failing (the error names both).
- Widgets with a fake `setup_adapters`: consent → download → empty window; "Not Now" and the
  question coming back with a song; cancel; a failure, then "Try Again".
- By hand: a fresh setup into a copy of the adapters on the development machine, timed, and
  interrupted once.

#### Boundaries

- **Always:** the consent before any download; ADTOF's licence named before agreeing; the
  checksum of the mirrored checkpoint checked; what is done kept on failure or cancel.
- **Ask first:** publishing the mirror release; any other mirrored file; changing a model or its
  version.
- **Never:** download anything before consent; ship ADTOF's weights; hide which server failed.

#### Success criteria

1. A fresh setup of Fast from the app works on the development machine (owner) and takes a
   few minutes on a home connection.
2. Interrupted (cancel, or the app killed), the next start goes on and finishes.
3. With JKU down, Beat This!'s model comes from the copy; with both down, screen 3 names them.
4. "Not Now" opens the empty window; opening a song asks again.
5. ADTOF from the archive gives the same results as before (cached results rekeyed, the
   benchmark's own songs unchanged).
6. German complete; every page fits 360 px; `scripts/check.sh task` green, `stickler_gtk/logic`
   at ≥ 95% coverage.

#### Open questions

- None.

### Module `packaging`

> Status: **done** (Checkpoint N, release 5, 2026-11-15). Approved by the owner on 2026-11-15. Plan: `tasks/plan.md` ("GTK application:
> `packaging`"), tasks 71–77 in `tasks/todo.md`.

#### Assumptions

1. **Where it goes** (owner, 2026-11-15): every release gets a `.flatpak` file and an AppImage
   attached, both built by GitHub Actions. No store, after a search on 2026-11-15:
   - Flathub's "Generative AI policy" requires the manifest to be free of AI-generated or
     AI-assisted content and forbids AI tools from opening or writing the submission PR; other
     AI-generated code must be disclosed and may be rejected; machine-generated translations
     are not allowed ([requirements](https://docs.flathub.org/docs/for-app-authors/requirements)).
     Flathub stays a later idea that needs the owner's hand-written manifest and submission.
     German is checked by the owner (a native speaker); Spanish is not checked yet.
   - elementary AppCenter allows no AI-generated content at all; Fedora Flatpaks carry
     Fedora-built packages only. A signed repository of our own on GitHub Pages stays possible
     later (a GPG key in GitHub's secrets).
2. **The Flatpak** (`packaging/flatpak/ng.tshia.Stickler.yml`):
   - Runtime `org.gnome.Platform//51` (current, released 2026-09-16; 49–51 not end of life).
     It brings Python 3.14, PyGObject, GTK, libadwaita, GStreamer with its decoders, and
     `ffmpeg`/`ffprobe` 8.1 with MP3, AAC, FLAC, Opus and Vorbis (checked 2026-11-15): no
     ffmpeg module is needed.
   - The app's Python packages (numpy, pyyaml, mido, typer, verovio) are vendored with
     `flatpak-pip-generator` (flatpak-builder-tools, maintained) as wheels; the build has no
     network.
   - `uv` is the static release binary (version and SHA-256 pinned), as the sandbox trial used.
   - The Leipzig font, icons, desktop file, MetaInfo and the `.mo` files go into `/app`.
   - Permissions exactly as the table in `app-shell` (network, PulseAudio, Wayland/X11, IPC,
     DRI); no file system access.
3. **The AppImage** is built with `quick-sharun` (pkgforge-dev Anylinux-AppImages, MIT, active:
   last commit 2026-11-15), pinned to a commit, inside an Arch Linux container: it bundles
   Python, GTK 4, libadwaita, GStreamer, `ffmpeg`/`ffprobe`, `uv` and glibc, so it runs on any
   x86_64 distribution and needs no FUSE. Gradia (Python, GTK 4, libadwaita) is built this way.
   Estimated 70–90 MB. It carries update information (zsync) for AppImage update tools.
4. **Where the models live** in a packaged app: `$XDG_DATA_HOME/stickler/adapters` (in the
   Flatpak `~/.var/app/ng.tshia.Stickler/data/...`). The adapters' sources ship read-only with
   the app and are copied there; a new app version refreshes the copy, keeping environments and
   weights, and `uv sync` updates what changed. The result cache goes to
   `$XDG_CACHE_HOME/stickler`. Running from the checkout (`scripts/gtk.sh`) keeps today's folders;
   `STICKLER_ADAPTERS` still overrides.
5. **Python 3.14 for the models the app uses** (owner, 2026-11-15: ADTOF, Beat This!, Demucs;
   the four benchmark-only models stay on 3.12, the benchmark was run already). ADTOF and Beat This! were checked:
   every package has a 3.14 wheel, no version changes, and Eye of the Tiger gives identical
   results (1375 hits, byte-identical MIDI; 441 beats). Demucs is checked the same way (it needs
   numpy 2, which has 3.14 wheels; the old lock had kept numpy 1.26 without one);
   identical results are rekeyed (CLAUDE.md), different ones recomputed when next needed (they
   matter only to the benchmark, owner). In the Flatpak, `uv` uses the runtime's Python 3.14 (no
   download). A runtime with another Python would leave `uv` without a matching interpreter, so
   the release workflow checks that the runtime's Python equals the models' `.python-version`;
   moving to such a runtime means moving the models to its Python first (code review, 2026-11-15).
   In the AppImage, `uv` downloads its own Python 3.14
   (its bundled Python moves with every mount); its downloads and that Python stay in Stickler's
   folders (`~/.cache/stickler/uv`, `~/.local/share/stickler/python`), so deleting Stickler's
   three folders removes everything (owner, 2026-11-15; README `> INSTALL THE APP`).
6. **The app stops importing the benchmark's code** (`mir_eval`, and with it scipy), so neither
   package has to ship.
7. **AppStream MetaInfo** (`packaging/ng.tshia.Stickler.metainfo.xml`): name, summary,
   description, screenshots, releases, OARS, licence (GPL-3.0-or-later; the metadata CC0-1.0), developer
   `ng.tshia`; validated with `appstreamcli` in CI, so GNOME Software shows the bundle properly.
8. **Releases:** pushing a release tag builds both files and attaches them; a manual run builds
   them without a release, for testing. Release notes say how to install each.
9. **x86_64 only.** M4A/AAC songs are not promised: Beat This! reads audio with soundfile (MP3,
   FLAC, WAV, OGG), as the empty window already says.

#### Objective

A drummer downloads one file from a release, opens it, and Stickler runs: the Flatpak through
GNOME Software (or `flatpak install`), the AppImage by making it executable and starting it.

#### Commands

```bash
flatpak-builder --user --install --force-clean build packaging/flatpak/ng.tshia.Stickler.yml
flatpak build-bundle ~/.local/share/flatpak/repo Stickler.flatpak ng.tshia.Stickler
scripts/appimage.sh                     # in the Arch container, as CI runs it
appstreamcli validate packaging/ng.tshia.Stickler.metainfo.xml
scripts/check.sh task
```

#### Project structure (additions)

```
packaging/flatpak/ng.tshia.Stickler.yml    # the manifest
packaging/flatpak/python-deps.json         # generated by flatpak-pip-generator
packaging/ng.tshia.Stickler.metainfo.xml
scripts/appimage.sh                        # quick-sharun build
.github/workflows/release.yml              # both files for a release tag or by hand
src/stickler_gtk/logic/paths.py            # + packaged: models and cache in XDG folders
adapters/{transcribers/adtof,beats/beat_this,separators/demucs}/  # Python 3.14
```

#### Testing strategy

- Logic: where models and cache go (checkout, Flatpak, AppImage, `STICKLER_ADAPTERS`); the
  refreshed copy keeps environments and weights; the app imports no benchmark module.
- Each model on 3.14: lock, wheels, one song compared with 3.12.
- CI: `appstreamcli validate`, the manifest builds, the AppImage builds and starts
  (`quick-sharun --test`).
- By hand (owner): install the `.flatpak`, set up the models, analyse, play and export a song;
  start the AppImage on the same machine.

#### Boundaries

- **Always:** pinned versions and checksums for everything downloaded at build time; the
  `app-shell` permissions and no more; both files from CI, not from a developer's machine.
- **Ask first:** a store or an own repository; more permissions; another architecture;
  dropping a model.
- **Never:** ship ADTOF's weights; add file system permissions; let an AI tool submit to Flathub.

#### Success criteria

1. A manual CI run produces `Stickler-<version>.flatpak` and `Stickler-<version>-x86_64.AppImage`; a release tag
   attaches both to its release.
2. The Flatpak installs on the owner's machine, the setup assistant sets up the models inside
   the sandbox, and a song can be opened, analysed, played and exported (owner).
3. The AppImage does the same on the owner's machine (owner).
4. ADTOF, Beat This! and Demucs run on Python 3.14; each was compared with its 3.12 result.
5. The app no longer imports scipy or mir_eval.
6. The MetaInfo validates; `scripts/check.sh task` is green.

#### Open questions

- None.

### Module `polish`

> Status: **done** (Checkpoint O, 2026-11-15). Approved by the owner on 2026-11-15. Three wishes of the owner after release 5.
> Plan: `tasks/plan.md` ("`polish`"), tasks 78–81 in `tasks/todo.md`.

#### Assumptions

1. **Click volume follows the song, one level per song** (owner, 2026-11-15). The clicks suit
   Eye of the Tiger but are too loud on Amaranthe's "Fearless". `render_hits` measures the song
   where its hits are (the loudness of 50 ms windows at the hits, the measure used on
   2026-11-15) and scales the clicks so that they stand out by as much as they do on Eye of the
   Tiger today (about 4 dB over the song). One gain for the whole song: steady, no pumping. The
   soft limit stays, so the clicks never clip; a silent song or one without hits keeps today's
   level. Reading the song takes about a second in the worker that writes the clicks; the
   volume sliders stay on top of it.
2. **The artist in the PDF** (owner, 2026-11-15). Stickler's MusicXML names the artist as the
   composer, which Verovio keeps in its metadata but does not engrave (checked 2026-11-15). The
   MusicXML gets `<credit>` elements for the title (centred) and the artist (right), as
   notation programs write them: the PDF's first page shows both (checked with Verovio), and
   MuseScore shows them too. The app's sheet keeps no header (the window title shows both).
3. **"Remove Downloaded Models…" in the main menu, only in the installed app** (owner,
   2026-11-15): in the Flatpak and the AppImage the models lie in Stickler's own folders; from
   the checkout the entry would delete the benchmark's models, so it is not shown there.
   - It asks first (an alert) and says how much it frees.
   - By default it removes the models with their programs and downloads (uv's cache and, in
     the AppImage, its Python) and the saved analyses; settings, recent songs and corrections
     stay. A check box "Also remove settings, recent songs and corrections" removes everything,
     as a new install would have it (owner, 2026-11-15).
   - It is not offered while an analysis, an export or a download runs. Afterwards the window
     is empty, and the setup assistant asks again before the next analysis.
4. **The logic is apart from GTK:** which folders a removal touches (never anything outside the
   app's own folders, nothing in the checkout), and the click gain.

#### Objective

The clicks are as easy to hear on a loud song as on a quiet one; the printed sheet names the
band; an AppImage user can free the space the models take without knowing where they lie.

#### Commands

```bash
uv run pytest -q                       # library and logic tests
scripts/gtk.sh test                    # widget tests (headless)
scripts/check.sh task                  # before every commit
```

#### Project structure (additions)

```
src/stickler/audio.py, api.py          # the click gain from the song's loudness
src/stickler/notation.py               # credits for title and artist
src/stickler_gtk/logic/removal.py      # what a removal deletes, in the app's folders only
src/stickler_gtk/ui/menu.py, window.py # the menu entry and its alert
```

#### Testing strategy

- Clicks: a quiet and a loud version of the same song get clicks at the same level relative to
  the song; a silent song keeps today's level; the clicks never clip.
- Artist: the MusicXML holds both credits; the first A4 page's SVG contains the artist; no
  artist, no credit.
- Removal: the folders for Flatpak, AppImage, with and without the check box; nothing outside
  the app's folders, nothing in the checkout; the size it frees. Widgets: the entry shows only
  when packaged, is disabled while a job runs, and leads to the consent page afterwards.

#### Boundaries

- **Always:** a removal asks first and touches only the app's own folders.
- **Ask first:** deleting anything the user did not choose; another click level.
- **Never:** remove models from the checkout's `adapters/`; let clicks clip.

#### Success criteria

1. On Fearless and Eye of the Tiger the clicks sound about equally prominent (owner, by ear).
2. The PDF's first page shows title and artist (owner).
3. In the Flatpak or AppImage, the menu entry frees the models' space after asking; with the
   check box nothing of Stickler is left; afterwards the assistant asks again (owner).
4. German and Spanish complete; `scripts/check.sh task` green.

#### Open questions

- None.

### Module `legend`

> Status: **deferred by the owner on 2026-11-17** ("maybe later, not needed now"): the code, names and tests stay, but the PDF export does not draw the legend (`ui/window.py`); switching it back on is one line. Task 91's owner check and Checkpoint Q wait with it.
> Before: **approved** by the owner on 2026-11-17, after a fresh-context review against the code
> (Verovio experiments on 2026-11-17; their findings are in the assumptions). The owner's wish
> after release 6: "a legend, so that untrained readers can check in the exported sheet what it
> means". Plan: `tasks/plan.md` ("`legend`"), tasks 88–91 in `tasks/todo.md`.

#### Assumptions

1. **Finer classes wait for a better model** (owner, 2026-11-15, after a measurement on the
   cached results). ADTOF, the app's model, writes every hi-hat as closed and every cymbal as
   crash (0 of 2172 open hi-hats and 0 of 845 ride hits in the own songs), and Quality takes
   hi-hat and cymbals from ADTOF too (`api.MODES`). MuScriptor M names them, but on the own
   songs only half of its open hi-hats are right and it finds 10 % of the rides; taking
   ADTOF's timing with MuScriptor's kind is no better there than always writing "closed" (82 %
   either way). The finer classes go with the item "new candidate models": in only when a model
   is measurably better on the own songs. This module adds no model.
2. **The legend is in the PDF the app exports, at the top of page 1,** under the title and the
   band: one short staff with one entry per position the sheet uses, its notehead in its place
   on the staff and its name below, sorted from top to bottom. An entry is a distinct `Staff`
   value of `notation.STAFF` (step, octave, notehead), so the legend can never disagree with
   the music; that includes side stick, the three tom heights and other percussion (`OTHER`),
   which Quality can write. Ties at one height (snare and side stick on C5) follow STAFF's
   order. No stems. The positions come from the engraved MusicXML's instruments (what remains
   after quantizing and simplifying), not from the raw hits.
3. **Names** (owner, 2026-11-17): the cymbal position (A5, where ADTOF writes every cymbal) is
   named "Cymbal" ("Becken"), not "Crash"; a ride (F5) is named "Ride"; the toms "High Tom",
   "Mid Tom", "Floor Tom"; side stick "Side Stick"; `OTHER` "Other Percussion". No line about
   what the model does not tell apart (owner, 2026-11-17: not needed).
4. **Room on page 1** (owner, 2026-11-17: bars may move): blank header lines after the band,
   right-aligned at the bottom of the header (Verovio stacks top-aligned lines between title
   and band), push page 1's music down by about 18 px each; page 1 then holds fewer systems, so
   bars move to later pages and the page count may grow by one. Pages 2 and later start at the
   same top margin. The lines are added in memory when the PDF's pages are engraved, never to
   the stored or exported MusicXML (module `polish`: plain title and artist credits). Where the
   legend goes is read from page 1's SVG (the first system's top), not assumed, with and
   without a band name; a sheet without any position gets no legend and no room.
5. **Where it is drawn:** the legend is a small score of its own, engraved by Verovio like the
   sheet (the same font and noteheads, names as lyrics, one stemless measure, hidden time
   signature), and nested into page 1's SVG in `logic/engraving.py`. `ui/pdf.py` stays as it
   is, so everything but the final PDF is tested without a display. It is engraved at its
   natural width; wider than the page (all 15 positions in German, more than about 12 entries)
   it is drawn smaller as a whole, since Verovio would otherwise squeeze the names into each
   other (2026-11-17).
6. **The names are in the app's language** (English, German, Spanish; the Spanish ones for the
   teacher's review with the rest). The strings are `N_()` constants in the GTK-free
   `stickler_gtk/logic/legend.py`, where `scripts/i18n.sh` finds them; `notation` takes the
   labels as a parameter and holds no strings.
7. **Not in this module:**
   - The MusicXML export: notation programs show their own drum key.
   - The command line's PDF: MuseScore engraves that one.
   - The app's sheet view: the window is for playing along. If the owner wants the legend there
     too, it is a small follow-up, since the legend's SVG already exists then.

#### Objective

Someone who has never read drum notation can open the exported PDF and see on the first page
which line and which notehead is which drum.

#### Commands

```bash
uv run pytest -q                       # library and logic tests
scripts/gtk.sh test                    # widget tests (headless)
scripts/check.sh task                  # before every commit
```

#### Project structure (additions)

```
src/stickler/notation.py               # the positions a sheet uses; the legend's MusicXML (labels given)
src/stickler_gtk/logic/legend.py       # the names (N_), the entries for a sheet in the app's language
src/stickler_gtk/logic/engraving.py    # room on page 1, the legend engraved and nested into page 1's SVG
po/*.po                                # the names
```

#### Testing strategy

- Positions: a sheet with kick, snare and hi-hat gives those three from top to bottom; side
  stick, three toms and `OTHER` each get an entry; ties follow STAFF; an empty sheet has none.
- The legend's MusicXML uses STAFF's step, octave and notehead for each entry, stemless, with
  the given labels as lyrics.
- Page 1 with the legend: the music starts lower, with and without a band; the legend sits
  under the band and above the first system without overlap; page 2 starts at the same top
  margin; the exported MusicXML has no blank credits.
- Width: every STAFF entry with the longest language's names stays one line.
- The written PDF has the legend on page 1 only (widget test, Poppler).

#### Boundaries

- **Always:** the legend follows `notation.STAFF`; it names only the positions the sheet uses.
- **Ask first:** a legend on every page; the legend in the app's sheet view.
- **Never:** change how the music itself is engraved; put the legend's room into the exported
  MusicXML.

#### Success criteria

1. The exported PDF of a song shows the legend on page 1, under title and band, with the right
   names for the sheet's positions (owner, with two songs, one in Fast and one in Quality).
2. Pages 2 and later start at the same top margin; bars may move to later pages, and the page
   count may grow by one (owner, 2026-11-17).
3. German and Spanish complete; `scripts/check.sh task` and the widget tests green.

#### Open questions

- None (the cymbal's name and the hint line were decided on 2026-11-17).

## Release 7: New candidates

> Status: **approved** by the owner on 2026-11-16. Candidates chosen by the owner on 2026-11-16
> after a web check of each (facts and sources below). Plan: `tasks/plan.md` ("Release 7"),
> tasks 12 and 82–86 in `tasks/todo.md`. **Result (2026-11-17):** measured on all three datasets;
> no candidate beats or comes within 0.01 of a mode on the own songs, so Fast and Quality stay
> unchanged (owner; ADR 0008, `docs/report.md` section 5.6).

### Objective
**Find out whether a newer model makes Fast or Quality better on the owner's music.** A
candidate replaces a pipeline in the app only if it beats it on the 25 own songs, corrected for
reference errors (owner, 2026-11-16); otherwise its results go into the report and the app stays
as it is.

User stories:
- As the owner, I want to know whether the models published since the benchmark beat Fast and
  Quality on my rock and metal songs.
- As the owner, I want the app to change only for a measured improvement, never for a promise.

Scope: three candidates, measured like every pipeline so far (25 own songs, MDB Drums, ENST
drummer 3; ±50 ms; 5 and 3 classes). Not in scope: fine-tuning (owner, 2026-11-13), new scoring,
finer classes in the sheet music (a later module; DrumSep's ride/crash split is only recorded).

### Candidates (owner, 2026-11-16; facts checked on the web 2026-11-16)
| ID | What | Source and licence | Notes |
|---|---|---|---|
| `drumsep_onset` (Task 12) | MDX23C DrumSep by aufr33/jarredou splits a drum stem into kick, snare, toms, hi-hat, ride, crash; librosa onset detection per stem → GM MIDI | In python-audio-separator 0.48.0 (`models.json`: `MDX23C-DrumSep-aufr33-jarredou.ckpt`), the version the `roformer` adapter pins; code MIT, weights without a formal licence (community model) | Needs a drum stem: runs as `demucs+drumsep_onset`. The original weight host is gone; the download is checked first. Ride and crash are merged into cymbals for scoring |
| `muscriptor_l` | MuScriptor large (~1.4 B parameters), like `muscriptor_s/_m` | HF `MuScriptor/muscriptor-large`, `model.safetensors` 5.47 GB, CC BY-NC 4.0, gated (accept the terms, `hf auth login`); muscriptor 0.4.0 (pinned) loads it | Download > 2 GB approved by the owner (2026-11-16). Measured on RunPod; a Quality candidate only (never Fast) |
| `sad` | Separate-and-Detect (Hsu et al., arXiv 2608.01093, Aug 2026): a latent-diffusion model generates five drum stems, a fixed onset detector turns them into hits | github.com/ddman1101/Separate-and-detect (MIT, last push 2026-08-13), weights HF `ddman1101/Separate-and-Detect` `msgld_obtb.ckpt` (MIT) | **Exception (owner, 2026-11-16):** tested although the project is research code without visible maintenance (CLAUDE.md asks for actively maintained projects): Python 3.9/3.10, conda, madmom, CUDA scripts. Trained on drum-only multitracks, so it runs on a Demucs stem; diffusion is slow, so measured on RunPod |

Looked at and left out (2026-11-16): Noise-to-Notes (Sony, 2025/26; no code or weights
published), LarsNet (5-stem U-Nets, 2023; the baseline Separate-and-Detect beats), MVSEP's
RoFormer DrumSep variants (no downloadable weights).

### Method
1. **Each candidate as an adapter**, like the others (own `pyproject.toml`, own environment,
   README with source, version/commit and licence). The harness is unchanged.
2. **Settings are chosen before the own songs are seen**: onset parameters (DrumSep) and any
   threshold on MDB and ENST, as in Phase 5c; the own songs are the final check only.
3. **Measured on all three datasets**; laptop runtimes (RTF, peak RAM) for every candidate that
   can run there, RunPod for the rest (the laptop stays the reference for the app's modes).
   **Exception for `sad`: tuned on MDB first, closed there** (owner, 2026-11-17; the rule of
   commit 9d5ff60, stricter than the stages written the same afternoon): if `sad` with tuned
   thresholds stays more than 0.03 macro-F1 behind tuned `drumsep_onset` and `muscriptor_l` on
   MDB's oracle stems, it is closed as tested and inferior and its ENST and own-song runs are
   skipped. **Result (2026-11-17): closed.** Tuned on MDB oracle (`stickler tune`, 23 tracks),
   mean F1 over 5 classes `sad` ≈ 0.60 (KD 0.937, SD 0.700, TT 0.318, HH 0.668, CY 0.361) against
   `drumsep_onset` ≈ 0.73 and `muscriptor_l` 0.81 (untuned); the report and ADR 0008 say so. Known
   risk, accepted: MDB choices transferred badly to the owner's rock/metal songs before.
4. **Measured first, listened to only where it can matter** (owner, 2026-11-16): all candidates
   are compared on measured scores. A candidate whose measured macro-F1 on the own songs (5-class
   scheme, as the modes were chosen and corrected; owner, 2026-11-17) comes within 0.01 of a
   mode's, or beats it, gets a listening round of about 40 new spots drawn from
   its own errors with release 3's procedure (blind, fixed seed, drawn once); its corrected score
   comes from those verdicts. The others go into the report with measured scores only.
5. **Time budget** (owner, 2026-11-16): Fast stays the fast mode that runs on any laptop
   (~15 s for a 4-minute song). A Quality candidate may take at most **20 minutes** (15 minutes
   plus a buffer) for a 4-minute song: on the laptop CPU, or, if it is too slow there, on a
   strong GPU (measured on RunPod's RTX 4090 as the reference). In the second case Quality
   requires a strong GPU (a strong integrated or dedicated card, or a rented one such as
   RunPod); how the app says so is decided with the mode (Task 86). Slower candidates are
   reported, never put into the app.
6. **Decision rule**: a candidate (alone or in a combination like today's Quality) replaces Fast
   or Quality only if its corrected macro-F1 on the own songs is higher and it stays within the
   mode's time budget. Per song better/worse counts and the 95 % interval are reported as for
   Quality vs Fast.

### Commands
```bash
uv run stickler setup --adapter drumsep_onset   # likewise muscriptor_l, sad
uv run stickler run --config config/benchmark.yaml
uv run stickler run --config config/own.yaml
uv run stickler remote …                        # RunPod for muscriptor_l and sad
uv run stickler eval --config config/own.yaml && uv run stickler report
```

### Project structure (additions)
```
adapters/transcribers/drumsep_onset/   # audio-separator DrumSep + librosa onsets
adapters/transcribers/muscriptor_l/    # copy of muscriptor_m with SIZE = "large"
adapters/transcribers/sad/             # Separate-and-Detect, pinned commit
config/benchmark.yaml, config/own.yaml # the new pipelines
docs/report.md, README.md              # results, candidates table
```

### Testing strategy
- Adapter smoke tests (`pytest -m adapters -k <id>`): 10 s of a real mix through the pipeline
  gives valid GM MIDI and `meta.json`; GM mapping of each candidate's classes as unit tests.
- DrumSep: the per-stem onset step is a pure function with unit tests on generated clicks.
- Results checked against the cache rules: existing entries untouched (new adapters, new keys).

### Boundaries
- **Always:** source, commit and licence in each adapter's README; weights downloaded by
  `setup`, never committed or shipped.
- **Ask first:** changing a mode of the app; adding a fourth candidate; a RunPod run longer than
  planned.
- **Never:** tune on the own songs; change the scoring to favour a candidate.

### Success criteria
1. Each of the three candidates produces MIDI or a logged error on all MDB, ENST and own songs
   (`sad` on MDB only: closed there by method 3's rule; owner, 2026-11-17).
2. `metrics.csv`, `report.html` and `docs/report.md` contain them next to Fast and Quality.
3. A decision per mode, recorded as an ADR: unchanged, or replaced (owner).
4. README candidates and results tables updated; `scripts/check.sh task` green.

### Resolved questions (owner, 2026-11-16)
1. Corrected scores need listening, because a new pipeline makes other errors than Fast and
   Quality: measured scores first, a listening round of about 40 spots only for a candidate
   that comes close (method, point 4).
2. Time budget for Quality: at most 20 minutes (15 plus a buffer; owner first said 30, then 20)
   for a 4-minute song, on the laptop or, if too slow there, on a strong GPU, which Quality then
   requires (method, point 5).

## Release 8: macOS app

> Status: **approved** by the owner on 2026-11-17 (capability map with `mac-design`, minimum
> scope, open questions 1 and 2 decided). Module specs are written and approved one at a time, in
> build order, as for the GTK application. Starts from the macOS research in `tasks/todo.md`
> (2026-11-16).

A native macOS app (SwiftUI) for the same drummers as the GTK app: open or drop a song, wait for
the analysis, read the sheet music, export it. Apple Silicon only. The Python core (models,
`stickler.api`, Verovio) is the same on both systems; each app is a thin interface over it.

### Objective
- **User:** a drummer with a Mac (Apple Silicon, macOS 26 or newer) who is not technical.
- **First version (minimum, owner 2026-11-17):** open or drop a song, set up the models with
  consent, analyse it with progress and cancel, read the sheet music, export MusicXML, PDF and the
  drum track, recent songs, English, German and Spanish. Fast mode only (owner, 2026-11-18):
  Quality needs MuScriptor, whose weights are gated on Hugging Face (an account, the licence
  accepted, a token), too much for a drummer who is not technical; the GTK app has no Quality
  either. Quality comes later for both apps, in a module of its own.
- **Later releases:** playback (`mac-playback`), corrections (`mac-corrections`), the GPU through
  Metal (`mac-gpu`, measured against the CPU first).
- **Success:** a drummer installs the `.dmg` from a GitHub release on a Mac they own and gets
  sheet music for a song without a terminal.

### Decisions for all modules (owner, 2026-11-17)
- **macOS only** in this release; Windows gets its own spec later.
- **Native interface (SwiftUI)**, not GTK: this replaces the decision of 2026-11-16 ("GTK on
  Windows and macOS to start with") for macOS. The GTK app stays the Linux app.
- **One shared core, two thin interfaces.** Everything that is not a widget lives in Python and is
  used by both apps: the app logic of `stickler_gtk/logic` moves to a neutral package
  `stickler_app` (GTK imports it in process; the Mac app reaches it through `stickler-bridge`).
  New features are built once, in Python, and tested once; Swift only draws and forwards.
- **One source for translations:** `po/*.po` stays the only place to translate. A script turns it
  into the Mac app's String Catalog (`.xcstrings`) at build time, mapping placeholders (`{name}`
  ↔ positional `%@`) and plural forms. Text the core produces (step names, errors, setup texts)
  arrives already translated from Python.
- **Distribution without paying:** an ad-hoc signed `.dmg`, built on GitHub's free macOS arm64
  runners and attached to every release like the Flatpak and the AppImage. macOS 15 and later
  block its first start; the install guide shows "System Settings → Privacy & Security → Open
  Anyway" with pictures. The Apple Developer Program (99 USD a year) is reconsidered if the Mac
  app finds users.
- **CPU only** in this release. Metal (MPS) is `mac-gpu`, a later module: Demucs and MuScriptor
  measured on a Mac against the CPU (identical notes) before it is used.
- **Testing on a Mac:** no Mac is available to Claude. Swift code is built, linted and tested on
  GitHub's macOS runners (screenshots of the windows as artifacts); the owner checks the app on
  their own Mac (Apple Silicon, macOS 26) at every checkpoint. Modules are cut small for that.
- **Quality bar:** CONSTRAINTS.md is extended to Swift with the same rules: no suppressions
  (`swiftlint:disable`, `// swiftlint:` comments), no stubs (`fatalError("TODO")`,
  `preconditionFailure` as a placeholder), no skipped tests (`XCTSkip` without a reason in the
  commit), SwiftLint clean, XCTest coverage ≥ 95 % outside pure views (pure SwiftUI views are
  excluded as `ui/` is in GTK). The extension is written when `mac-shell` fixes the paths.
- **Out of this release:** everything under "Not Doing" for the GTK app's first version, plus
  playback, corrections, the GPU, the Mac App Store, Intel Macs (Demucs holds them at torch < 2.3),
  Homebrew (a tap stays an idea for technical users).

### Capability map

| Module id | Responsibility | Depends on | Spec |
|---|---|---|---|
| `shared-core` | `stickler_gtk/logic` and `i18n` move to `stickler_app` (no visible change on Linux, the existing tests guard it); `scripts/xcstrings.py` writes the String Catalog from `po/` | – | done, below |
| `mac-design` | Mockups of every screen of the minimum, following Apple's Human Interface Guidelines, made with the owner on the design canvas; no code | – | done, below |
| `mac-core` | The Python core and the app's models on macOS arm64: Demucs' and MuScriptor's `environments` widened (a `digests.yaml` pair for Linux, behaviour unchanged there), the POSIX spots checked, the test suite on a macOS runner | – | approved, below |
| `core-bridge` | `stickler-bridge`: the core as a subprocess speaking JSON lines (analyse with progress and cancel, pages as SVG with bar positions, export, setup, settings, recent songs); the contract lives here, tested in Python | `shared-core`, `mac-core` | approved, below |
| `mac-shell` | SwiftUI app: window, menu bar, open or drop a song, analysis steps with cancel, errors, recent songs, export, the core started and stopped; the setup assistant (consent, model download with progress, resumable, "Remove Downloaded Models…"), moved here from `mac-setup` (owner, 2026-11-18) | `core-bridge`, `mac-design` | approved, below |
| `mac-sheet` | Sheet music in a `WKWebView` from the core's SVG pages, zoom, title, artist and tempo in the window | `mac-shell` | to write |
| `mac-package` | `.app` with `uv` and the core's sources, a Python fetched by `uv` at setup (as in the AppImage), ad-hoc signed `.dmg`, release workflow, install guide with pictures | all | to write |

Build order: `shared-core`, `mac-design`, `mac-core` (in parallel) → `core-bridge` →
`mac-shell` (with the setup, owner 2026-11-18) → `mac-sheet` → `mac-package`.

Out of order on purpose, like the Flatpak sandbox trial before: a **packaging spike** early in
`mac-package` (an ad-hoc signed `.app` from a macOS runner that runs `uv`, builds ADTOF's
environment and analyses a clip on the owner's Mac after "Open Anyway"), because a failure
changes `mac-shell`'s setup and `core-bridge`.

### Tech stack
- Swift 6 and SwiftUI with the Observation framework, deployment target macOS 26 (owner, 2026-11-17), `WKWebView` for the
  sheet music, Swift Package Manager; Xcode as installed on GitHub's `macos-26` arm64 runner
  (Xcode 26.x default, checked on 2026-11-17; the exact version is pinned in the workflow when
  `mac-shell` starts, newest stable at that time).
- SwiftLint, newest release at that time (0.65.x on 2026-11-17), as a pinned binary in CI.
- The Python core unchanged: `uv`, Python 3.12–3.14, the adapters' own environments.
- No new Python dependencies for the bridge (JSON lines over stdin/stdout, standard library).

### Commands (planned)
```
uv run stickler-bridge                     # the core for the Mac app (JSON lines)
uv run python scripts/xcstrings.py         # po/*.po → mac/Stickler/Localizable.xcstrings
xcodebuild -scheme Stickler -destination 'platform=macOS' test   # on a macOS runner
swiftlint --strict mac/
scripts/check.sh task                      # unchanged; also checks the String Catalog is current
```

### Project structure (additions)
```
src/stickler_app/         # the shared app logic (was src/stickler_gtk/logic) and i18n
src/stickler_gtk/         # GTK widgets only, importing stickler_app
mac/                      # the Swift package / Xcode project of the Mac app
mac/Stickler/             # SwiftUI views and the bridge client
mac/SticklerTests/        # XCTest
scripts/xcstrings.py      # String Catalog from po/
.github/workflows/mac.yml # build, lint, test, screenshots; the .dmg on release
docs/install-macos.md     # install guide with the "Open Anyway" pictures
```

### Testing strategy
- The bridge's contract is tested in Python (pytest, the 95 % rule): every message, errors,
  cancellation, a fake analysis as in the GTK widget tests.
- Swift: XCTest for the bridge client and the view models against a recorded or fake core;
  pure views are checked by screenshots on the runner and by the owner.
- `mac-core`: the existing test suite on a macOS arm64 runner, plus the adapters' smoke tests
  for ADTOF and Beat This! on the runner's CPU.
- The String Catalog: a test that every `msgid` is in it, placeholders and plurals kept, for
  every language in `po/LINGUAS`.

### Boundaries
- **Always:** keep the Linux app and the benchmark unchanged in behaviour; run `scripts/check.sh
  task` before every commit; every Swift change goes through the macOS workflow before it counts.
- **Ask first:** paying for anything (Apple Developer Program, runners beyond the free tier);
  changing a model's environment beyond widening its platforms; a new Python dependency; moving a
  feature from Python into Swift.
- **Never:** ship model weights; ship a feature in Swift that the core could do; weaken
  CONSTRAINTS.md for Swift; claim a Mac check that the owner has not done.

### Success criteria
1. On the owner's Mac (macOS 26), the `.dmg` from a GitHub release installs after "Open Anyway", the setup
   assistant downloads the Fast models, and a song becomes sheet music; export of MusicXML, PDF
   and the drum track works.
2. The app is in English, German and Spanish from the same `po/` files as the GTK app.
3. The Linux app, the command line and the benchmark behave as before (all tests green, cache
   keys unchanged except the documented `digests.yaml` pair).
4. The macOS workflow builds, lints and tests on every push; the release attaches the `.dmg`.
5. CONSTRAINTS.md covers Swift; coverage ≥ 95 % outside pure views.

### Open questions
Decided (owner, 2026-11-17): the oldest macOS is 26 (the owner tests on it; the torch wheels
need 14, so 26 is the app's own floor). Decided (owner, 2026-11-18): Fast only in the first Mac
version (see Objective); the bridge is one long-running process per app start that holds the
app's state in Python and sends all of it on every change (module `core-bridge`).

1. Does `uv` run the models from inside an ad-hoc signed `.app` after "Open Anyway" (quarantine
   of the downloaded `uv`, Python and wheels)? Answered by the packaging spike.

### Module `shared-core`

> Status: **done** 2026-11-17 (tasks 92–95, Checkpoint R; the owner checked the app). Approved
> by the owner on 2026-11-17 (the Mac app shares the app ID `ng.tshia.Stickler`). Plan: `tasks/plan.md` ("`shared-core`"), tasks 92–95.

**Objective.** The app's logic and its translations no longer belong to the GTK app but to a
neutral package that both apps use: GTK in process as today, the Mac app later through
`core-bridge`. The Mac app's String Catalog is generated from `po/`. Nothing changes that a
Linux user could see.

**Assumptions** (from the code on 2026-11-17):
1. `src/stickler_gtk/logic/` (15 modules, about 1,500 lines) imports no GTK; it depends only on
   `stickler`, Verovio, `stickler_gtk.i18n` and `stickler_gtk.prefix` (`paths.py`).
2. `po/stickler.pot` has 156 texts, 2 with plural forms, no `msgctxt`, no `%` formats; the
   placeholders are named (`{reason}`, `{name}`, …), one with a format spec (`{size:n}`). German
   and Spanish use `nplurals=2; plural=(n != 1)`.
3. The Mac app's bundle identifier is the same app ID, `ng.tshia.Stickler`.

**Scope.**
1. **Package `src/stickler_app/`:** the 15 modules of `stickler_gtk/logic/` with their names
   unchanged (`stickler_app.session`, `stickler_app.engraving`, …), `i18n.py`, and in
   `__init__.py` what both apps share: `APP_ID`, `APP_NAME`, `prefix()`. `stickler_gtk/logic/`
   and `stickler_gtk/i18n.py` are removed, without re-export shims; `stickler_gtk` imports from
   `stickler_app`. Only moves and import changes: no behaviour, text or signature changes.
2. **Everything that names the old paths:** `pyproject.toml` (packages, coverage source and
   omit), `scripts/i18n.sh` (both packages scanned), the Flatpak manifest and
   `scripts/appimage.sh` (copy `src/stickler_app` too), `scripts/demo.py`, CONSTRAINTS.md (the
   boundary and coverage rows name `stickler_app`).
3. **Boundaries, tested in `tests/gtk/test_boundaries.py`:** `stickler_app` imports no `gi` and
   no `stickler_gtk`; `stickler` imports neither `stickler_app` nor Verovio; `stickler_app` may
   import Verovio (LGPL, the app's alone, as before).
4. **Tests:** the tests of the moved logic move to `tests/app/` (they need no GTK); the widget
   tests (`test_widgets.py`, `test_player.py`) and the boundary test stay in `tests/gtk/`.
5. **`scripts/xcstrings.py`:** writes `mac/Stickler/Localizable.xcstrings` (String Catalog, JSON,
   `"version": "1.0"`, `"sourceLanguage": "en"`) from `po/stickler.pot` and every language in
   `po/LINGUAS`:
   - **Key and placeholders:** the key is the English text with each named placeholder replaced
     by a positional one in order of first appearance: `{reason}` → `%1$@`, a number such as the
     `n` of a plural → `%1$lld`, `{size:n}` → `%1$@` (the core formats sizes). A translation
     uses the same numbers by name, so a reordered sentence stays right.
   - **Plurals:** a `msgid_plural` entry becomes `variations.plural` with `one` (msgstr[0]) and
     `other` (msgstr[1]); a language whose `Plural-Forms` differs from `(n != 1)` makes the
     script stop with an error instead of guessing.
   - **Comments:** `Translators:` comments become the entry's `comment`.
   - **Missing or fuzzy translations** are left out (the app shows English), as gettext does.
   - **Deterministic:** sorted keys, fixed indentation; `--check` exits non-zero when the file in
     the repository differs from what it would write, and `scripts/check.sh` runs it.
   - Swift's own texts (menus, buttons) come into `po/` through extraction from Swift sources,
     which `mac-shell` specifies; this script turns whatever is in `po/` into the catalog.

**Success criteria.**
1. All tests green, coverage ≥ 95 % with `stickler_app` counted; `scripts/gtk.sh test` green.
2. `scripts/gtk.sh` starts the app and an analysis, export and playback work as before (owner's
   quick check on the laptop).
3. Flatpak and AppImage build from the branch and start (as for `packaging`).
4. `po/stickler.pot` is unchanged after `scripts/i18n.sh` (same texts, only source references
   change).
5. `scripts/xcstrings.py --check` passes in `scripts/check.sh`; its tests cover placeholder
   mapping incl. reordering, plurals, comments, left-out entries, determinism and the error for
   an unknown plural rule.
6. Adapter cache keys unchanged (no adapter file touched).

**Out of scope.** `stickler serve` (`core-bridge`); extracting Swift texts (`mac-shell`); any
change of behaviour or text; the Xcode project (only the catalog's path under `mac/` is fixed
here).

### Module `mac-core`

> Status: **approved** by the owner on 2026-11-17 (the peak RAM fix counts as behaviour-neutral on
> Linux, with `digests.yaml` pairs; no Hugging Face token in CI). Plan: `tasks/plan.md`
> ("`mac-core`"), tasks 96–99.

**Objective.** The Python core and the app's models run on macOS arm64 (CPU), checked on every
push by a macOS runner, before any Swift exists. Linux behaves exactly as before.

**Assumptions** (from the code and the research of 2026-11-16, checked 2026-11-17):
1. The app's models are those of its modes: ADTOF and Beat This! (Fast), Demucs and MuScriptor
   medium (Quality). Release 7 replaced none of them (ADR 0008, 2026-11-17).
2. ADTOF's and Beat This!'s locks already hold torch 2.15 wheels for `macosx_14_0_arm64`;
   Demucs', MuScriptor medium's and MuScriptor large's `pyproject.toml` restrict
   `environments` to `sys_platform == 'linux'` (a leftover from an old torch on Intel Macs).
3. The process handling (`os.killpg`, `start_new_session`, `SIGKILL`) and `resource` are POSIX
   and exist on macOS; `torch.cuda` is false there, so `choose_device("auto")` gives the CPU.
4. **Found while writing this spec:** `stickler_adapter._peak_rss_mb` divides `ru_maxrss` by
   1024 because Linux reports KiB; macOS reports bytes, so every Mac `meta.json` would show a
   peak RAM 1024 times too high.
5. ffmpeg and ffprobe come from the `PATH` (Homebrew on the runner); how the app finds them is
   `mac-package`'s question.

**Scope.**
1. **Wider platforms:** Demucs and MuScriptor medium get `environments = ["sys_platform ==
   'linux'", "sys_platform == 'darwin' and platform_machine == 'arm64'"]` and a new lock.
   MuScriptor large likewise (a release 7 candidate; cheap to keep in step). **The Linux
   resolution must stay identical:** a script compares every package, version and wheel hash
   that applies to Linux before and after; only then is the change behaviour-neutral on Linux,
   and the old → new digests go into `src/stickler/digests.yaml` (CLAUDE.md). If anything for
   Linux moves, the change is a real one: stop and ask the owner (results would be recomputed).
2. **Peak RAM on macOS:** `_peak_rss_mb` reads bytes on `darwin`, KiB elsewhere. This edits
   `adapters/_common`, so every adapter's digest changes; on Linux the result is the same
   number, so each adapter gets a `digests.yaml` pair (taken with `stickler cache-digests`
   before and after, in the same commit). A test fixes both units.
3. **macOS in CI:** a job on GitHub's `macos-26` arm64 runner (free for a public repository)
   with Python 3.14 and Homebrew's ffmpeg runs `scripts/check.sh task` (no GTK there; the GTK
   tests stay Linux-only as today). A test that cannot hold on macOS is marked
   `skipif(sys.platform == "darwin", reason=...)` with the reason, never skipped silently, and
   named in the commit message (CONSTRAINTS.md).
4. **The models on the runner's CPU:** the smoke tests of ADTOF, Beat This! and Demucs
   (`pytest -m adapters`, their synthetic clips) after `stickler setup` for those three, in the
   same job or a second one that runs on pushes touching `adapters/` or `src/stickler/`, and
   weekly. MuScriptor is gated (Hugging Face login): on the runner only its lock is checked
   (`uv sync --locked`); it runs on the owner's Mac at the checkpoint if Quality goes into the
   first Mac version.
5. **Times on the runner:** the smoke tests' `meta.json` seconds and peak RAM are printed into
   the job summary, a first look at the CPU cost on Apple Silicon (the owner's Mac gives the
   real numbers later).

**Success criteria.**
1. The macOS job is green on every push: lint, floor guard, all tests with ≥ 95 % coverage.
2. ADTOF, Beat This! and Demucs pass their smoke tests on the runner's CPU, with a plausible
   peak RAM (MB, not GB × 1024).
3. On Linux: every adapter's Linux packages identical before and after (the comparison
   script's output in the commit), all cache entries found under the new digests (nothing
   recomputed: `stickler eval` for the three configs still reads every result), CI green on
   3.12 and 3.14.
4. No test skipped without a stated reason.

**Out of scope.** Metal/MPS (`mac-gpu`); `stickler serve` (`core-bridge`); how the `.app`
ships Python, ffmpeg and `uv` (`mac-package`); Intel Macs; the release 7 candidates other than
keeping MuScriptor large's platforms in step.

**Decided (owner, 2026-11-17):** no Hugging Face token in CI; MuScriptor is only resolved on the
runner and runs on the owner's Mac at the checkpoint (if Quality is in the first Mac version).

### Module `mac-design`

> Status: **done** 2026-11-17: every screen approved by the owner on the private design canvas
> "Stickler Mac screens" (a canvas of its own); sources in [docs/design/mac/](docs/design/mac/README.md).

**Objective.** Mockups of every screen of the Mac app's first version, made with the owner on
the design canvas, following Apple's Human Interface Guidelines for macOS 26. No code. The Mac
modules build what is drawn here, as the GTK modules built the `design` screens.

**Screens** (the minimum of release 8; playback and corrections come later):

| # | Screen | Module |
|---|---|---|
| M1 | First start: consent (what is downloaded, sizes, ADTOF's non-commercial licence) | `mac-shell` (was `mac-setup`, owner 2026-11-18) |
| M2 | First start: download with the setup steps | `mac-shell` (was `mac-setup`, owner 2026-11-18) |
| M3 | First start: a server is not answering (names it, keeps what is done, retry) | `mac-shell` (was `mac-setup`, owner 2026-11-18) |
| M4 | Empty window: drop area, "Open a Song…", recent songs | `mac-shell` |
| M5 | Analysis: the steps, cancel | `mac-shell` |
| M6 | Sheet music: title, artist, tempo and time signature in the window; zoom | `mac-sheet` |
| M7 | Export: menu or toolbar button, the save panel's start, the "saved" note | `mac-shell` |
| M8 | The menu bar: Stickler, File (Open, Open Recent, Export), View (zoom, appearance follows the system), Window, Help | `mac-shell` |
| M9 | Light and dark: M4 and M6 in both | all |

**Carried over from the GTK `design` (same app, same words):** one step list for setup and
analysis (done, running, waiting, a short line each; model names only in setup); English copy
written for drummers, German and Spanish through `po/`; the sheet music inverted in dark mode,
the bar marker blue; tempo and time signature in the window, not on the page; the cost of the
drum track export announced before it starts.

**Different on the Mac (proposed, to settle on the canvas):**
- **Native controls:** SwiftUI's toolbar, buttons, progress and sheets in the system's look and
  accent colour; no libadwaita look.
- **The menu bar carries the commands** (macOS apps put open, export, zoom and appearance there);
  the toolbar keeps open and export only. No hamburger menu.
- **Appearance follows the system**; no three-way switch in the app (macOS apps rarely have one).
- **Note size** as View → Zoom In / Zoom Out / Actual Size (⌘+, ⌘−, ⌘0) instead of the GTK
  menu's "− 100 % +" row.
- **Recent songs** also in File → Open Recent (the system's list), besides the empty window.
- **Errors** as alerts or inline text as the HIG says; the GTK app's toasts become a short note
  in the window.
- **App icon:** the macOS shape (a rounded square the system masks) built from the GTK icon's
  layers (paper, staff, notes, sticks), drawn on the canvas with the screens.

**Success criteria.**
1. Every screen M1–M9 is on the canvas, in light and dark where M9 says so, and approved by the
   owner.
2. The canvas sources are copied to `docs/design/mac/` (the live canvas stays private, as for
   the GTK mockups), and the decisions are written here.
3. Every text on the screens exists in `po/` or is listed for `mac-shell` to add.

**Out of scope.** Playback and corrections screens; narrow windows (macOS windows have a minimum
size; decided in `mac-shell`); the install guide's "Open Anyway" pictures (`mac-package`).

**Decided (owner, 2026-11-17):** a design canvas of its own for the Mac screens (the GTK canvas
stays as it is); the macOS app icon is part of this module.

**Decisions from the mockups (owner, 2026-11-17):**
- **Window:** a unified toolbar (title, and under it artist, tempo and time signature once a
  song is open); on the right a capsule with Open and Export (Export is a menu, disabled without
  a song). The sheet music sits on a grey desk, the page as in the GTK app.
- **First start** comes as sheets over the empty window (consent, download, a server not
  answering), with the GTK app's texts and step list; buttons right-aligned, the default one blue.
- **Export menu** items carry a second line (macOS 14 and later): PDF, MusicXML, Drum Track,
  then Open With…; after saving, a short bar at the bottom of the window with "Show in Finder"
  instead of a toast.
- **Menu bar:** Stickler (About, Remove Downloaded Models…, Hide, Quit; **no Settings window**:
  appearance follows the system and zoom is in View), File (Open… ⌘O, Open Recent, Export, Close
  Window), Edit (the system's), View (Zoom In ⌘+, Zoom Out ⌘−, Actual Size ⌘0, Full Screen),
  Window, Help.
- **App icon:** the GTK icon's layers on the macOS shape, background `#2f5d8c`, a dark variant on
  `#1c1c1e`.
- **New texts for `po/`** (added by `mac-shell`): "Show in Finder", "Takes about 15 seconds",
  "Open Recent", "Clear Menu" (the last two may come from the system).

### Module `core-bridge`

> Status: **approved** by the owner on 2026-11-18 (GTK moves onto the controller in this
> module). Decided before the draft (owner, 2026-11-18): Fast only; one long-running process per
> app start; the state lives in Python and is sent whole on every change. Plan:
> `tasks/plan.md` ("`core-bridge`"), tasks 100–106.

**Objective.** The Mac app reaches the shared core through one subprocess that speaks JSON
lines over stdin and stdout. Python keeps everything that is not drawing: what the window
shows (`stickler_app.session`), the analysis, the setup, exports, recent songs, settings and
every text the user reads, already translated. Swift sends commands and draws the state it is
sent; it never rebuilds a flow. The contract is written and tested here, before any Swift
exists.

**Assumptions** (from the code on 2026-11-18):
1. The states and their changes are in `stickler_app.session` (8 states, pure functions), but
   the flows that drive them live in the GTK window (`stickler_gtk/ui/window.py`, 918 lines):
   the analysis thread and its cancel token, the setup with its download meter sampled twice a
   second, the model check at start (`setup.sync_adapters`, `api.mode_ready`, the stored
   consent), recent songs, "Remove Downloaded Models…" and the drum track export with its cost.
   A bridge that only exposed `session` would leave these to Swift.
2. `stickler` may import nothing but itself (boundary test; the CLI imports only
   `stickler.api`), so the bridge cannot be `stickler serve` as planned: it is an entry point
   of `stickler_app`.
3. The PDF is written by the GTK interface (`ui/pdf.py`: cairo and librsvg from `gi`); the core
   only engraves the A4 pages as SVG (`engraving.a4_pages`).
4. `stickler_app.paths` knows "flatpak" and "appimage" and the XDG folders; a Mac app has
   neither and keeps its files under `~/Library`.
5. Every text the window shows is built in Python with gettext (`steps`, `session.failed`,
   `exports.drum_track_cost`, `recent.rows`, `setup`); the language comes from `LANGUAGE`.

**Scope.**
1. **A GUI-neutral controller, `stickler_app.controller`:** the flows of assumption 1, moved
   out of the GTK window's logic into one class that owns the current `session.State`, runs
   long work in a thread (one job at a time; a new analysis cancels the running one, as now),
   samples the setup meter, and hands every new state to a callback. The host decides on which
   thread the callback runs (GTK: the main loop; the bridge: its writer). Behaviour is the GTK
   window's today, nothing new; the tests drive it with the fake adapters of the widget tests.
2. **The bridge, `stickler_app.bridge`** (entry point `stickler-bridge`, also `python -m
   stickler_app.bridge`): one process per app start, standard library only.
   - **Lines:** one JSON object per line, UTF-8, on stdout; logs and tracebacks on stderr only.
     The bridge's first line is `{"event": "hello", "protocol": 1, "version": "<release>",
     "language": "<code>"}`.
   - **Commands** from Swift: `{"id": <int>, "cmd": "<name>", ...arguments}`. Every command gets
     exactly one reply, `{"id": <int>, "ok": true, ...}` or `{"id": <int>, "ok": false,
     "error": {"code": "<stable id>", "message": "<translated>"}}`. A reply comes at once; long
     work is reported through state events, not through the reply.
   - **Events:** `{"event": "state", "seq": <int>, "state": {...}}` after every change, the
     whole state each time (a few kB; the SVG pages are not part of it), and `{"event":
     "recent", "rows": [...]}` when the recent songs change, and `{"event": "notice", "text":
     "<translated>", "opens": <path or null>}` for a short message the GTK window shows as a
     toast (a correction or the recent songs not saved, a file saved: `opens` names it, so the
     app can offer to open it; the state stays). `seq` grows by one per event, so Swift can drop
     a late one.
   - **The state** as JSON: `kind` (`empty`, `consent`, `setting_up`, `setup_failed`,
     `analysing`, `result`, `exporting`, `failed`) and the fields Swift draws, already
     translated: step rows (`id`, `label`, `detail`, `state`), the consent's models with their
     texts, sizes and licence (from `setup.model_text`, `setup.total_size`), the result's
     `title`, `subtitle`, `tempo`, `meter`, the failure's `title`, `description`, `details`,
     `can_retry`; and which commands are possible now (`can_export`, `can_cancel`, …), so Swift
     enables menu items from the state alone.
   - **Commands** (the minimum of release 8): `start` (the model check; leads to `empty`,
     `consent` or `setting_up`), `agree`, `not_now`, `retry_setup`, `open {path}`, `cancel`,
     `retry`, `close` (back to `empty`), `pages {width, zoom}` (reply: the pages of the current
     result as SVG with width, height and the written bars' rectangles, from
     `engraving.engrave`), `a4_pages` (the A4 pages for the PDF), `export_musicxml {dest}`,
     `drum_track_cost` (reply: minutes, text, whether Demucs is downloaded first),
     `export_drum_track {dest}`, `forget_recent {path}`, `settings` and `set_zoom {zoom}`,
     `zoom_in`, `zoom_out`, `actual_size` (reply: the new zoom), `removal_sizes` and
     `remove_models {everything}`, `quit`.
   - **Errors:** a line that is not JSON, an unknown command or a wrong argument gets an error
     reply (`bad_request`, `unknown_command`, `bad_argument`) and the bridge keeps running; a
     command that does not fit the state (`export_musicxml` without a result) gets `not_now`.
     A failure inside a flow becomes a `failed` or `setup_failed` state, as in GTK. A command
     that fails for an unforeseen reason (a bug) gets `internal`, its traceback goes to stderr,
     and the bridge keeps running (owner, 2026-11-18).
   - **Ending:** `quit`, or stdin closing (the app quit or crashed), cancels the running job,
     waits for its clean-up (at most 2 s, as the GTK window does) and exits 0. The models run
     in their own process groups and are killed by the cancel, so nothing outlives the app.
3. **The PDF stays drawing:** the bridge gives the A4 pages as SVG; writing them into a PDF is
   the interface's job, as `ui/pdf.py` is GTK's (`mac-shell` draws them with WebKit or Core
   Graphics). This needs no new Python dependency (cairo without `gi` would be one: ask first).
4. **A Mac kind in `paths`:** `packaged()` also returns `"macos"` when the app's launcher sets
   `STICKLER_PACKAGED=macos`; then models, results and settings go under `~/Library/Application
   Support/Stickler` and the scores and clicks under `~/Library/Caches/Stickler` (Apple's
   folders), unless XDG variables are set. Linux paths do not change (their tests stay as
   they are).
5. **Translations:** the bridge loads the catalogue of `LANGUAGE`, which Swift sets from the
   user's preferred languages when it starts the process; `hello` names the language found.
   How the `.mo` files reach the `.app` is `mac-package`'s.
6. **The contract on paper:** `docs/bridge.md` lists every command, reply, event and state
   field with an example line. A test checks that the commands in it and in the code are the
   same set, and that every state kind is documented.
7. **GTK onto the controller** (owner, 2026-11-18): the GTK window uses
   `stickler_app.controller` too, so each flow exists once. The widget tests stay as they are and must pass
   unchanged; the owner checks the app on the laptop as at Checkpoint R.

**Testing.**
- The controller: pytest with the fake adapters (an analysis, a cancel in every state, a failed
  setup and Try Again, the consent, the drum track with and without the download, the removal),
  the 95 % rule.
- The bridge in process (its loop reading and writing in-memory streams): every command, every
  error reply, `seq` order, a cancelled analysis, stdin closing during a job.
- The bridge as a real subprocess once: `hello`, `open` on a short fixture song with fake
  adapters until `result`, `pages`, `quit`; and that closing stdin ends it and its model
  process within 3 s.
- On the macOS runner the same tests run (the `macos` job), with `STICKLER_PACKAGED=macos` for
  the paths.

**Success criteria.**
1. `stickler-bridge` passes every test above on Linux and on the macOS runner; coverage stays
   ≥ 95 %.
2. A song becomes a `result` and its pages through the bridge alone, driven by a small script
   (`scripts/bridge_demo.py`) on the laptop with the real Fast models: the same MusicXML as the
   GTK app's for that song.
3. Closing the bridge's stdin in the middle of an analysis leaves no process behind and no
   half-written cache entry.
4. The GTK app behaves as before (widget tests unchanged and green; the owner's quick check),
   and the adapter cache keys are unchanged (no adapter file touched).
5. `docs/bridge.md` matches the code (its test).

**Out of scope.** Swift (`mac-shell`); Quality, playback and corrections (their commands come
with `mac-playback` and `mac-corrections`, the state already carries what they will need); how
the `.app` finds `uv`, Python and ffmpeg (`mac-package`); a socket or several clients; more
than one window.

**Decided (owner, 2026-11-18):** GTK moves onto the controller in this module, as its last
task (scope 7), so no flow exists twice even for a while.
**Decided (owner, 2026-11-18, after Task 100):** the controller reports what the window showed
as a toast as a `Notice`, and the bridge sends it as a `notice` event.

### Module `mac-shell`

> Status: **approved** by the owner on 2026-11-18. Plan: `tasks/plan.md` ("`mac-shell`"),
> tasks 107–116. Decided before the draft (owner,
> 2026-11-18): the owner tries each stage as an app built by CI that starts the core from a
> checkout on the Mac; the Swift code that talks to the core is a package of its own that also
> builds and tests on Linux; when the core stops, the window says so and offers to start it
> again; until `mac-sheet`, a result shows a placeholder and every export works; the setup
> assistant (screens M1–M3) is part of this module, not of a later `mac-setup`.

**Objective.** The first Stickler that runs on a Mac: the SwiftUI window of `mac-design` (M1–M5,
M7, M8 and M9 for M4) over the core that `core-bridge` made. A drummer opens or drops a song,
agrees to the download on the first start, watches the steps, cancels, sees errors, and saves
MusicXML, PDF and the drum track. The sheet music itself comes with `mac-sheet`; the `.dmg`
with `mac-package`.

**Assumptions** (from the code and the web on 2026-11-18):
1. The bridge (`docs/bridge.md`) carries every state, command and text this module needs,
   translated; the app enables buttons and menu items from the state's `can_*` fields alone.
2. A packaged Mac app runs the core with `STICKLER_PACKAGED=macos` and
   `STICKLER_ADAPTER_SOURCES` (the adapters' sources it ships): models, results and settings go
   to `~/Library/Application Support/Stickler`, scores to `~/Library/Caches/Stickler`, and
   "Remove Downloaded Models…" is allowed (`stickler_app.paths`).
3. GitHub's `macos-26` arm64 runner has Xcode 26.6 as its default (26.0.1–26.6 installed,
   runner-images README of 2026-11-02); the `ubuntu-26.04` runner has Swift 6.4.2; SwiftLint
   0.65.1 (2026-08-21) has macOS and Linux binaries; XcodeGen 2.47.0 (2026-11-17) generates
   Xcode 26 projects.
4. On Linux, Foundation has `Process`, pipes and `JSONDecoder`, but not `FileHandle.bytes`
   (swift-corelibs-foundation, main, 2026-11-18): the client reads lines itself.
5. `actions/upload-artifact` drops file permissions in its zip; a `.app` keeps its executable
   bit and signature only as a `ditto` zip or a tar uploaded with `archive: false`.
6. An ad-hoc signed app downloaded in a browser is blocked on its first start; macOS 15 and
   later open it only through System Settings › Privacy & Security › Open Anyway (Apple, support
   article 102445, 2026-05-27).

**Scope.**
1. **`SticklerCore`, a Swift package with Foundation only** (`mac/SticklerCore/`): starts the
   core as a subprocess (`uv run stickler-bridge` in the checkout, with the environment of
   assumption 2), writes commands as JSON lines and reads its lines on a thread of its own (no
   `FileHandle.bytes`), decodes `hello`, `state`, `recent`, `notice` and replies into Swift types
   that mirror `docs/bridge.md`, matches each reply to its command by `id`, and notices when the
   process ends (its exit status and stderr's last 40 lines kept for the error page). An
   `@Observable` model for the window holds the latest state, the recent songs and the notices;
   it never decides a flow, it only forwards commands (SPEC "Release 8", one shared core).
   Builds and tests on Linux (Swift 6.4) and macOS.
2. **The app, `mac/Stickler/`** (SwiftUI, Swift 6, Observation, deployment target macOS 26):
   - **Window** (M4, M5, M9): the unified toolbar with title and, once a song is open, the
     subtitle line; the capsule with Open and Export; the empty window with the drop area,
     "Open a Song…" and the recent songs (a missing file dimmed with a remove button, as in
     GTK); the step list with Cancel for analysis and drum track; the error page with
     "Technical Details", "Open Another Song…" and "Try Again" when `can_retry`.
   - **Result placeholder** (until `mac-sheet`): the grey desk with one centred line, "Sheet
     music ready. Export it as PDF to read it." Never in a release: `mac-package` requires
     `mac-sheet`.
   - **Setup** (M1–M3) as sheets over the empty window: consent with the models, their
     licences and sizes, "Download" and "Not Now"; the download's step list with Cancel and the
     amount downloaded; a failed download naming the server, "Technical Details", "Try Again"
     and "Later". "Remove Downloaded Models…" in the Stickler menu: sizes from
     `removal_sizes`, the checkbox for settings, recent songs and corrections, a destructive
     button.
   - **Exports** (M7): the Export menu with second lines (PDF, MusicXML, Drum Track; Open With…
     opens the MusicXML with the system's chooser); `NSSavePanel` with the core's file name;
     the drum track's cost in an alert first (`drum_track_cost`); the PDF drawn in Swift from
     `a4_pages` (each page's SVG rendered by WebKit, `createPDF`, the pages joined with PDFKit),
     as `ui/pdf.py` does with cairo for GTK. After saving, the bar at the bottom with "Show in
     Finder" (M7); other notices in the same bar.
   - **Menu bar** (M8): Stickler (About, Remove Downloaded Models…, Hide, Quit), File (Open…
     ⌘O, Open Recent with the core's recent songs and Clear Menu, Export, Close Song ⌘W),
     Edit, View (Full Screen only until `mac-sheet` brings zoom), Window, Help (opens the
     README on GitHub). **Close Song** (owner, 2026-11-18, for the Mac and the GTK app): while
     a song is in the window (`can_close`: analysing, result, exporting, failed), ⌘W sends
     `close` and the empty window comes back; otherwise the item reads "Close Window" and ⌘W
     closes the window. The canvas's "Close Window" item is replaced; no back button (a Mac
     app closes a document instead).
   - **The core stopped:** when the bridge exits or does not start (no `uv`, a wrong folder, a
     crash), the window shows "Stickler Stopped Unexpectedly", the technical details (exit
     status, stderr's last lines) and "Start Again", which starts a new core and sends `start`.
     A running analysis is lost; finished results stay in the cache.
   - **Where the core is** (until `mac-package`): on the first start the app asks for the
     Stickler folder (an open panel, the checkout), remembers it, and checks it holds
     `pyproject.toml` and `adapters/`; File › "Choose Stickler Folder…" changes it. `uv` is
     looked for in `~/.local/bin`, `/opt/homebrew/bin` and `PATH`. Gone in `mac-package`, whose
     `.app` brings the core along.
   - **Quitting** sends `quit` and waits at most 3 s for the core to exit, then ends it.
   - **Texts:** every text comes from `po/` through the String Catalog (`scripts/xcstrings.py`);
     the new ones of `mac-design` ("Show in Finder", "Takes about 15 seconds") and of this module
     are added to `po/` with German and Spanish. Window size: at least 640 × 480 points.
3. **The Xcode project** is generated from `mac/project.yml` by XcodeGen (pinned, in CI), not
   committed: a hand-edited `.xcodeproj` cannot be written or reviewed without Xcode, and no one
   here has one. The generated project is a CI artifact for the owner.
4. **CI, `.github/workflows/mac.yml`:** on `macos-26` with Xcode 26.6 pinned: generate, build,
   `swiftlint --strict`, `xcodebuild test` with coverage; screenshots of every screen in light
   and dark (rendered by the tests from fixed states, saved as artifacts); the ad-hoc signed
   `Stickler.app` as a `ditto` zip artifact. On `ubuntu-26.04`: `swift test` for `SticklerCore`
   against the real bridge with stand-in models (as `tests/app/test_bridge_process.py`).
5. **CONSTRAINTS.md for Swift** (SPEC "Release 8", quality bar): no `swiftlint:disable` or `//
   swiftlint:` comments, no `fatalError("TODO")` or placeholder `preconditionFailure`, no
   `XCTSkip`/disabled tests without a reason in the commit, SwiftLint clean, coverage ≥ 95 % for
   `SticklerCore` and the app's models (pure SwiftUI views excluded, as `ui/` in GTK). The
   app's models include the app target's files that are not views (`Exports`, `Removal`,
   `SheetPDF`, `Panels`; owner, 2026-11-18): measured with `xccov` in CI, gated at 95 %; what
   only AppKit can answer (save and open panels, Open With) sits behind a small protocol with a
   fake in the tests;
   `scripts/floor_guard.py` learns the Swift patterns.
6. **`docs/mac-development.md`:** the owner's Mac set up once (Homebrew, `uv`, `ffmpeg`, `git
   clone`), downloading the CI artifact, "Open Anyway", choosing the folder; what to check at the
   checkpoint.

**Testing.**
- `SticklerCore` on Linux and macOS: decoding of every example line in `docs/bridge.md` (the
  same lines the Python doc test checks), replies matched to commands, lines split across
  reads, a core that exits (status and stderr kept), and the real bridge as a subprocess with
  stand-in models: `hello`, `open` until `result`, `cancel`, `quit`.
- The app's models with a fake core (XCTest): each state to what the window offers, the setup
  sheets, the export flows up to the save panel's answer, the core stopped and started again.
- Screenshots: each screen of M1–M5, M7 and the stopped core, light and dark, from fixed states;
  the owner compares them with the canvas.
- The PDF: a test writes it from a fixed `a4_pages` reply and checks the page count, A4 size and
  that the tempo mark's text is drawn (Verovio sets it in the Leipzig font; WebKit must have it).

**Success criteria.**
1. On the owner's Mac (macOS 26), the CI's `Stickler.app` opens after "Open Anyway", finds the
   checkout, asks for consent, downloads the Fast models into `~/Library/Application
   Support/Stickler`, and turns a dropped song into a result; Cancel works during the analysis
   and the download.
2. MusicXML, PDF and the drum track are saved; the PDF has the same pages as the GTK app's for
   that song; "Show in Finder" shows the file.
3. Killing the core (`kill` on its process) shows the stopped page; "Start Again" works.
4. Every screen matches the canvas in light and dark (screenshots, the owner's check); English,
   German and Spanish follow the system's language.
5. `mac.yml` is green on every push: build, SwiftLint strict, tests, coverage ≥ 95 % outside
   pure views; `SticklerCore`'s tests green on Linux too. The Linux app and the core unchanged
   (`scripts/check.sh task` green, no adapter file touched).

**Out of scope.** The sheet music, zoom and the bar marker (`mac-sheet`); the `.dmg`, the
bundled core and Python, the install guide (`mac-package`); playback, corrections, Quality, the
GPU; Intel Macs; the Mac App Store.

**Risks.**
- WebKit draws the page's text without the Leipzig font: the PDF test catches it; Verovio can
  embed the font in the SVG, or the app registers `packaging/fonts/Leipzig.ttf`.
- "Open Anyway" missing on the owner's Mac (reported on macOS 15.1): `xattr -dr
  com.apple.quarantine Stickler.app` in `docs/mac-development.md`.
- Line reading on Linux differs from macOS (old `readabilityHandler` end-of-file reports): the
  client reads with `read(upToCount:)` on its own thread, tested on both.

## Website

> Status: **approved** by the owner on 2026-11-18, after the interview (`docs/intent/website.md`)
> and the mockup (private canvas "Stickler website"). Plan: `tasks/plan.md` ("Website"). Replaces
> the older "GitHub Pages site" idea (a generator-built site from `docs/`), which is dropped.

### Objective
- **User:** a drummer who is not technical and has never seen GitHub.
- **What:** one static page that shows what Stickler does and gets it installed: English at
  `/`, German at `/de/`, plus an about page and a privacy page in both languages. The order
  follows tuxtalk.app (read 2026-11-18): hero, how it works, the examples, the models and the
  computer it needs, a look around, privacy, the downloads, uninstalling, the footer.
- **Success:** someone who is not technical lands on the page and has Stickler installed and
  running without help: on Linux through the Flatpak or the AppImage, on a Mac through the
  `.dmg` including "Open Anyway", shown with pictures.
- **When (owner, 2026-11-18):** built now; online with release 8, when the Mac `.dmg` exists.
  Until then it is built and checked in the repository but not deployed.

### Content (in this order)
1. **Navigation:** the app icon and name, anchors to the sections, "Deutsch"/"English", a
   Download button.
2. **Hero:** one line ("Drop a song, get the drum sheet music." — final wording with the owner),
   a subline, the animated overview (`docs/screenshots/overview.gif`, later a Mac recording
   next to it), Download and "See it work" buttons, four short facts (runs on your computer,
   free and open source, about 15 s per song on a laptop, English/German/Spanish app).
3. **How it works:** four numbered steps: open or drop a song, wait about 15 seconds, read the
   sheet music, export PDF or MusicXML.
4. **An example:** a few seconds of a song (CC BY 4.0, "Fluffing a Duck", as the screenshots)
   next to its sheet music; plain `<audio controls>` (no script).
5. **How good it is:** the honest numbers in plain words, from the report (macro-F1 of Fast on
   the own songs), what it gets wrong (fills, ghost notes) and that corrections exist.
6. **The models and your computer:** each model with what it does, its download size and its
   licence (from the setup assistant's texts); the time per song on a laptop CPU (the apps run
   Fast on the CPU; no GPU figure, as the Mac app has none); disk space.
7. **A look around:** the screenshots (sheet, corrections, dark, the Mac app), each enlarging
   on click with `<a href>` to the image or `<dialog>` without script.
8. **Privacy:** everything runs on the computer; the only network use is the model download.
9. **Get Stickler:** one card per package (Mac `.dmg`, Flatpak, AppImage) with the system it
   needs, its size and a download button; the Mac card shows "Open Anyway" in three pictures
   (from `mac-package`'s install guide); the Flatpak card a copyable command.
10. **Uninstalling:** per package, including "Remove Downloaded Models…".
11. **About the author** (owner, 2026-11-18, instead of "How it's made"): a photo, the
    owner's name and a few lines of their own on who they are and why Stickler exists; that it
    is built with Claude writing the code and the owner deciding; a link to the repository.
    The words and the photo come from the owner.
12. **Footer:** GitHub, the release notes, privacy, about the author, licence (GPL-3.0-or-later).

### Decisions (owner, 2026-11-18)
- **Plain HTML and CSS, no generator.** Two languages are two hand-kept files per page; a test
  keeps them in step (same sections and anchors, same images).
- **Host:** GitHub Pages from this repository through an Actions workflow, custom domain
  `stickler.tshia.ng`: a DNS CNAME record `stickler` → `niklastshiang.github.io`, the domain
  verified in the GitHub account first (TXT record, against takeover), "Enforce HTTPS" once the
  certificate is there. With a workflow, GitHub needs no `CNAME` file (GitHub Docs, "Managing a
  custom domain", read 2026-11-18).
- **Look of its own, matching the app:** calm like libadwaita, on a warm light grey; not
  TuxTalk's look, not GymMane's. Chosen on the mockup (owner, 2026-11-18): **Figtree** as the
  typeface and **Apricot** as the accent (buttons `#f4a26b` with dark text `#2b160a`; links
  and numbers `#a14a16` on light, `#f6b083` on dark; soft fills `#fde4d2` / `#3d2a1f`).
- **Light and dark follow the browser** (owner, 2026-11-18), with no switch and no script:
  the colours through `prefers-color-scheme`, every screenshot through `<picture>` with a
  dark `<source media="(prefers-color-scheme: dark)">`, the overview video through `<video>`
  with a `<source media>` per scheme. So each screenshot and the overview exist twice, light
  and dark, made from the app in its light and dark style.
- **No tracking, no cookies, no third-party requests:** fonts, images and videos served from
  the site. JavaScript only where HTML and CSS cannot do it: `site.js` copies the Flatpak
  command and holds the overview video still under `prefers-reduced-motion` (task 120);
  without it the command is still selectable and the video keeps its pause button.
- **No Spanish, no documentation pages** (the report and the CLI guide stay on GitHub, linked).

### Accessibility and good practice (owner, 2026-11-18: as accessible as the layout allows, and the usual best practices)
Target: **WCAG 2.2, level AA**, for both languages and both colour schemes.
- **Structure:** landmarks (`header`, `nav`, `main`, `footer`), one `h1` per page, headings
  without skipped levels, lists as lists, a "Skip to content" link first; `lang` on every page
  and on words in the other language ("Deutsch").
- **Keyboard:** everything reachable and usable with the keyboard in reading order; a visible
  focus ring (`:focus-visible`, 3:1 against its background); no keyboard traps; anchors move
  the focus to their section.
- **Contrast** (measured 2026-11-18): body text ≥ 6.2:1, links and numbers ≥ 4.9:1 (`#a14a16`
  on the light fills), ≥ 7.3:1 on dark; button text 8.4:1. Colour never carries meaning alone.
- **Text and reflow:** sizes in `rem`, readable at 200 % zoom and at 320 px width without
  sideways scrolling; line length ≤ about 75 characters; no text in images.
- **Targets:** buttons and links in menus at least 44 × 44 px.
- **Motion:** the overview video has visible pause/play controls; with
  `prefers-reduced-motion: reduce` it does not play by itself (a still frame shows); no other
  animation.
- **Media:** every image has `alt` text in the page's language (empty for decoration); the
  audio clip has a visible caption with title, artist and licence; the video has no sound, so
  it needs no captions, and a sentence beside it says what it shows.
- **Speed:** HTML+CSS+fonts < 300 KB; images with `width`/`height` (no layout shift),
  `loading="lazy"` below the first view, WebP; the typeface preloaded, `font-display: swap`;
  the first view under 2 MB.
- **Findable and shareable:** `<title>` and `<meta name="description">` per page, `canonical`,
  `hreflang` between the languages, Open Graph title, description and image, favicon and
  `apple-touch-icon` from the app icon, `robots.txt`, `sitemap.xml`, a 404 page in both
  languages.
- **Safe:** HTTPS enforced; a Content Security Policy as `<meta http-equiv>` (GitHub Pages sets
  no headers) allowing only the site itself; `referrer` policy `strict-origin-when-cross-origin`;
  outside links to GitHub only.
- **Privacy page:** what the app does (nothing leaves the computer) and what the site does: no
  cookies, no tracking, but GitHub Pages, the host, keeps visitors' IP addresses in its logs
  (GitHub's privacy statement, linked).

### Tech stack
- HTML5, CSS (custom properties, `prefers-color-scheme`, `clamp()` for type), the typeface as
  WOFF2 subsets (Latin incl. German), served from the site with its licence.
- Images: the screenshots in light and dark as WebP with a PNG fallback through `<picture>`;
  the overview as a muted looping `<video>` in light and dark, each as AV1 WebM (open-source
  Chromium and some Linux Firefox builds have no H.264) and H.264 MP4 (Safari), with a link
  as fallback; about 80–100 KB each.
  `scripts/demo.py` learns to record in the dark style and to write the screenshots, so both
  sets come from the same run of the app ("Fluffing a Duck", Fast).
- Typeface: Figtree (SIL Open Font License 1.1), weights 400, 500 and 700 as WOFF2 subsets
  (Latin with German), served from `site/fonts/` with its licence; source and version checked
  on the web when it is added.

### Commands (planned)
```
python3 -m http.server -d site 8000        # look at it locally
uv run pytest -q tests/test_site.py        # the site's checks (part of scripts/check.sh task)
```
Deploy: `.github/workflows/site.yml` on a published release (and by hand): copies `site/`,
fills in the release's file names (`Stickler-<n>.flatpak`, …) and sizes from the release,
uploads with `actions/upload-pages-artifact`, deploys with `actions/deploy-pages`.

### Project structure (additions)
```
site/index.html, site/about.html, site/privacy.html     # English
site/de/index.html, site/de/about.html, site/de/privacy.html
site/style.css
site/fonts/                 # the typeface (WOFF2) and its licence
site/images/                # screenshots, the overview video, Open Anyway pictures, the icon
tests/test_site.py
.github/workflows/site.yml
```

### Testing strategy
`tests/test_site.py` (pytest, standard library `html.parser`, runs in `scripts/check.sh task`):
- every local link and image exists; every anchor points to an `id`;
- English and German pages have the same anchors, the same images and the same downloads, and
  link to each other (`hreflang`, `lang` set);
- no request leaves the site (no `http(s)://` in `src`, `@import` or `url()`), no cookies, no
  `<script>` except the allowed one;
- every image has `alt` text (German on the German pages), `width` and `height`; headings do
  not skip levels; one `h1`; the skip link comes first; each page has title, description,
  canonical, `hreflang` and Open Graph tags; the CSP meta is there;
- the page weight stays under a budget (HTML+CSS+fonts < 300 KB; all of the first view < 2 MB).
- **axe-core** (pinned, through Playwright in a CI job of `site.yml`) finds no WCAG 2.2 A/AA
  violation on every page, light and dark (a new CI dependency: asked with this spec).
The owner checks both languages on a phone and a laptop, light and dark, with the keyboard
only and with the screen reader (Orca or VoiceOver) once, before release 8.

### Boundaries
- **Always:** both languages changed together; texts plain and short, for someone who is not
  technical; facts on the page (sizes, times, numbers) from the repository, not from memory.
- **Ask first:** any script beyond the copy button; any third-party service (analytics, fonts,
  comments, a CDN); deploying before release 8; changing the DNS (the owner does it).
- **Never:** tracking or cookies; a claim the report does not back; model weights on the site.

### Success criteria
1. `stickler.tshia.ng` serves the English page over HTTPS, `/de/` the German one; both pass
   `tests/test_site.py`.
2. On a phone and a laptop, light and dark, every section reads well (owner).
3. Someone who is not technical installs Stickler from the page alone on a Mac and on Linux
   (owner, with one person who has not used it).
4. The page makes no request to another server (checked in the browser's network panel).
5. A release updates the download cards without editing the HTML.
6. axe-core reports no WCAG 2.2 A/AA violation; the owner's keyboard and screen-reader pass
   finds nothing that blocks reading or downloading.

### Out of scope (deferred)
- Spanish (the app has it; the site may follow if people ask).
- A documentation site; the report as a web page.
- A language switch by the browser's language (needs script or a server).
- Windows (no Windows version yet).

### Open questions
1. **The typeface** (decided, owner 2026-11-18): Figtree, chosen on the mockup from twelve
   open-licence sans faces (Zed Sans, IBM Plex Sans, Inter, Geist, Manrope, Figtree, Plus
   Jakarta Sans, DM Sans, Instrument Sans, Outfit, Bricolage Grotesque, Atkinson Hyperlegible
   Next); the accent Apricot instead of the icon's brown.
2. **The hero's line** and the four facts, in English and German: shown in the mockup (owner).
3. **The example song** (decided, owner 2026-11-18): "Fluffing a Duck" by Kevin MacLeod,
   CC BY 4.0, as the screenshots.
4. **An imprint (Impressum)?** German law may require one for a site run from Germany even
   without money involved; this is a legal question for the owner, not decided by Claude.

## Decisions (ADRs)
- [0001 Demucs via the fork adefossez/demucs](docs/adr/0001-demucs-fork.md)
- [0002 NC licenses allowed](docs/adr/0002-nc-lizenzen.md)
- [0003 GPU via AMD ROCm wheels](docs/adr/0003-rocm-kanal.md)
- [0004 RoFormer checkpoint BS-Roformer-SW](docs/adr/0004-roformer-checkpoint.md)
- [0005 YourMT3+ variant PS](docs/adr/0005-yourmt3-variante.md)
- [0006 Sequential version numbers](docs/adr/0006-versionierung.md)
- [0007 GPL-3.0-or-later instead of MIT](docs/adr/0007-gpl.md)
- [0008 Two modes, Fast and Quality](docs/adr/0008-modi.md)

## Resolved Questions
1. MuScriptor: the user accepts the license on Hugging Face and logs in with `uvx hf auth login`.
2. ENST Drums: I draft the application, the user submits it. Until the data is available, MDB and the own songs are used.
3. RoFormer checkpoint: chosen while building the adapter, recorded as an ADR.
4. Report: local HTML file.

## Open Questions
- none
