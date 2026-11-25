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
   Changed 2026-11-19 (owner): a song's first bar is never part of a multi-measure rest. The
   tempo mark stands over bar 1 and the rest's count over its middle, and Verovio drew them
   into each other ("= 9722" for 22 empty bars at ♩ = 97). An empty bar 1 is a whole-bar rest
   of its own and the multi-measure rest starts at bar 2 (two empty bars at the start are two
   whole-bar rests). Eye of the Tiger then has 44 written bars: bar 1, a three-bar rest at
   bar 2, and the 42 after it.
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
   bar 3 (inside the first multi-measure rest) marks written bar 1 (bar 2 since 2026-11-19,
   when bar 1 left the rest: module `engine-api`, success criterion 4).
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

> Status: **done** (Checkpoint P, release 7, 2026-11-17). Approved by the owner on 2026-11-16. Candidates chosen by the owner on 2026-11-16
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

> Status: **done** (release 8, 2026-11-20: every module's checkpoint met). Approved by the owner on 2026-11-17 (capability map with `mac-design`, minimum
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
- **macOS only** in this release; Windows gets its own spec ("Release 11 (proposed): Windows app",
  approved 2026-11-24 and 2026-11-25).
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
| `mac-sheet` | Sheet music in a `WKWebView` from the core's SVG pages, zoom, title, artist and tempo in the window | `mac-shell` | approved, below |
| `mac-package` | `.app` with `uv` and the core's sources, a Python fetched by `uv` at setup (as in the AppImage), ad-hoc signed `.dmg`, release workflow, install guide with pictures | all | approved, below |

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
.github/workflows/mac.yml # build, lint, test, screenshots
.github/workflows/release.yml # the .dmg on release (job `mac`, module `mac-package`)
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

> Status: **done** (Checkpoint S, 2026-11-18). Approved by the owner on 2026-11-17 (the peak RAM fix counts as behaviour-neutral on
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
5. ffmpeg and ffprobe come from the `PATH` (Homebrew on the runner); how the packaged app
   finds them is `mac-package`'s question. Until then the app puts Homebrew's prefixes in the
   core's `PATH` (module `mac-shell`, "Where the core is").

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
> The playback screens (M10, for `mac-playback` in a later release) approved on 2026-11-24.

**Objective.** Mockups of every screen of the Mac app's first version, made with the owner on
the design canvas, following Apple's Human Interface Guidelines for macOS 26. No code. The Mac
modules build what is drawn here, as the GTK modules built the `design` screens.

**Screens** (the minimum of release 8, and M10 for the playback of a later release; corrections
come later):

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
| M10 | Playback (a later release): the controls, the volume popover, the Controls menu; light and dark | `mac-playback` |

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

**Out of scope.** Corrections screens (playback: M10, added on 2026-11-24, below); narrow windows
(macOS windows have a minimum size; decided in `mac-shell`); the install guide's "Open Anyway" pictures (`mac-package`).

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
- **App icon:** the GTK icon's layers on the macOS shape, background `#e8894a` (owner, 2026-11-20:
  the website's orange, a little deeper; before `#2f5d8c`; the sticks keep their colours), a dark
  variant on
  `#1c1c1e`.
- **New texts for `po/`** (added by `mac-shell`): "Show in Finder", "Takes about 15 seconds",
  "Open Recent", "Clear Menu" (the last two may come from the system).

**Playback screens M10 (owner, 2026-11-24).** The GTK app's behaviour (module `playback`), drawn
the macOS 26 way, for `mac-playback`:
- **Controls:** a glass capsule floating over the desk at the window's bottom, the sheet
  scrolling under it: Previous Bar, Play/Pause, Next Bar (plain glyphs, as in Apple's Music; the
  step buttons at the owner's wish, the GTK app has only the keys), the time, a position slider,
  the length, "Bar 2 of 110", Volume, and Song · Hits · Both as the native segmented picker.
- **Volume:** a popover above the button with two sliders, Song and Detected hits (70 % and
  100 % at first, remembered per song, as in the GTK app).
- **A Controls menu** between View and Window, named as in Apple's Music: Play or Pause (Space;
  the entry says what Space does now), Previous Bar (←), Next Bar (→), Go to the Start (⌥←, as
  in QuickTime Player; Stickler also takes Home, as on Linux), then Song, Hits and Both with a
  checkmark.
- **The bar marker** in the accent colour; a click on a bar jumps there. The "saved" note (M7)
  moves up above the capsule while a song is open.
- **Checked against Apple's support guides (2026-11-24):** Music names the menu ("Choose
  Controls > Shuffle") and uses Space and the arrows for play and the previous or next song;
  QuickTime Player goes to the beginning of a movie with Option-Left Arrow and does not name
  Home. Not checked: the TV app.
- **New text for `po/`** (added by `mac-playback`): "Controls". Previous Bar, Next Bar, Go to
  the Start, Song, Hits, Both, Volume and Detected hits exist.

### Module `core-bridge`

> Status: **done** (Checkpoint T, 2026-11-19). Approved by the owner on 2026-11-18 (GTK moves onto the controller in this
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
   `LANGUAGE` is written as gettext reads it (owner, 2026-11-19, found at the check on the
   Mac: `de-DE` was not read as German): `de_DE` for the Mac's `de-DE`, and the list ends
   with `en` at the first English entry, because English is the source's language and has no
   catalogue, so gettext would go on to a later language.
   How the `.mo` files reach the `.app` is `mac-package`'s; until then `scripts/mo.sh` builds
   them into the checkout's environment (`docs/mac-development.md`).
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

> Status: **done** (Checkpoint U, 2026-11-19). Approved by the owner on 2026-11-18. Plan: `tasks/plan.md` ("`mac-shell`"),
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
     looked for in `~/.local/bin`, `/opt/homebrew/bin` and `PATH`. The core gets the folder of
     the `uv` that was found and Homebrew's two prefixes (`/opt/homebrew/bin`,
     `/usr/local/bin`) in front of its own `PATH` (owner, 2026-11-19, found at the check on the
     Mac: an app started from the Finder has only the system's folders, so the core found
     neither `uv` for the models nor ffmpeg and ffprobe). Gone in `mac-package`, whose `.app`
     brings the core along.
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

### Module `mac-sheet`

> Status: **done** (Checkpoint X, 2026-11-19). Approved by the owner on 2026-11-18. The sheet's model (scope 1) starts at once
> (owner, 2026-11-18: it is tested on Linux and touches no view); the rest starts when
> `mac-shell`'s checkpoint U is met (the owner's check on the Mac, task 116; met on 2026-11-19).
> Design: screen M6 of `mac-design`
> (`docs/design/mac/Sheet.dc.html`, `Sheet-Dark.dc.html`).

**Objective.** The Mac app shows the sheet music instead of `mac-shell`'s placeholder: the
result's pages, as wide as the window, light and dark, with the note size of the View menu. A
drummer opens a song and reads its drums in the window, as in the GTK app; nothing about the
sheet is decided in Swift (SPEC "Release 8": one shared core, two thin interfaces).

**Assumptions** (from the code on 2026-11-18):
1. The core engraves already (`core-bridge`): `pages` returns the result's pages as SVG at a
   width and note size, with every written bar's rectangle; `settings`, `set_zoom`, `zoom_in`,
   `zoom_out` and `actual_size` keep the note size for every song (0.5 to 3, ×1.25 a step).
   `SticklerCore` decodes `Pages`, `Zoom` and `Settings` already; `AppModel` does not ask for
   them yet.
2. Verovio embeds a subset of the Leipzig font in each SVG (seen in `mac-shell`'s PDF, task
   115), so WebKit draws the tempo mark without the app's font; the app's `Leipzig.ttf` stays as
   the PDF's safeguard.
3. One `WKWebView` holds all pages, one under the other, and scrolls them itself: WebKit draws
   the SVG sharp at every scale, and long songs are one document instead of many views. It runs
   no script of the core's: the SVG is placed in a fixed local page, JavaScript stays off.
4. A width in the core is in CSS pixels, which are points on the Mac; the web view's width in
   points is the width to ask for (Retina is WebKit's business).

**Scope.**
1. **`SticklerCore`, the sheet's model** (tested on Linux and macOS, as `AppModel`):
   - the note size and its percent from `settings` at start, and from each zoom reply;
   - `pages` for the shown result at the sheet's width: asked again when a result arrives
     (a new song or a correction), when the width changes (once it has settled for 0.3 s, as
     the GTK app waits after resizing), and after every zoom change;
   - a reply that a newer request has overtaken is dropped (the newest width and size win);
   - while pages are on their way the old ones stay (no flash of an empty page); a failed
     `pages` reply leaves them and shows the core's message as a notice.
2. **The sheet in the window** (replaces `ResultPlaceholder`): the pages on the grey desk of
   M6, each page white with the canvas's soft shadow (`0 1px 3px`, as Preview and Pages show a
   page; owner, 2026-11-18), one under the other, scrolling vertically only; in
   dark mode the page is inverted (light notes on a dark page), as in the GTK app. The window's
   title and subtitle (artist · tempo · meter) stay as `mac-shell` made them.
3. **Note size:** View › Zoom In ⌘+, Zoom Out ⌘−, Actual Size ⌘0 (`mac-design` M8), enabled
   with a result; a trackpad pinch changes it too: while the fingers move, the shown pages
   grow and shrink with them as a picture, around the pointer; once the fingers lift, the core
   engraves at that size and the pages laid out anew take the picture's place (owner,
   2026-11-19, at the check of task 129: a pinch that shows nothing until the fingers lift does
   not read as a zoom on a Mac; the GTK app applies it once the fingers rest). New pages replace
   the old ones in the loaded page, which is not loaded again for them. The size is the core's
   setting, so it holds for every song and the GTK app's value is not mixed up with the Mac's
   (each app has its own settings folder).
4. **Accessibility:** the web view reads as one image to VoiceOver, labelled with the song's
   title and the page count ("Sheet music of Eye of the Tiger, 3 pages"); the menu items carry
   their shortcuts; nothing in the sheet takes the keyboard focus from the window's controls.
5. **Texts:** "Zoom In", "Zoom Out", "Actual Size" and the VoiceOver label through `po/` with
   German and Spanish (`scripts/xcstrings.py`); the view menu's other items are the system's.

**Not in this module:** the bar marker and a click on a bar (they belong to playback,
`mac-playback`, a later release), corrections (`mac-corrections`), printing (the PDF covers it),
a page view of A4 sheets in the window.

**Testing.**
- `SticklerCore` (Linux and macOS): the sheet model with a scripted core: the first pages at
  the width and stored size; a new result and a correction ask again; a quick series of widths
  makes one request after the pause; zoom in, out and actual size send their commands and ask
  for pages at the new size; a late reply is dropped; a refused `pages` keeps the old pages and
  tells the notice. Coverage ≥ 95 % as before.
- The app (macOS runner): the sheet's HTML for a page (no script, the inversion only in dark
  mode, the pages in order) as plain functions, gated by `scripts/xccov_gate.py` like `Exports`;
  the View menu's items follow the result; screenshots of M6 in light and dark from a fixed
  `pages` reply (the groove of `tests/app/fakes.py`), for the owner to compare with the canvas.
- By hand on the owner's Mac: Eye of the Tiger reads right at 800 and 1600 points, pinch and
  ⌘+/⌘−/⌘0, dark mode, VoiceOver's label.

**Success criteria.**
1. On the owner's Mac, an analysed song shows its sheet music in the window; it fills the
   window's width after a resize and scrolls vertically; the tempo mark is drawn, not a box.
2. ⌘+, ⌘−, ⌘0 and a pinch change the note size; it is kept for the next song and the next start.
3. In dark mode the page is inverted; screenshots of M6 in both appearances match the canvas.
4. `SticklerCore` and the app's logic stay at ≥ 95 % coverage; the `mac` workflow is green.

**Decided (owner, 2026-11-18):** the pinch comes in this module, as the GTK app has it from
`sheet-view`; the page has the canvas's soft shadow, as macOS shows document pages.

**Changed (owner, 2026-11-19, at the check on the Mac):** the pinch's picture follows the
fingers (scope 3); before, the note size changed once, when the fingers lifted.

### Module `mac-package`

> Status: **done** (Checkpoint Z, 2026-11-20). Approved by the owner on 2026-11-19 (the five questions decided, at the end;
> then the build started with `/build auto`, and the spike before `mac-sheet`'s checkpoint X:
> "Spike: your recommendation"). Plan: `tasks/plan.md`, tasks 131–137. The spike (scope 1)
> comes first, as "Release 8" asks; what follows it waits for checkpoint Y. The website's page `install-mac.html` (task 130) takes its pictures from
> this module.

**Objective.** A drummer downloads `Stickler-8.dmg` from the release, drags Stickler to
Applications, allows it once in System Settings, and gets sheet music for a song: no Terminal,
no Homebrew, no checkout. The app brings the core along; `mac-shell`'s folder question is gone.

**Assumptions** (from the code and the web on 2026-11-19; sources with the date read):
1. The core already knows the packaged Mac (`paths.packaged() == "macos"` through
   `STICKLER_PACKAGED=macos`): models, settings and recent songs in `~/Library/Application
   Support/Stickler`, scores in `~/Library/Caches/Stickler`; the shipped adapters are copied
   from `STICKLER_ADAPTER_SOURCES` and refreshed by a new version, as in the AppImage.
2. `uv` 0.13.9 (2026-11-17) is the newest release; its `uv-aarch64-apple-darwin.tar.gz` has a
   published SHA-256 (`5aeca67f…382ca`, fetched and compared 2026-11-19) and is signed by Astral
   since 0.12.12 (astral-sh/uv issue 14870). Signing the app again replaces that signature with
   the app's ad-hoc one. The AppImage pins 0.13.8; both packages move to one version together.
3. Files `uv` downloads later (Python, wheels) are not quarantined: only browsers and the like
   set `com.apple.quarantine` (Apple DTS, developer forums thread 706442; uv issue 16003).
   **Known risk:** on some Macs a Python installed by `uv` is killed at start (uv issue 16726,
   open; reported on macOS 15.6 and 26.6, the maintainers suspect company security software);
   `codesign --force -s -` on it helps. The spike shows whether the owner's Mac is affected
   (it is not: the Python `uv` fetched there ran, 2026-11-19).
4. A quarantined app started from Downloads or from the mounted image may run from a random
   read-only path (app translocation, forums thread 724969). So the app finds everything it
   ships through `Bundle.main` and writes nothing into itself.
5. ffmpeg and ffprobe: no maintained source ships a small static arm64 build under a licence
   that fits. Martin Riedl's builds (9.0.2, GPLv3, SHA-256 per file, versioned URLs; checked
   2026-11-19) are complete video builds, 28 MB zipped each. evermeet.cx has no arm64, BtbN no
   macOS, Homebrew's bottle is bound to `/opt/homebrew`. So they are built here (decision 2).
6. The image needs no Finder: `hdiutil create -srcfolder` on a folder with `Stickler.app` and a
   link to `/Applications` (the runner has no display session for Finder's layout scripts).
   Checked on the runner in the spike, including that helper programs keep their executable
   bit.
7. Opening an app that is not notarised, on macOS 15 and 26 (Apple, Mac User Guide "Open a Mac
   app from an unknown developer", read 2026-11-19): try to open it, then System Settings ›
   Privacy & Security › Security › **Open Anyway** (shown for about an hour), the login
   password, then **Open**. The guide and the website show exactly these steps.

**Scope.**
1. **The spike, before anything else** (a throwaway branch of the workflow, nothing merged
   from it but its findings): an ad-hoc signed `.app` from the runner that holds `uv`, the
   core and the adapters' sources as planned below, in a `.dmg`; on the owner's Mac after
   Open Anyway it sets up ADTOF and Beat This! and analyses a song. It answers: does the core
   start from inside the bundle (also translocated, straight from Downloads); do `uv`'s Python
   and the wheels' compiled parts run (assumption 3); does the executable bit survive the
   image. A failure changes this spec before any task is planned.
   **Answered on the owner's Mac (2026-11-19, macOS 27.0.1, the image of run 44507367954),
   yes to all three, so nothing here changes:** the app copied to Applications and the one
   started straight from the mounted image both start their core, without asking for a
   folder; the core runs with the bundle's Python and a `PATH` of the bundle's `bin` and the
   system's folders only, fetched a Python 3.14.10 through the bundled `uv`, made the
   environments of ADTOF and Beat This! and turned a song into its sheet music; `uv`, ffmpeg
   and ffprobe kept their executable bits and the copied app passes `codesign --verify
   --strict`. Not tried: macOS 26, the deployment target (the owner's Mac runs 27).
2. **What the app holds** (`Stickler.app/Contents/Resources/core/`):
   - `bin/uv`, `bin/ffmpeg`, `bin/ffprobe`, each pinned by version and SHA-256 at build time
     and signed ad-hoc one by one before the app is (Apple DTS: inside out, no `--deep`);
   - `python/`, a relocatable Python with the core's packages (decision 1), and the core's
     own sources (`stickler`, `stickler_app`);
   - `python/share/stickler/adapters` (sources only, never environments or weights), the `.mo` files
     built from `po/` at build time, the Leipzig font as today;
   - the licences of what is shipped (uv, ffmpeg, Python, the wheels) in one folder, linked
     from Help (Help › "Licences" opens the folder; greyed out in a build without its core).
3. **Starting the core:** `CoreClient` starts the bundled core with `STICKLER_PACKAGED=macos`,
   `STICKLER_ADAPTER_SOURCES`, `uv`'s folders inside Stickler's own (`UV_CACHE_DIR`,
   `UV_PYTHON_INSTALL_DIR`, managed Pythons only, as `paths.py` does for the AppImage) and a
   `PATH` that starts with the bundle's `bin`. "Where Is Stickler?", "Choose Stickler
   Folder…" and the search for `uv` and Homebrew leave the app and its texts leave `po/`; a
   debug build keeps the folder through an environment variable for development
   (`docs/mac-development.md` is rewritten for it).
   **Built (task 134):** `CoreClient` itself sets `STICKLER_PACKAGED`, `LANGUAGE` and the
   `PATH`; the adapters' sources and `uv`'s folders the core works out from where it lies
   (`paths.packaged_env`, since the spike). The variable is `STICKLER_CHECKOUT`. Only a build for debugging
   reads it and then runs `uv run stickler-bridge` in that checkout, with the `PATH` it was
   started with (the app looks for no `uv`); a released build ignores it. Before each start
   the client looks for the bundle's Python, `uv`, ffmpeg, ffprobe and the adapters' folder:
   with one of them missing or not executable the core is not started, and "Stickler Stopped
   Unexpectedly" names it, the technical details unfolded. The folder an earlier build
   remembered is removed from the app's defaults at launch.
4. **The app icon** of `mac-design` goes into the app (the consent sheet shows it), with the
   version from `pyproject.toml` in About (a test keeps `project.yml` and `pyproject.toml`
   equal).
5. **Removing:** "Remove Downloaded Models…" with "everything" already empties Stickler's
   folders; the guide says that dragging the app to the Trash afterwards removes the rest.
6. **The release:** `release.yml` gets a `mac` job on `macos-26`: build, sign, image, a start
   test (the app's bundled core answers `hello` and engraves the test groove, without models),
   then `Stickler-<version>.dmg` attached to the release next to the Flatpak and the AppImage
   (`gh release upload`); a manual run gives the image as an artifact. `mac.yml` keeps testing
   every push and stops uploading the bare `.app`.
   **Built (task 136):** the job builds ffmpeg and ffprobe anew from the pinned source rather
   than taking `mac.yml`'s cached build, so nothing a release ships comes from a cache
   (zizmor's `cache-poisoning`; about three minutes more). It signs every Mach-O file of the
   core on its own (`uv`, ffmpeg, ffprobe, Python and the wheels' compiled parts; `uv`'s own
   signature by Astral is replaced), then the app. The start test runs the core twice: straight
   from the read-only mounted image, as a translocated app runs, and from the app copied out
   of it. The spike's workflow is gone; the image to check a build comes from a manual run of
   `release.yml` (its artifact `mac`).
7. **The guide** `docs/install-macos.md` and the README's install section: download, drag,
   Open Anyway step by step, the first start, removing. It has no pictures of its own: for
   the windows macOS shows it points to Apple's guide ("Open a Mac app from an unknown
   developer", Mac User Guide), as the website's page does (owner, 2026-11-19; before, four
   pictures taken on the owner's Mac in light and dark).

**Not in this module:** notarisation and a Developer ID (reconsidered if the Mac app finds
users), updates from inside the app (a new release is a new download), Intel Macs, Homebrew,
the Mac App Store, Quality, the GPU.

**Testing.**
- Python: where a packaged Mac keeps things and which environment `uv` gets (extends
  `tests/app/test_paths.py`); the version check.
- Swift: the bundled core's command line and environment from a bundle folder (on Linux, with
  a made-up bundle); the folder question's removal leaves no state behind for readers who
  used a development build.
- CI: the start test of the built image (mounted, the app copied out, the core asked for
  `hello` and one page); `codesign --verify --strict` on the app and each helper.
- By hand (owner): the success criteria on the owner's Mac, and once on a second Mac or a
  fresh user account if one is at hand (no Homebrew, no checkout).

**Success criteria.**
1. On the owner's Mac, `Stickler-8.dmg` from a draft release installs by dragging, opens
   after Open Anyway, sets up the models after the consent, and turns a song into sheet
   music; PDF, MusicXML and the drum track are saved. No Terminal, no Homebrew's ffmpeg or
   `uv` on the `PATH` (checked with both moved away or on a fresh account).
2. The app is in German and Spanish as the system is set, the core's texts too.
3. Removing everything and trashing the app leaves nothing of Stickler behind (checked with
   `find ~/Library -iname '*stickler*'`). That includes what macOS keeps for the app by its
   identifier (preferences, caches, saved windows): "Remove Downloaded Models…" with
   everything removes them, and once more when the app quits (owner, 2026-11-19).
4. The release workflow attaches the image; `mac.yml` and `check.yml` stay green; the Linux
   packages are unchanged but for `uv`'s version.
5. The website's Mac card has the image's size, and `install-mac.html` leads to Apple's guide
   for the windows macOS shows (owner, 2026-11-19: instead of pictures of our own).

**Decided (owner, 2026-11-19).**
1. **The core's Python is inside the app:** a relocatable Python (python-build-standalone, the
   one `uv` installs, pinned by version and SHA-256) and the core's wheels from `uv.lock` with
   their hashes. The app starts offline and the consent comes before any download. The
   image's size is measured in the spike (estimated 60–80 MB more).
2. **ffmpeg and ffprobe are built on the runner** from ffmpeg's own source (pinned tarball
   and checksum), audio only: the decoders and demuxers for what `paths.AUDIO_SUFFIXES`
   accepts, FLAC and WAV out. The build time and the two programs' size are measured in the
   spike; the licence follows the configuration and is shipped with the others.
3. **M4A/AAC work and are named** (owner, 2026-11-19, after the check below; before it:
   "not promised"): the empty window of both apps and the website's first step say "MP3, M4A,
   FLAC, WAV or OGG". Checked 2026-11-19: the question's premise was out of date. Since 2026-11-13 (331c9c4) every
   format the models cannot read is converted to FLAC by ffmpeg first, so an `.m4a` already
   works (`stickler notate` on an AAC clip of Eye of the Tiger: 59 hits, a MusicXML), as the
   README and `docs/cli.md` say; module `packaging`'s assumption 9 was written before that
   was noticed. The Mac's own ffmpeg has the AAC decoder and read the spike's `.m4a` clip.
   Not checked: playing an `.m4a` in the GTK app (GStreamer's decoder in each package).
4. **No second Mac and no spare account:** success criterion 1 is checked on the owner's Mac,
   with Homebrew's folders and `~/.local/bin` kept out of the app's reach (the app's own
   `PATH` for the core holds the bundle's `bin` and the system's folders only; a test fixes
   that, and the check looks at the core's `PATH` in the technical details). Claude's reading
   of the owner's "no"; to be corrected if a fresh account was meant.
5. **A plain image:** the app and the link to Applications, no background picture.

## Website

> Status: **done**, online with release 8 on 2026-11-20 (Checkpoint W). Approved by the owner on
> 2026-11-18, after the interview (`docs/intent/website.md`)
> and the mockup (private canvas "Stickler website"). Plan: `tasks/plan.md` ("Website"). Replaces
> the older "GitHub Pages site" idea (a generator-built site from `docs/`), which is dropped.

### Objective
- **User:** a drummer who is not technical and has never seen GitHub.
- **What:** one static page that shows what Stickler does and gets it installed: English at
  `/`, German at `/de/`, plus an about page, a privacy page and a legal notice (imprint) in
  both languages. The order
  follows tuxtalk.app (read 2026-11-18): hero, how it works, the examples, the models and the
  computer it needs, a look around, privacy, the downloads, uninstalling, the footer.
- **Success:** someone who is not technical lands on the page and has Stickler installed and
  running without help: on Linux through the Flatpak or the AppImage, on a Mac through the
  `.dmg` including "Open Anyway", step by step, with a link to Apple's own guide.
- **When (owner, 2026-11-18):** built now; online with release 8, when the Mac `.dmg` exists.
  Until then it is built and checked in the repository but not deployed.

### Content (in this order)
1. **Navigation:** the app icon and name, anchors to the sections, "Deutsch"/"English", a
   Download button.
2. **Hero:** one line ("Drop a song, get the drum sheet music." — final wording with the owner),
   a subline, the animated overview (`docs/screenshots/overview.gif`, later a Mac recording
   next to it), Download and "See it work" buttons, four short facts (runs on your computer,
   free and open source, about 15 s per song on a laptop, English/German/Spanish app).
3. **How it works:** a story that follows the scroll (owner, 2026-11-22; before: four numbered
   cards): the four steps scroll by next to a picture that changes with the step in view; see
   "Change 2026-11-22: How it works as a story" below.
4. **An example:** a few seconds of a song (CC BY 4.0, "Eyesplit", as the screenshots)
   next to its sheet music; plain `<audio controls>` (no script), the song with a click on
   every detected hit as the app's "Both" plays it (owner, 2026-11-18), so a visitor hears what
   was written down (`scripts/site_clip.py`).
5. **How good it is:** the honest numbers in plain words, from the report (macro-F1 of Fast on
   the own songs), what it gets wrong (fills, ghost notes) and that corrections exist.
   It links to a page of its own, `accuracy.html` in both languages (owner, 2026-11-18): how
   Stickler works, drawn as an inline SVG that follows light and dark and is translated (the
   apps' path: song → ADTOF and Beat This! → notes → PDF and MusicXML, Demucs for the drum
   track), how it was measured (test sets, ±50 ms, macro-F1, reference errors judged by ear),
   all the numbers of the report's summary in plain words, and a link to the full report.
6. **The models and your computer:** each model with what it does, its download size and its
   licence (from the setup assistant's texts); the time per song on a laptop CPU (the apps run
   Fast on the CPU; no GPU figure, as the Mac app has none); disk space.
7. **A look around:** the screenshots (sheet, corrections, dark, the Mac app), each enlarging
   on click with `<a href>` to the image or `<dialog>` without script.
8. **Privacy:** everything runs on the computer; the only network use is the model download.
9. **Download Stickler** ("Stickler herunterladen"; owner, 2026-11-22, with a joke under it): one list, one row per download (owner, 2026-11-22, after TuxTalk's page;
   before: one card per computer): the Mac's `.dmg`, Ubuntu's `.deb`, Fedora's `.rpm`, the
   Flatpak and the AppImage, each row with the system it is for, its terminal line to copy (the
   Mac's row: the link to `install-mac.html` instead) and its download with the size; below it
   what holds for all (open it with the Software app or run the line in the download folder,
   one way only, the first start's model download). Stacked on a phone. Before that (owner,
   2026-11-20, with release 9; before: one card per package): one card per computer: the Mac card with the `.dmg`, and one Linux card that leads by system (Ubuntu
   26.04+ the `.deb`, Fedora 44+ the `.rpm`, any other Linux the Flatpak or the AppImage), each
   download with its size, and the terminal lines folded away under "In a terminal"; the Mac card shows "Open Anyway" in three pictures
   (from `mac-package`'s install guide); the Flatpak card a copyable command.
   Changed (owner, 2026-11-19): the pictures get a page of their own, `install-mac.html` in
   both languages, linked from the Mac card: a short guide in steps, each with its picture
   (open the `.dmg` and drag the app, the first start's warning, System Settings › Privacy &
   Security › Open Anyway, confirm), and the Terminal line for a Mac without that button.
   The card itself keeps one sentence and the link. The pictures are taken on the owner's
   Mac with the `.dmg` of `mac-package`, in light and dark like every screenshot.
   Changed again (owner, 2026-11-19): the page keeps its steps in words and has no pictures;
   at "Open Anyway" it links Apple's own guide, the German page its German edition
   (`https://support.apple.com/guide/mac-help/mh40616/mac`, `…/de-de/guide/…`, both answered
   on 2026-11-19). Apple shows its own windows there and keeps them current; pictures of
   ours would show one macOS version in one language.
10. **Uninstalling:** per package, including "Remove Downloaded Models…".
11. **About the author** (owner, 2026-11-18, instead of "How it's made"): a photo, the
    owner's name and a few lines of their own on who they are and why Stickler exists; that it
    is built with Claude writing the code and the owner deciding; a link to the repository.
    The words and the photo come from the owner.
12. **Footer:** GitHub, the release notes, privacy, about the author, licence (GPL-3.0-or-later).


### Change 2026-11-22: How it works as a story

> Status: **approved** by the owner on 2026-11-22 (the plan in chat: replace the four cards, no
> hint at any operating system, CSS only). Plan: `tasks/plan.md` ("Website: How it works as a
> story"), tasks 145–149. Seen at tuxtalk.app, whose story switches its picture by script.

**Objective.** A visitor scrolls through four steps and sees each one happen: a song goes in,
Stickler hears the hits, the sheet music follows the song, the files come out. The pictures look
like Stickler's work, not like any desktop: no screenshots, so no title bar, window buttons or
widgets of GNOME or macOS.

**Scope.**
1. **The steps** (English; German alongside, same meaning):
   1. *Open a song*: "Drop an MP3, M4A, FLAC or WAV on Stickler, or choose one." Picture: a file
      card `eyesplit.mp3` over a dashed drop area; it slides in and settles.
   2. *Stickler listens*: "It finds every hit, then the beat and the bars. About 15 seconds."
      Picture: the song's first 20 seconds as a waveform with the detected hits as dots in the
      three groups the clicks have (kick, snare and toms, cymbals), the three stages (hits, beat
      and bars, notes) below; the dots appear from left to right, the stages tick off one after
      the other.
   3. *Read and play along*: "The sheet music follows the song, bar by bar." Picture: the first
      two systems of Stickler's sheet music of the clip and a plain bar with play and time; the
      current bar's mark moves from bar to bar.
   4. *Keep it*: "PDF to print, MusicXML for MuseScore, the drum track to practise with."
      Picture: three file cards, PDF, MusicXML and FLAC; they fan out.
2. **The pictures are made of HTML, CSS and inline SVG** in the site's own look (its colours,
   cards and type, light and dark), from real data: the waveform from the song's first 20
   seconds, the hits from Stickler's Fast analysis of the song (the ones `scripts/site_clip.py`
   clicks), the notes from Stickler's engraving of it (the first two systems, without the tempo
   mark and the music font Verovio embeds for its note, 58 kB that nothing else uses; an `<img>`
   of `site/story/notes.svg`, turned light in dark mode). The site's Content-Security-Policy
   allows no style attributes, so each hit's and bar's part of the scroll is a rule in
   `site/story/story.css`, written with the pictures.
   `scripts/site_story.py` analyses once and keeps the data it needs in the repository
   (`site/story/*.json`), then writes the SVGs from that data; a test fails when the stored SVGs
   differ from what the script makes of the stored data.
3. **Layout:** on a wide screen the text on one side and the picture on the other, the picture
   staying in view (`position: sticky`) while its step's text passes; on a phone the picture
   above its text. Each step carries its own picture, so no picture depends on another step's
   timeline.
4. **Motion in CSS only** (SPEC "Website": JavaScript only where HTML and CSS cannot):
   scroll-driven animations, each picture on its own step's `view()` timeline (Baseline since
   October 2026 per web.dev: Chrome and Edge 115, Safari 26, Firefox 159). No `timeline-scope`
   (its support was not confirmed on 2026-11-22).
5. **Without support or with `prefers-reduced-motion`:** no motion; every picture shows its end
   state (the file in place, all dots and ticks, bar 1 marked, the cards fanned) and the steps
   stand one under the other, complete.
6. **Accessibility:** the pictures are decoration (`aria-hidden="true"`), the text says
   everything; a numbered list (`<ol>`) of the four steps; contrast and focus as every page.
7. **The section's place, anchor and heading stay** (`#how`, "How it works", "So funktioniert’s"),
   so links and the navigation keep working; the four cards and their icons go.

**Boundaries.**
- Always: both languages with the same structure (`tests/test_site.py`), light and dark, no
  horizontal scroll from 320 px up.
- Ask first: sound on the stage, a second song, any JavaScript for it.
- Never: screenshots of an operating system's window in the story; a library for the motion.

**Success criteria.**
1. The four steps with their pictures in English and German, in the order above.
2. In a browser with scroll-driven animations each picture moves with its step's scroll; with
   reduced motion and in a browser without them every end state shows and nothing is cut off.
3. The SVGs come from the stored data by `scripts/site_story.py`, checked by a test.
4. axe 0 violations in light and dark; no overflow at 320, 390, 900 and 1280 px in both
   languages; the owner has seen a scroll recording and the live page.
5. `scripts/check.sh task` green; the site's workflow green.

**Open questions.** None (the owner, 2026-11-22: it replaces the cards; no sound on the stage, as "Hear it, read it" follows right after it, proposed and agreed).

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
- **No Spanish, no documentation pages** (the report and the CLI guide stay on GitHub, linked;
  the accuracy page carries only the report's summary).

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
- **A look around** is a carousel without script (owner, 2026-11-18): CSS scroll snapping, the region focusable for the arrow keys, the next picture peeking in, dots through `::scroll-marker` where the browser has it.
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
  sets come from the same run of the app ("Eyesplit", Fast).
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
- Windows (no Windows version yet; the Windows app is planned in "Release 11 (proposed): Windows
  app", and its card comes with `win-package`).

### Open questions
1. **The typeface** (decided, owner 2026-11-18): Figtree, chosen on the mockup from twelve
   open-licence sans faces (Zed Sans, IBM Plex Sans, Inter, Geist, Manrope, Figtree, Plus
   Jakarta Sans, DM Sans, Instrument Sans, Outfit, Bricolage Grotesque, Atkinson Hyperlegible
   Next); the accent Apricot instead of the icon's brown.
2. **The hero's line** and the four facts, in English and German: shown in the mockup (owner).
3. **The example song** (decided, owner 2026-11-24; before: "Fluffing a Duck" by Kevin MacLeod,
   2026-11-18): "Eyesplit" by Shane Ivers (silvermansound.com), CC BY 4.0, a metal song in the
   owner's genres, as the screenshots. Credit as the site asks: "Music: Eyesplit by Shane Ivers -
   https://www.silvermansound.com"; licence checked on the track's page 2026-11-24.
4. **An imprint (Impressum)** (decided, owner 2026-11-18): yes, `imprint.html` in both
   languages ("Legal notice" / "Impressum", under § 18 Abs. 1 MStV: the site is free and has no
   ads, so § 5 DDG likely does not apply, but it is not purely personal; checked on the web
   2026-11-18, no legal advice), linked from every page's footer. For now with name and email
   only, no postal address (owner, 2026-11-18), although § 18 Abs. 1 MStV asks for one; it and the privacy page follow the owner's own texts for tshia.ng, adapted
   to GitHub Pages as the host (no own server logs) and mailbox.org for mail.

## Release 9: `.deb` and `.rpm`

> Status: **done** (Checkpoint AA, release 9, 2026-11-22). Approved by the owner on 2026-11-20. Plan: `tasks/plan.md` ("Release 9"), tasks 138–144. Decided by the owner on
> 2026-11-20: Ubuntu 26.04 LTS and newer, Fedora 44 and newer; the files on the release page,
> no own repositories (those are a todo for later). Facts checked on the web 2026-11-20.

### Module `linux-packages`

#### Objective

A drummer on Ubuntu or Fedora downloads one file from a release, opens it with the system's
software centre (or `sudo apt install ./…` / `sudo dnf install ./…`), and Stickler is in the
app menu, using the system's GTK, libadwaita and GStreamer like any other GNOME app. Flatpak and
AppImage stay for every other distribution.

#### Assumptions

1. **Systems** (owner, 2026-11-20): Ubuntu 26.04 LTS and newer (`.deb`), Fedora 44 and newer
   (`.rpm`), x86_64. The app needs libadwaita ≥ 1.8 (`Adw.ShortcutsDialog`; `WrapBox` and
   `ToggleGroup` are 1.7): Ubuntu 26.04 has 1.8/1.9, Fedora 44 has 1.9 and Fedora 45 GNOME 51.
   Not supported: Debian 13 (libadwaita 1.7.6) and Ubuntu 24.04 (1.5); the package's dependency
   `libadwaita ≥ 1.8` stops the install there with the package manager's message.
2. **One `.deb` and one `.rpm`**, not one per distribution version, built with nFPM (goreleaser,
   MIT, v2.49.0 of 2026-11-12, active) from one file `packaging/nfpm.yaml`; the nFPM binary is
   pinned by version and SHA-256, as `uv` is.
3. **From the system** (package dependencies): Python 3, PyGObject, GTK 4, libadwaita ≥ 1.8,
   librsvg, GStreamer with the good plugins and libav, ffmpeg, PyYAML. The exact package names
   per family are written in the task and checked by installing into clean containers.
4. **Python 3.14 and 3.15:** Ubuntu 26.04 and Fedora 44 have 3.14, Fedora 45 has 3.15 (its
   default since 2026-11-03). The app's own packages that the systems do not have (numpy,
   mido, packaging, verovio) ship in `/usr/lib/stickler/` as wheels unpacked per Python minor
   version (numpy 2.5.4 has cp315 wheels; verovio is abi3, mido and packaging pure Python); the
   launcher puts the folder of the running Python on the path. PyYAML has no cp315 wheel yet
   (6.0.3), so it comes from the system (`python3-yaml` / `python3-pyyaml`). The app's
   `requires-python` becomes `>=3.12,<3.16` and CI tests 3.15 too.
5. **The models** stay on Python 3.14 as in the AppImage: the bundled `uv` downloads its own
   3.14 into Stickler's folders (`~/.local/share/stickler/python`), so the system's Python
   version never touches the models.
6. **Where things go:** the code under Python's site path is avoided (no clash with the system's
   packages): `/usr/lib/stickler/` holds the three packages, the wheels' folders and `uv`
   (pinned, not on `PATH`, so a system `uv` is untouched); `/usr/share/stickler/adapters` the
   adapters' sources (as in the AppImage); `/usr/bin/stickler-gtk` the launcher; icons, desktop
   file, MetaInfo, `.mo` files and the Leipzig font in the usual `/usr/share` folders.
   `paths.packaged()` learns `"system"` (set by the launcher), with the AppImage's folders.
7. **Names:** the package is `stickler`, version `9`; the release files are
   `Stickler-9_amd64.deb` and `Stickler-9.x86_64.rpm`. Unsigned (GPG signing comes with own
   repositories); a local file installs without a key on both systems (to be checked).
8. **Built and tested in CI** with every release tag, like the other packages: install into
   clean `ubuntu:26.04`, `fedora:44` and `fedora:45` containers, start the app on an invisible
   screen (the window opens, no exception), remove it again (no files left under `/usr`).
9. **Uninstall:** `apt remove` / `dnf remove` removes the program; models and settings stay in
   the home folder until "Remove Downloaded Models…" or by hand, as with the AppImage (README).
10. **Flatpak next to it:** both use the app ID `ng.tshia.Stickler`, so with both installed the
   menu shows two "Stickler" entries; the install texts say to use one.

#### Commands

```bash
uv run python scripts/linux_packages.py build  # builds dist/Stickler-<v>_amd64.deb and .x86_64.rpm
uv run python scripts/linux_packages.py test   # installs, starts and removes them in the three containers
scripts/check.sh task
```

#### Project structure (additions)

```
packaging/nfpm.yaml                  # both packages
packaging/linux/stickler-gtk         # the launcher (Python path per minor version)
scripts/linux_packages.py            # wheels, staging, nFPM, container tests (Python: tested)
.github/workflows/release.yml        # + the .deb and .rpm
src/stickler_app/paths.py            # + packaged() == "system"
```

#### Testing strategy

- Unit: `packaged()` and the folders for `"system"`; the launcher picks the right wheel folder.
- Package contents: every file in place, no adapter environment or weight, no `__pycache__`.
- CI: install, start and remove in the three containers.
- By hand (owner): install the `.deb` on Ubuntu 26.04 and the `.rpm` on Fedora (the owner's
  computer), through the software centre; set up the models, analyse, play and export a song.

#### Boundaries

- **Always:** pinned versions and checksums; the packages built in CI; dependencies from the
  distributions, not copies of system libraries.
- **Ask first:** another distribution or version; own repositories or signing; arm64.
- **Never:** ship model weights; touch files outside the package's own paths; run scripts
  that change the system beyond what the package manager does.

#### Success criteria

1. A release tag attaches `Stickler-<v>_amd64.deb` and `Stickler-<v>.x86_64.rpm`; a manual run
   builds them without a release.
2. Both install, start and uninstall cleanly in clean Ubuntu 26.04, Fedora 44 and Fedora 45
   containers (CI).
3. On Ubuntu 26.04 and on the owner's Fedora, a song can be set up, analysed, played and
   exported (owner).
4. README, website and release notes name both files with their systems.
5. `scripts/check.sh task` is green; the app's tests also pass on Python 3.15.

#### Open questions

- Answered 2026-11-20 (task 141): Fedora's `ffmpeg-free` (8.1 on 44, 9.0 on 45) and its
  GStreamer libav plugin decode MP3 and AAC; the dependencies stay as they are.
- Answered 2026-11-22 (task 144): both Software apps open the files and install them through
  the backend the container test now uses for every release. Ubuntu 26.04's App Center (stable
  channel) claims `.deb` files and installs them through PackageKit: an unsigned file is refused
  while only trusted packages are allowed (`need-untrusted`), then installed. GNOME Software 51
  on Fedora 44 and 45 claims `.rpm` files and installs through dnf5daemon, which takes the
  unsigned file. Not checked: the clicks in either window and how the warning about an unsigned
  package looks (that would need a desktop VM; the owner, 2026-11-22: fine without).

## Release 10 (proposed): keep and remove

> Status: **done** (release 10, 2026-11-24; Checkpoint AB with the owner). Approved by the owner on 2026-11-22 (open questions 1–3 answered; on the owner's
> Bluefin, `appstream:ng.tshia.Stickler` opens Bazaar on Stickler's page with its uninstall
> button). Written at the owner's request from two ideas, "Back up settings and analysed
> songs" and "Uninstall Stickler…", both seen at TuxTalk. Facts on uninstalling checked on the
> web on 2026-11-22. Plan: `tasks/plan.md` ("Release 10: keep and remove"), tasks 150–160.

### Objective
- **User:** a drummer who changes computers, reinstalls the system, or wants Stickler gone,
  and does not know where an app keeps its files.
- **What:** two entries in the apps' menus. **Back Up… / Restore Backup…** keeps what a user
  would miss in one file and brings it back on another computer. **Uninstall Stickler…**
  removes the app and everything it downloaded, the same question on every system, with the
  user's settings kept unless they say otherwise.
- **Success:** after a restore on a new computer, a song analysed before opens with its sheet
  music and its corrections without a new analysis; after an uninstall nothing of Stickler is
  left except what the user chose to keep, without a terminal (one exception, the Flatpak, see
  scope B3).

### Scope A: backup
1. **The menu:** "Back Up…" and "Restore Backup…" in the GTK app's main menu and in the Mac
   app's Stickler menu, next to "Remove Downloaded Models…"; only in an installed app (from the
   checkout the files are the benchmark's, as for the removal).
2. **One file:** `Stickler Backup 2026-11-22.zip`, saved where the user chooses (the file
   chooser; in the Flatpak through its portal, as the exports). A zip, so a user can look
   inside. It holds:
   - `backup.json`: the format's version, the app's version, the date, the system;
   - the settings, the recent songs and the corrections (`settings.json`, `recent.json`,
     `corrections.json`);
   - the models' results for the analysed songs (`results/`, keyed by the song's content and
     the model's code, so they are found again wherever the song now lies), without Demucs's
     separated drum tracks (tens of MB per song; the next drum-track export makes them again)
     and the analysis's own copies of mp3 and m4a songs (`_decoded`, the songs themselves).
     The apps analyse in Fast; a song analysed in Quality (the command line's mode, on
     Demucs's track) needs its analysis again after a restore.
   - Not in it: the models, uv and its Python (downloaded again by the setup assistant), the
     engraved scores and clicks (made again from the results in seconds), the songs themselves
     and the user's exports (they are the user's own files).
3. **Songs found again by content:** today recent songs and corrections are remembered by the
   song's path, which differs on a new computer. Each entry also gets the song's SHA-1 (the
   digest the results cache already uses); when a song is opened whose path is unknown but
   whose content is known, its corrections apply and its recent entry moves to the new path.
   Older entries without a digest get one the next time their song is opened.
4. **Restore:** the app shows what the file holds (date, songs, size) and asks; it then adds
   the results, adds the recent songs and corrections the computer does not have yet (an
   entry already here stays), and takes the backup's settings, except the consent to download
   the models, which stays this computer's (a new computer asks again). A file of a newer format
   version, or not a Stickler backup, is refused with a reason; nothing is changed then.
5. **Across systems:** a backup made by any of the packages or the Mac app restores in any of
   them (only relative paths inside the file; each app puts the parts into its own folders).
6. **Not included:** an automatic history of earlier settings (TuxTalk keeps its last ten):
   Stickler's settings are a few volumes and sizes, nothing an update could break (open
   question 2).

### Scope B: uninstall
1. **The menu:** "Uninstall Stickler…" below "Remove Downloaded Models…", in both apps, only
   in an installed app. The dialog says what goes and how much space that frees: the program,
   the models with their programs and downloads, the saved analyses; one box, off by default,
   "Also remove my settings, recent songs and corrections" (as TuxTalk: a reinstall then picks
   up where the user left off). The user's songs and exports are never touched.
2. **Behind the same dialog, per package** (facts of 2026-11-22):

   | Package | What the app does |
   |---|---|
   | AppImage | Removes its data, the menu entries and icons that an integration tool made for this file (Gear Lever, AppImageLauncher, appimaged: found by `Exec`/`TryExec` pointing at `$APPIMAGE` or by `X-AppImage-Identifier`), moves the AppImage file to the Bin, quits. The running file stays mounted until the app exits (follows from unlink(2); to be checked by a test). |
   | `.deb` / `.rpm` | Asks PackageKit over D-Bus to remove the package (`RemovePackages`; the system asks for the password, polkit `package-remove` is `auth_admin_keep`). The same call on Ubuntu 26.04 and Fedora 44/45, where PackageKit is installed by default; not dnf5daemon, which removes without a password for an administrator. Only after the removal succeeded the app deletes its data, with code it loaded before (the package's files are gone by then), and quits. A cancelled password prompt changes nothing. |
   | Mac | Deletes its folders under `~/Library` (Application Support, Caches, its preferences through `UserDefaults`, saved state, WebKit data), moves its own `.app` to the Bin with `FileManager.trashItem` (a running app may: task 150; no helper needed) and quits. An app running from a translocated path (started from the download without moving it) cannot move itself: it says so and shows the steps. |
   | Flatpak | Removes nothing itself and asks without the box (owner, 2026-11-22: the Software app asks whether the data goes when it uninstalls): it opens the Software app on Stickler's page (`appstream:ng.tshia.Stickler` through the open-URI portal; GNOME Software, KDE Discover and Bazaar claim it) and quits; the user presses Uninstall there and chooses whether the data goes. Where no app claims the link (Ubuntu's App Center does not), the dialog shows `flatpak uninstall --user --delete-data ng.tshia.Stickler` to copy, and that without `--delete-data` the models, settings and recent songs stay. A Flatpak cannot remove itself without the permission to run commands outside its sandbox (`org.freedesktop.Flatpak`), which turns the sandbox off: Stickler does not ask for it. |
3. **The owner's condition** (2026-11-20: "only if it makes sense on every system, otherwise not
   at all"): on three packages the app removes itself; on the Flatpak it removes everything it
   can and hands the last step to the Software app; the owner finds that enough (2026-11-22).
4. **Texts** in English, German and Spanish, in both apps; the website's and the README's
   uninstall texts name the menu entry first and keep the terminal lines.

### Boundaries
- **Always:** ask before anything is deleted; delete nothing when a step before failed or was
  cancelled; only Stickler's own folders and files.
- **Ask first:** a new permission for any package; a backup format others could edit.
- **Never:** the Flatpak's permission to run commands on the host; dnf5daemon for the removal;
  touching the user's songs or exports; deleting anything from the checkout.

### Success criteria
1. A backup made in one package restores in another and on the Mac: the songs open with their
   corrections and need no new analysis (tested with a song moved to another folder).
2. A broken, foreign or newer backup file is refused and changes nothing.
3. In clean containers, the `.deb` and the `.rpm` remove themselves through PackageKit and
   leave nothing in the user's folders (ticked) or only the settings (not ticked); the
   AppImage removes its data, its integration's entries and itself.
4. On the owner's computers: the Mac app goes to the Bin and its folders are gone; the Flatpak
   removes its data and opens the Software app on its page (or shows the command).
5. `scripts/check.sh task` and the `mac` workflow green; coverage as CONSTRAINTS.md.

### Open questions
1. Answered (owner, 2026-11-22): the Flatpak's hand-off to the Software app is enough for the
   condition; the uninstall comes on every package.
2. Answered (owner, 2026-11-22): no automatic history of earlier settings, not now.
3. Answered (owner, 2026-11-22): the box "Also remove my settings…" is off by default.
4. **Checked 2026-11-22:** the owner's Bluefin opens `appstream:` with Bazaar, which shows
   Stickler's page with an uninstall button for the Flatpak installed from a file. Task 150
   (2026-11-22): a running AppImage moved to the Bin keeps running (its file stays open in the
   Bin until it exits; tried with `Stickler-9-x86_64.AppImage` in a folder of the home; in
   `/tmp`, another file system, the Bin refuses, so the app deletes the file there after the
   user agreed); a running Mac app moves its own bundle to the Bin (`FileManager.trashItem`,
   a probe in the `mac` workflow on macOS 26, run 45035344176; no helper needed). **Left for
   the owner's check (task 160):** whether GNOME Software on Fedora Workstation shows an
   Uninstall button for a Flatpak installed from a file (`appstream:<id>`).

## Mac playback (module `mac-playback`)

> Status: **done** (Checkpoint AC, 2026-11-25: the owner's check on the Mac); released with the
> Windows app as release 11 (owner, 2026-11-25; "Release 11 (proposed): Windows app"). Approved by the
> owner on 2026-11-25 (the plan in chat; both open questions answered, below). The screens
> (M10) were approved on 2026-11-24 (SPEC "Module `mac-design`", "Playback screens M10"); this
> section adds what the
> screens leave open: where each decision lives, how the Mac plays two sources in time, what
> the bridge gains. Facts checked on 2026-11-25 on the owner's Mac (macOS 27.2, Command Line
> Tools SDK 26.5) unless named otherwise. Plan: `tasks/plan.md` ("Mac playback"), tasks 161–167.

**Objective.** The Mac app plays what the GTK app plays (module `playback`): the song, the
detected hits as clicks, or both, while the bar marker follows; drawn as M10 draws it. A
drummer hears on their Mac whether the notes are right, as on Linux.

**Assumptions.**
1. The core makes the clicks already: the controller writes `paths.hits_path(song)` after
   every analysis, for both apps (`controller._start`). The bridge's `result` state does not
   name it yet, nor the song's bars in played order (`notation.bars`: start, end, written bar).
2. The GTK app's rules are in `stickler_app.playback` (volumes per Song/Hits/Both, a bar
   click's target, the arrow keys' step, the "Bar 2 of 110" text) and `stickler_app.marker`
   (the bar sounding at a time, its rectangle, the bar under a click), tested there.
3. **AVAudioEngine** plays both sources: two `AVAudioPlayerNode`s into the engine's mixer,
   started together at one host time, so they share one clock as GStreamer's one pipeline
   does; each node's `volume` changes what is heard at once; a seek schedules both from the
   same frame. Its offline manual rendering mode runs it without a sound device, so the CI
   tests the real engine. GStreamer's counterpart is `ui/player.py`.
4. Core Audio (`AVAudioFile`) reads MP3, M4A, FLAC, WAV, AIFF, Opus and Ogg Vorbis on macOS
   27 (tried on the owner's Mac). Not checked on macOS 26, the app's oldest: a song it cannot
   read is played from a FLAC copy the core decodes with its ffmpeg (as
   `stickler.audio.readable` does for the models), once, into the cache.
5. Content JavaScript stays off in the sheet's web view (`mac-sheet`); the app's own scripts
   (`callAsyncJavaScript`) run, as the pinch's picture does. The marker and a click's page
   point are such scripts.
6. The bridge handles one command at a time; `pages` takes a moment while it engraves. A
   command sent then waits for it (`docs/bridge.md`).

**Where each decision lives** (SPEC "Release 8": one shared core; moving work into Swift is
asked first, so it is listed here for the owner):
- **Python (the core, tested once):** the bars in played order with their "Bar n of N" text,
  sent in the `result` state; the clicks file; a bar click's target (`jump`) and the arrow
  keys' step (`step`); the gains for Song/Hits/Both and the remembered volumes (`volumes`); the
  playable copy of a song (`playable`).
- **Swift, lookups at 20 frames a second** (a round trip per frame would wait behind `pages`):
  which of the core's bars sounds at the player's position, the rectangle that marks it (the
  core's page rectangles; a bar inside a multi-measure rest is shown by the engraved bar
  before it, as `marker.locate`), the bar under a click (`marker.bar_at_point`) and the time
  as "0:06" (`playback.clock`, no translation). Each mirrors its Python function and is tested
  with the same cases as the Python tests.
- **Swift, the player:** the engine itself, as `ui/player.py` is GTK's.

**Scope.**
1. **The bridge** (`stickler_app.bridge`, `docs/bridge.md`, protocol stays 1: fields and
   commands are only added):
   - `result` gains `clicks` (the clicks file, `null` when it is not there) and `bars`: in
     played order, each `{"start", "end", "bar", "label"}` (seconds, the written bar,
     "Bar 3 of 110"). A correction sends new bars with its new state.
   - `jump {bar, at}`: the time a click on written bar `bar` goes to from position `at`
     (`playback.jump_target`; `null` when the song never plays it). `step {at, by}`: the
     start of the bar `by` bars away (`playback.step`). Only on a result; `not_now` otherwise.
   - `volumes {hear, song?, hits?}`: remembers the given volumes (0 to 1) in the settings and
     replies with the gains to play, `{"song", "hits"}` (`playback.volumes`, with the stored
     volumes for the ones left out). `settings` already sends `song_volume` and `hits_volume`.
   - `playable`: the result's song as a file the Mac plays, a FLAC copy decoded once into
     the app's cache (`playable/`, beside the clicks in `hits/`; caches are never part of a
     backup). Asked only when Core Audio cannot read the song.
2. **`SticklerCore`** (Linux and macOS): the new fields and commands; `PlaybackModel`
   (`@Observable`, owned by `AppModel` as `playback`): the player behind a protocol
   (`Playing`: load, play, pause, seek, position, gains, stop; a fake in the tests), playing
   or paused, the position and length, the sounding bar's index and label, the marked bar,
   Song/Hits/Both, the two volumes from `settings`; a tick every 50 ms only while playing;
   play, pause, seek, previous and next bar (`step`), go to the start, a bar click (`jump`;
   when stopped it moves the position without playing); at the song's end it stops, and play
   starts from the beginning; a new song, Close Song, a new core or the stopped core stop the
   player at once. A player that fails shows its error as the window's notice.
3. **The player** (app target, `Player.swift`): AVAudioEngine as in assumption 3; the song
   from its file or, when `AVAudioFile` refuses it, from `playable`; the clicks only when the
   file is there; the engine's configuration change (headphones unplugged, another output)
   pauses playback instead of losing it; nothing holds the sound device once stopped.
4. **The controls** (M10): the glass capsule floating over the desk at the window's bottom
   (`glassEffect`), the sheet scrolling under it: Previous Bar, Play/Pause, Next Bar, the
   time, the position slider, the length, "Bar 2 of 110", Volume (a popover with the Song and
   Detected hits sliders) and Song · Hits · Both as the segmented picker. VoiceOver names
   every control ("Position" with the time and bar as its value). The "saved" note sits above
   the capsule while a song is open. Shown with a result only (not during an export's steps).
5. **The marker and bar clicks:** the sounding bar's rectangle drawn over the page in the
   system's accent colour, also on the inverted dark page (drawn outside the inverted
   paper), and scrolled into view when it leaves it; a click on a bar jumps there. Both by the
   app's own scripts in the loaded page (assumption 5); the page's own scripts stay off.
6. **The Controls menu** between View and Window: Play or Pause (Space; the item reads "Play"
   or "Pause", what Space does now), Previous Bar (←), Next Bar (→), Go to the Start (⌥←;
   Home does the same), then Song, Hits and Both with a checkmark. Enabled with a shown result.
7. **Texts:** "Controls" new in `po/` with German ("Steuerung", as in Apple's Music) and
   Spanish ("Controles"); the others exist.

**Not in this module:** loops, slower playback, muting single drums (GTK's "Not Doing" too),
drum samples, the Now Playing widget and media keys, remembering the position per song.

**Testing.**
- Python: the new state fields (bars and labels, clicks or `null`, a correction's new bars),
  `jump`, `step`, `volumes` (gains per mode, remembered, bad values `bad_argument`), `playable`
  (a copy once, `not_now` without a result), the doc test for the new lines; 95 %.
- `SticklerCore` with a scripted core and a fake player: every control, the tick only while
  playing, the end, stopping on a new song, close, a new core and a stopped core, a refused
  command as a notice; the lookups with the Python tests' cases; 95 %.
- The player on the macOS runner in offline rendering: both sources start together, a seek
  lands on its frame, the gains mute one source (measured in the rendered samples), the end is
  reported once, stop leaves the engine stopped; the fallback to `playable` when a file cannot
  be read. Counted by `scripts/xccov_gate.py` (`Player`, and the marker's and click's script
  builders), 95 %.
- Screenshots of M10 in light and dark, with the volume popover, from fixed states.
- By hand on the owner's Mac: Eye of the Tiger with clicks by ear, Song/Hits/Both and the
  volumes without a gap, the marker in dark mode, a click inside repeats, Space, ←, →, ⌥←,
  Home, the menu's checkmarks, headphones unplugged, quitting while playing.

**Success criteria.**
1. On the owner's Mac a song plays with its clicks in time with the drums (by ear); pause,
   resume, the slider, Previous and Next Bar work.
2. Song/Hits/Both and both volume sliders change what is heard without a gap; the volumes are
   the same after a restart.
3. The marker follows the sounding bar within 0.1 s in the accent colour, light and dark, and
   keeps it in view; a click on a bar inside repeat signs jumps to its next pass.
4. The Controls menu and its keys work as in scope 6; the item says what Space does.
5. Opening another song, Close Song and quitting stop the sound at once.
6. The screens match M10 in light and dark (screenshots, the owner's check).
7. `scripts/check.sh task` green; `SticklerCore` and the app's logic ≥ 95 %; the `mac` workflow
   green; the GTK app and the benchmark unchanged.

**Decided (owner, 2026-11-25):**
1. "Remembered per song" (M10) means what the GTK app does: one pair of volumes kept for
   every song, like the note size.
2. Playback comes in a release together with other work, not in a release of its own.

## Release 11 (proposed): Windows app

> Status: **capability map approved** by the owner on 2026-11-24 (open questions 2–4 decided as
> proposed; Windows 11 only, the owner's PC runs it). **Changed by the owner on 2026-11-25**
> (open questions 5–7): the first version has what the Mac app has, playback, backup and
> uninstall included; release 11 is the Windows app and the Mac playback together; Claude may
> build and test on the owner's PC itself. A second draft written that day on a stale checkout
> was replaced by this section when the branches were merged. Module specs follow in build order. Written from the owner's interview of 2026-11-24
> ([docs/intent/windows-app.md](docs/intent/windows-app.md)) and the Windows research in
> `tasks/todo.md` (2026-11-16); facts checked on the web on 2026-11-24 (sources below). Module
> specs are written and approved one at a time, in build order, as for the Mac app.

A native Windows app (WinUI 3, C#) for the same drummers as the other two apps, built the way
the Mac app is: a thin interface over the shared Python core, reached through
`stickler-bridge`. Windows is the gap the website still shows next to Linux and the Mac.

### Objective
- **User:** a drummer with a Windows PC (x64, Windows 11) who finds Stickler through the
  website and is not technical.
- **First version (owner, 2026-11-25: the same state as the Mac app; replaces "so wie
  Release 8 beim Mac" of 2026-11-24):** what the Mac app has when release 11 is cut. On
  2026-11-25 that is: the setup assistant (consent, model download with progress, resumable,
  "Remove Downloaded Models…"), open or drop a song, the Fast analysis on the CPU with progress
  and cancel, the sheet music with zoom, export of MusicXML, PDF and the drum track, recent
  songs, every language in `po/LINGUAS`; release 10's "Back Up… / Restore Backup…" and
  "Uninstall Stickler…"; and playback as `mac-playback` built it (song, clicks or both, the
  bar marker; screens W10). Corrections are not in it: the Mac app has none yet. Whatever else
  reaches the Mac app before release 11 joins this list.
- **The same everywhere, from release 11 on (owner, 2026-11-24 and 2026-11-25):** release 11
  is the Windows app and the Mac playback together, released when both apps are at the same
  state; the Mac playback, done on `main`, waits for it. From then on every new feature ships
  in all three apps in the same release.
- **Success:** a drummer downloads `Stickler-11-setup.exe` from a GitHub release, installs it
  without administrator rights, gets past SmartScreen with the website's guide, and gets sheet
  music for a song without a terminal.

### Decisions for all modules (owner, 2026-11-24)
- **Native interface, the Mac pattern:** WinUI 3 (Windows App SDK) and C#. Not Qt, GTK or
  Electron. The Python core, the bridge's contract and `po/` are shared; C# only draws and
  forwards, as Swift does. Anything the core could do is not built in C#.
- **A C# `SticklerCore`:** the bridge client and the view models, as a plain `net10.0` class
  library without Windows APIs, so it builds and is tested on Linux too (as `mac/SticklerCore`
  is with `swift test`). The WinUI app references it.
- **Distribution without paying:** a per-user installer made with Inno Setup (no administrator
  rights, `PrivilegesRequired=lowest`), x64, built on GitHub's free Windows runners and attached
  to every release next to the `.dmg`, the Flatpak, the AppImage, the `.deb` and the `.rpm`.
  Unsigned at first; the install guide shows SmartScreen's "More info → Run anyway" with
  pictures. In parallel, an application to the SignPath Foundation (free for OSI-licensed open
  source; needs a code signing policy page on the website and builds on GitHub-hosted runners);
  once approved, every release is signed. No paid certificate.
- **CPU only**, as the Mac app at release 8. CUDA on Windows is a later module.
- **Testing on Windows (changed by the owner on 2026-11-25):** Claude's sessions also run
  natively on the owner's PC, the company laptop (Windows 11 23H2; .NET SDK, `uv` and the
  WebView2 runtime present, checked 2026-11-25), and Claude may build, test and start the app
  there and run the models on its CPU. Its network inspects TLS: `uv` downloads only with
  `UV_SYSTEM_CERTS=1`. GitHub's Windows runners stay the check every C# change goes through;
  `SticklerCore` is tested on Linux too. The owner checks the app on the same PC at every
  checkpoint. Modules are cut small for that.
- **Quality bar:** CONSTRAINTS.md is extended to C# with the same rules as for Swift: no
  suppressions (`#pragma warning disable`, `[SuppressMessage]`, `.editorconfig` severities
  lowered to `none`; a grep in the check, since no analyzer forbids them), no placeholder
  `throw new NotImplementedException()`, no `[Ignore]` without a reason in the commit, the
  build with `TreatWarningsAsErrors`, `AnalysisLevel=latest-recommended` and
  `EnforceCodeStyleInBuild`, `dotnet format --verify-no-changes` clean, coverage ≥ 95 % in
  `SticklerCore` and the app's logic types (pure XAML views excluded, as SwiftUI views are).
  The extension is written when `win-shell` fixes the paths.
- **Out of this release:** corrections (the Mac app has none yet), CUDA (later, owner
  2026-11-25), ARM64, `.msi`/WiX, winget, Scoop, the Microsoft Store, a paid certificate,
  features only Windows has.

### Capability map

| Module id | Responsibility | Depends on |
|---|---|---|
| `win-design` | Mockups of every screen of the minimum following Microsoft's Windows 11 design guidance (Fluent, Mica, the title bar, light and dark), made with the owner on the design canvas; no code | – |
| `win-core` | The Python core and the Fast models plus Demucs on Windows x64: the POSIX spots made portable (cancel without `os.killpg`, peak RAM without `resource`; `digests.yaml` pairs, Linux unchanged), Demucs' and MuScriptor medium/large's `environments` widened to `win32` (Linux resolution identical), `paths` knows `STICKLER_PACKAGED=windows` (`%LOCALAPPDATA%\Stickler`), the test suite and the smoke tests on a Windows runner | – |
| `win-spike` | Before any interface: a throwaway Inno Setup installer from the runner holding `uv`, the core and the adapters' sources; on the owner's PC it installs per user past SmartScreen, sets up ADTOF and Beat This! and analyses a song (answers open questions 3 and 4) | `win-core` |
| `win-shell` | WinUI 3 app and the C# `SticklerCore`: window, menus, open or drop a song, analysis steps with cancel, errors, recent songs, export, the setup assistant, "Back Up… / Restore Backup…" (release 10, through the bridge), the core started and stopped; the app's own texts from `po/` (`scripts/winstrings.py`); CONSTRAINTS.md for C#; `.github/workflows/win.yml` | `core-bridge` (done), `win-design`, `win-spike` |
| `win-sheet` | Sheet music in WebView2 from the core's SVG pages (a virtual host mapped to the score folder), zoom, title, artist and tempo; the PDF from the A4 pages through WebView2's print to PDF | `win-shell` |
| `win-playback` | Added 2026-11-25: what `mac-playback` does, drawn as W10: the song, the clicks or both in time, volumes, the bar marker, a click on a bar, the keys; the rules stay in `stickler_app.playback` and `marker`, the bridge's playback commands are reused; the Windows audio library (two sources from one clock, as `AVAudioEngine` on the Mac) chosen in its spec, maintenance and licence checked on the web | `win-sheet` |
| `win-package` | The installer (Inno Setup, per user, Start menu entry, an uninstall entry in Settings › Apps), "Uninstall Stickler…" as release 10 asks of every system, `uv`, ffmpeg and ffprobe pinned by SHA-256, refusing Windows 10 with a clear message, the release job, `docs/install-windows.md` and the website's download card and guide in English and German; the SignPath application | all |

Build order: `win-design`, `win-core` (in parallel) → `win-spike` → `win-shell` → `win-sheet` →
`win-playback` → `win-package`. The spike comes earlier than the Mac's did, because the risks are in the
packaging (long paths, SmartScreen, `uv` under `%LOCALAPPDATA%`) and a failure there changes
`win-shell`'s setup and the core's folders.

### Tech stack (checked 2026-11-24)
- C# on **.NET 10** (LTS until 2028-11), **Windows App SDK 2.7** (2026-11-17; the 2.0 line is
  serviced until 2027-04-29), **unpackaged and self-contained** (`WindowsAppSDKSelfContained`,
  .NET self-contained): the runtime lies next to the `.exe` in the install folder, no MSIX, no
  bootstrapper. No Native AOT and no trimming (reflection-based bindings warn there).
- **WebView2** through the Windows App SDK's control. Windows 11 includes its runtime, so the
  installer brings no bootstrapper.
- **Inno Setup** (7.1.1, 2026-10-28; the runners have 6.7.1, the version is pinned when
  `win-package` starts).
- **ffmpeg and ffprobe:** a static GPLv3 build pinned by version and SHA-256 (gyan.dev's
  versioned "essentials" archive, about 35 MB as `.7z`, or a dated BtbN build; chosen in
  `win-package`). GPL fits Stickler's GPL-3.0-or-later.
- Tests: MSTest with Microsoft.Testing.Platform and its code coverage (Cobertura).
- The runners: `windows-2025` (Visual Studio 2022 17.14 with the Windows App SDK C# workload,
  Windows SDK 26100), free for a public repository.
- The Python core unchanged otherwise: `uv`, Python 3.12–3.14, the adapters' own environments.

### Commands (planned)
```
uv run stickler-bridge                         # the core for the app (unchanged)
uv run python scripts/winstrings.py            # po/*.po → win/Stickler/Strings/*.json
dotnet test win/SticklerCore.Tests             # also on Linux
dotnet build win/Stickler.sln -c Release       # on a Windows runner
dotnet format win/Stickler.sln --verify-no-changes
iscc win/installer/Stickler.iss                # on a Windows runner (win-package)
scripts/check.sh task                          # unchanged; also checks the strings are current
```

### Project structure (additions)
```
win/                          # the Windows app
win/Stickler/                 # WinUI 3 app (XAML views, the window, WebView2 page)
win/SticklerCore/             # net10.0 class library: bridge client, view models (no Windows APIs)
win/SticklerCore.Tests/       # MSTest, runs on Linux and Windows
win/Stickler.Tests/           # MSTest for the app's logic types (Windows runner)
win/installer/Stickler.iss    # Inno Setup script (win-package)
src/stickler_app/win_texts.py # texts only the Windows app shows, collected into po/ (as mac_texts.py)
scripts/winstrings.py         # the app's string tables from po/
.github/workflows/win.yml     # build, analyse, test, screenshots if the runner allows them
docs/install-windows.md       # install guide with the SmartScreen pictures
```

### Testing strategy
- The bridge's contract stays tested in Python; the Windows app adds nothing to it unless a
  module spec says so (the Mac-only texts' model: Windows-only texts in `win_texts.py`).
- C#: MSTest for `SticklerCore` against a fake core (as `mac/SticklerCore`'s tests), on Linux in
  `scripts/check.sh` when the .NET SDK is present and on the Windows runner always; the app's
  logic types tested on the runner; pure XAML views checked by the owner and, if the runner has
  a desktop session, by screenshots (unconfirmed; the spike tries it).
- `win-core`: the existing test suite on a `windows-2025` runner, plus the smoke tests of ADTOF,
  Beat This! and Demucs on its CPU.
- The string tables: a test that every `msgid` is in them, placeholders and plurals kept, for
  every language in `po/LINGUAS`.

### Boundaries
- **Always:** keep the Linux and Mac apps and the benchmark unchanged in behaviour; run
  `scripts/check.sh task` before every commit; every C# change goes through the Windows
  workflow before it counts.
- **Ask first:** paying for anything (a certificate, runners beyond the free tier); changing a
  model's environment beyond widening its platforms; a new Python dependency; a NuGet package
  beyond the Windows App SDK, MSTest and its coverage; moving a feature from Python into C#.
- **Never:** ship model weights; ship a feature in C# that the core could do; weaken
  CONSTRAINTS.md for C#; claim a Windows check that the owner has not done.

### Success criteria
1. On the owner's Windows PC, the installer from a GitHub release installs without
   administrator rights after "Run anyway", the setup assistant downloads the Fast models, and
   a song becomes sheet music; export of MusicXML, PDF and the drum track works; the app is
   listed under Settings › Apps and its uninstall removes the program; the song, the clicks
   and both play with the bar marker following; "Uninstall Stickler…" leaves nothing behind
   but what the user chose to keep.
2. The app is in every language of `po/LINGUAS`, from the same `po/` files as the other apps.
3. The Linux and Mac apps, the command line and the benchmark behave as before (all tests
   green, cache keys unchanged except the documented `digests.yaml` pairs).
4. The Windows workflow builds, analyses and tests on every push; the release attaches the
   installer; the website offers it, with the install guide, in English and German.
5. CONSTRAINTS.md covers C#; coverage ≥ 95 % outside pure views.
6. A backup made on the Mac or on Linux restores on Windows and the other way round: a song
   analysed before opens with its sheet music without a new analysis.

### Out of scope (deferred)
- Corrections: they come to Windows and the Mac in the same later release.
- CUDA: measured against the CPU first, as `mac-gpu` (owner, 2026-11-25: later).
- Windows 10: out of Microsoft's support since 2025-10-14 (owner, 2026-11-24: Windows 11
  only).
- ARM64 Windows: torch's and the models' wheels for `win_arm64` not checked.
- `.msi`/WiX, winget, Scoop, the Microsoft Store: an installer people download is enough.
- Native AOT: not needed for an app that starts a Python core.

### Open questions
1. **Decided (owner, 2026-11-24): Windows 11 only.** Microsoft ended Windows 10's support on
   2025-10-14 (consumer ESU until 2027-10-12); about a quarter of desktop Windows was still 10
   in October 2026 (StatCounter). The installer refuses Windows 10 with a message that names
   Windows 11; the website says "Windows 11". The owner's PC runs Windows 11.
2. **Decided (owner, 2026-11-24): the app's language.** the Mac app follows the system. Windows' own resource system
   (`.resw`, MRT Core) needs MakePri for an unpackaged app, follows only the display language
   and has no plurals. `scripts/winstrings.py` writes one JSON table per language
   from `po/` (the same placeholder and plural rules as `scripts/xcstrings.py`), and a small
   C# lookup picks the user's first preferred UI language that `po/` has, else English. No
   NuGet package.
3. **Decided (owner, 2026-11-24): long paths.** Windows limits paths to 260 characters unless `LongPathsEnabled` is set
   (administrator rights); `uv` handles long paths only with it, and deep PyTorch paths have
   failed elsewhere (WinError 206). The core's folders stay short
   (`%LOCALAPPDATA%\Stickler\` with `uv`'s Python and cache under it); the spike installs the
   models under a long user name to see whether that is enough.
4. **Decided (owner, 2026-11-24): SmartScreen and Smart App Control.** an unsigned installer shows "Windows protected your
   PC" for every new version (reputation is per file hash); Smart App Control, when on, blocks
   unsigned programs outright, and the bundled `uv.exe`, `python.exe` and ffmpeg too
   (unconfirmed which). The spike checks it on the owner's PC; with Smart App Control on, the
   guide can only say to wait for the signed release.
5. **Decided (owner, 2026-11-25): the first version's scope** is the Mac app's state, CUDA
   later (see Objective). This replaces "so wie Release 8 beim Mac" and the catching up after
   it: playback, backup and uninstall come in release 11.
6. **Decided (owner, 2026-11-25): release 11** is the Windows app and the Mac playback
   together, once both apps are at the same state. A fix that has to go out earlier would
   take the number 11 by ADR 0006; that is asked of the owner then, not decided here.
7. **Decided (owner, 2026-11-25): Claude on the owner's PC.** Claude may build, test and start
   the app and run the models on the company laptop itself, and it stays the checkpoint PC
   (see "Testing on Windows"). Signing stays as decided on 2026-11-24 (owner, 2026-11-25:
   "erstmal unsigniert").

Sources (read 2026-11-24): Microsoft Learn, Windows App SDK release channels and
self-contained deployment; Windows 10 extended security updates; .NET release support;
WebView2 distribution and local content; Windows app testing; MRT Core string localization;
SmartScreen reputation and Smart App Control; GitHub `actions/runner-images` (Windows 2025,
image 20261116); jrsoftware.org (Inno Setup 7.1.1); signpath.org and its terms; uv storage
docs and PRs 16894 and 17241; gyan.dev and BtbN/FFmpeg-Builds; StatCounter (October 2026).

### Module `win-design`

> Status: **done** 2026-11-24: every screen approved by the owner on the private design canvas
> "Stickler Windows screens" (a canvas of its own, as for the Mac), as draft 2; sources in
> [docs/design/win/](docs/design/win/README.md). Draft 1 was checked against Windows' standards
> at the owner's request; the check changed four points (below). The playback screens (W10, for a
> later release) approved on 2026-11-24.

**Objective.** Mockups of every screen of the Windows app's first version, made with the owner
on the design canvas, following Microsoft's design guidance for Windows 11 (WinUI 3). No code.
`win-shell` and `win-sheet` build what is drawn here, as the Mac modules built the `mac-design`
screens.

**Screens** (the minimum of release 11, and W10 for the playback of a later release; corrections
come later):

| # | Screen | Module |
|---|---|---|
| W1 | First start: consent (what is downloaded, sizes, ADTOF's non-commercial licence) | `win-shell` |
| W2 | First start: download with the setup steps | `win-shell` |
| W3 | First start: a server is not answering (names it, keeps what is done, retry) | `win-shell` |
| W4 | Empty window: drop area, "Open a Song…", recent songs | `win-shell` |
| W5 | Analysis: the steps, cancel | `win-shell` |
| W6 | Sheet music: title, artist, tempo and time signature in the window; zoom | `win-sheet` |
| W7 | Export: the button's menu, the "saved" note | `win-shell` |
| W8 | The menu bar: File, View, Help; "About Stickler" | `win-shell` |
| W9 | Light and dark: W4 and W6 in both | all |
| W10 | Playback (a later release): the playback bar, the volume flyout, the Playback menu; light and dark | the Windows playback module |

**Carried over from `design` and `mac-design` (same app, same words):** one step list for setup
and analysis (done, running, waiting, a short line each; model names only in setup); the copy
written for drummers, every language through `po/`; the sheet music inverted in dark mode; tempo
and time signature in the window, not on the page; the cost of the drum track export announced
before it starts; no Settings window (appearance follows the system, zoom is in View).

**Decisions from the mockups (owner, 2026-11-24):**
- **Window:** the standard 32 px title bar (the app's icon at 16 px, "Stickler", the system's
  caption buttons) on Mica; under it a menu bar with File, View and Help, also on Mica. The
  content lies on a layer above. Window, dialog and flyout corners 8 px, controls 4 px, the type
  ramp's Caption, Body and Subtitle; the accent colour and light or dark come from the system
  (the mockups show the default blue; the app uses the theme's brushes, no fixed colours).
- **Open and Export beside the song's title:** once a song is open, a header shows its title,
  and under it artist, tempo and time signature; at its right "Open" and "Export" (a button
  with a menu). The empty window has no header: "Open a Song…" in the drop area and File › Open…
  are enough, and there is nothing to export. The sheet music sits on a grey desk, the page as
  in the other apps.
- **First start as dialogs** (ContentDialog) in the middle of the window over the dimmed empty
  window, with the other apps' texts and step list. Windows' order of buttons: the main one on
  the left in the accent colour, the one that closes on the right, each as wide as the other
  ("Download 2.2 GB" · "Not Now"; "Try Again" · "Later"); a single button ("Cancel") on the
  right. The download shows a determinate progress bar, a running step a progress ring.
- **Export menu** with one line per entry: Sheet Music (PDF)…, MusicXML…, Drum Track…, then Open
  With…. Windows' menu entries have a text, an icon and a key, no second line; the Mac's
  second lines ("To print or to read on a tablet" and the others) are the entries' tooltips
  (owner, 2026-11-24; not drawn on the canvas).
- **After saving:** a flyout under the Export button, "Saved “<file>”" with "Show in Folder"
  (owner, 2026-11-24: this wording, not Explorer's "Open file location");
  it closes on the next click. Not an InfoBar: Microsoft's guidance keeps that for lasting,
  app-wide status, not for confirming what the user just did, and it may not float over the
  content (draft 1 had one at the window's bottom).
- **Menu bar:** File (Open… Ctrl+O, Open Recent, Export, Remove Downloaded Models…, Exit), View
  (Zoom In Ctrl+Plus, Zoom Out Ctrl+Minus, Actual Size Ctrl+0), Help (Stickler Help, Licences,
  About Stickler). No Full Screen (draft 1 had it with F11; the window can be maximised, and the
  Mac's entry is the system's). "Exit" has no key shown (Alt+F4 is the system's).
- **About Stickler** as a dialog: icon, name, release, the GTK app's sentence ("Writes the drums
  of a song as sheet music, so you can play along."), the licence and the website, "Close".
  Microsoft recommends an About section on a Settings page; Stickler has no Settings page, and
  Microsoft's own menu bar example has Help › About.
- **App icon:** the free-standing GNOME icon (`packaging/icons/ng.tshia.Stickler.svg`), not the
  Mac's orange square: Windows icons have no fixed shape and look best on a transparent
  background. The `.ico` holds 16, 24, 32, 48 and 256 px (`win-package` builds it). The mockups
  show a simplified stand-in.

**Checked against Microsoft's guidance (2026-11-24, a research sub-agent, its findings read):**
confirmed: Mica as the base layer with the title bar on it; the 32 px title bar with a 16 px
icon and Caption text; 8 px and 4 px corners; the type ramp's sizes; a menu bar at the window's
top; ContentDialog's smoke layer, its buttons' order and equal widths, the default button in the
accent colour and a footer of its own; one-line menu entries; Ctrl+Plus, Ctrl+Minus and Ctrl+0
for zoom; a determinate ProgressBar for a download; following the system's theme and accent.
Changed after the check: the "saved" note (InfoBar → flyout), Full Screen and the Alt+F4 label
removed, the Help menu and the About text taken from the Mac and GTK apps. Not in Microsoft's
pages, so Stickler's own choice: the wording "Show in Folder" (Explorer says "Open file
location", browsers "Show in folder"), the name "Exit" (Microsoft's writing guide avoids the
word, its menu bar example and Notepad use it), Ctrl+O, and the caption buttons' and buttons'
exact sizes (the system's and the controls' own; the mockups' 46 px and 32 px are drawn by eye).

**Success criteria.**
1. Every screen W1–W9 is on the canvas, in light and dark where W9 says so, and approved by the
   owner.
2. The canvas sources are copied to `docs/design/win/` with a README (the live canvas stays
   private, as for the other mockups), and the decisions are written here.
3. Every text on the screens exists in `po/` or is listed here for `win-shell` to add.

**New texts for `po/`** (added by `win-shell` in `win_texts.py`): "Show in Folder", "Exit".
Already there and reused: "Open Recent", "Clear Menu", "Stickler Help", "Licences", "Takes about
15 seconds", "Running", "Actual Size", "About Stickler", "Close", the About sentence.

**Out of scope.** Corrections screens (playback: W10, added on 2026-11-24, below); the question before "Remove Downloaded
Models…" and the drum track's cost (the other apps' texts in a ContentDialog, `win-shell`, as
the Mac mockups left them to `mac-shell`); the page when the core has stopped ("Stickler
Stopped Unexpectedly", `win-shell`, as on the Mac); narrow windows (a minimum size, decided in
`win-shell`); dark variants of the dialogs and menus (the controls' own); the install guide's
SmartScreen pictures (`win-package`); high contrast (the controls follow it; checked by the
owner in `win-shell`).

**Playback screens W10 (owner, 2026-11-24).** The GTK app's behaviour (module `playback`), drawn
the Windows way, for the Windows playback module of a later release:
- **The playback bar** at the window's bottom, on the same layer as the song's header, in one
  row as in the GTK app: Previous Bar, Play/Pause, Next Bar (the step buttons at the owner's
  wish, as in Windows' Media Player; the GTK app has only the keys), the time, a position slider,
  the length, "Bar 2 of 110", Volume, Song · Hits · Both.
- **Play/Pause** is a round button in the accent colour, as in Media Player; the sliders are
  WinUI's (accent track, a thumb with an accent dot).
- **Song · Hits · Both** as three joined toggle buttons, the chosen one in the accent colour.
  WinUI has no segmented control of its own; the Community Toolkit's `Segmented` is a NuGet
  package, to be asked for before it is used.
- **Volume:** a flyout above the button with two sliders, Song and Detected hits (70 % and
  100 % at first, remembered per song, as in the GTK app).
- **A Playback menu** between View and Help: Play or Pause (Space; the entry says what Space
  does now), Previous Bar (Left), Next Bar (Right), Go to the Start (Home), then Song, Hits and
  Both as radio items. Windows shows keys in menus, and the app has no Keyboard Shortcuts window.
- **The bar marker** in the accent colour; a click on a bar jumps there.
- **New text for `po/`:** "Playback". Previous Bar, Next Bar, Go to the Start, Song, Hits, Both,
  Volume and Detected hits exist.

Sources (read 2026-11-24): Microsoft Learn, Windows apps: title bar design and customization,
Mica, geometry, typography, menus and menu flyouts, command bar, dialogs, buttons, InfoBar,
progress controls, keyboard accelerators, theming and colour, app icon construction, guidelines
for app settings; Microsoft Writing Style Guide ("exit"); `microsoft-ui-xaml` on GitHub
(ContentDialog, Button, MenuFlyout and common theme resources).

### Module `win-core`

> Status: **built** (2026-11-24, tasks 168–175 done; Checkpoint AD is the owner's). Approved by
> the owner on 2026-11-24 (three folders, `taskkill` first, the branch `claude/win-core`
> pushed). Plan: `tasks/plan.md` ("`win-core`"), tasks 168–175.

**Objective.** The Python core and the first version's models (ADTOF, Beat This!, Demucs) run on
Windows 11 x64 (CPU), checked on every push by a Windows runner, before any C# exists. Linux
and macOS behave exactly as before.

**Assumptions** (from the code, read 2026-11-24; the Windows behaviour itself is only seen on
the runner):
1. The first version's models are ADTOF and Beat This! (Fast, what the setup assistant
   downloads) and Demucs (the drum track's export). MuScriptor medium (Quality) is not in the
   first version; its platforms are kept in step, as MuScriptor large's were for the Mac.
2. ADTOF's and Beat This!'s locks already hold `win_amd64` wheels (torch 2.15.0+cpu,
   torchaudio 2.11.1+cpu); Demucs', MuScriptor medium's and large's `environments` name Linux
   and macOS arm64 only, and their locks hold no Windows wheel.
3. `adapters/_common` imports `resource` at the top, which Windows does not have: today no
   adapter starts there. Peak RAM is a benchmark number only; no app reads it.
4. Cancel and the time limit kill the adapter's process group with `os.killpg` and `SIGKILL`
   after `start_new_session=True`; Windows has neither, and `uv run` starts the model as a
   grandchild there too.
5. `stickler_app.paths` knows `STICKLER_PACKAGED` as `macos` and `system`; on Windows every
   folder would fall to the Linux defaults under the user's profile.
6. Output of other programs is decoded with the system's encoding in about 19 places
   (`text=True` without `encoding`), which is UTF-8 on Linux and macOS and the ANSI code page
   (cp1252) on Windows; ffprobe's tags (artist, title) are UTF-8. The bridge's protocol stream
   is opened without `newline`, so Windows would write `\r\n`.
7. The test suite has no platform skips today. It assumes POSIX in the tests' process helper
   (`/proc`, `ps`), one fake `uv` written as a shell script, seven tests around process groups
   and signals, and 158 file reads and writes without `encoding`.
8. No Windows computer is available to Claude (the owner's PC refuses to start the
   `python.exe` of an environment uv made, found 2026-11-24; `tasks/todo.md`, task 174):
   everything Windows-specific is seen only in the workflow's runs. What can be tested on Linux with a stand-in (as `_peak_rss_mb(platform)`
   is) is tested there first.

**Scope.**
1. **Encodings spelled out:** every reading of another program's output and every text file
   in `src/` names UTF-8 (output of other programs with `errors="replace"`, so a stray byte in
   a model's log cannot crash the harness); the tests' file reads and writes name it too.
   Found on Linux with Python's own `EncodingWarning` (`PYTHONWARNDEFAULTENCODING=1`). On
   Windows the adapters' processes get `PYTHONUTF8=1`, so their tracebacks arrive as UTF-8;
   their environment on Linux and macOS is unchanged. No adapter file is edited for this.
2. **Peak RAM without `resource`:** on Windows `_peak_rss_mb` reads the process's
   `PeakWorkingSetSize` (`GetProcessMemoryInfo` through `ctypes`; the package stays free of
   dependencies); `resource` is imported only where it exists. Linux and macOS give the same
   number as before, so each of the ten adapters gets a `digests.yaml` pair.
3. **Wider platforms:** Demucs, MuScriptor medium and large add `sys_platform == 'win32' and
   platform_machine == 'AMD64'` to `environments` and are relocked.
   `scripts/lock_platforms.py` must show the Linux packages, versions and hashes identical
   before and after (and the macOS ones: the script is widened to compare them too, or the
   check is done by hand and written into the commit); only then a `digests.yaml` pair each.
   If anything for Linux or macOS moves: stop and ask the owner.
4. **Cancel and the time limit on Windows:** the adapter's whole process tree ends within a
   second, as on Linux. Proposed: `taskkill /T /F /PID` on the `uv` process (it stays the
   model's parent on Windows); a Job Object through `ctypes` only if the runner shows
   processes left over. POSIX code path unchanged.
5. **Folders:** `paths.packaged` knows `STICKLER_PACKAGED=windows`. Then data, cache and
   settings are `%LOCALAPPDATA%\Stickler\data`, `\cache` and `\config` (three folders next to
   each other, so "Remove Downloaded Models…" and a later uninstall remove one without the
   others), and `packaged_env` gives uv its cache and Python there, as for the Mac app.
   Without the variable (a checkout on Windows, the runner's tests) nothing changes.
6. **The bridge's lines:** the protocol stream writes `\n` on every system.
7. **Windows in CI:** a job on `windows-2025` with Python 3.14 and ffmpeg runs
   `scripts/check.sh task` (in the runner's bash), on pushes to `main`, pull requests and
   `claude/win-*` branches. The tests' process helper learns Windows. A test that cannot hold
   on Windows is fixed, or marked `skipif(sys.platform == "win32", reason=...)` with its
   reason and named in the commit message (CONSTRAINTS.md); tests of Linux' and the Mac's
   packaging that only read files stay on.
8. **The models on the runner's CPU:** `models-windows.yml`, as `models-macos.yml`: `stickler
   setup` for ADTOF, Beat This! and Demucs, their smoke tests, MuScriptor medium's and large's
   locks checked with `uv sync --locked`, seconds and peak RAM in the job summary; on pushes to
   `main` touching `adapters/` or `src/stickler/`, on `claude/win-*`, weekly and by hand.

**Success criteria.**
1. The Windows job is green: lint, floor guard, all tests with ≥ 95 % coverage.
2. ADTOF, Beat This! and Demucs pass their smoke tests on the runner's CPU with a plausible
   peak RAM; the cancel and time-limit tests pass there with real processes.
3. On Linux and macOS: every adapter's packages identical before and after (the comparison's
   output in the commit), every cached result found under the new digests (`stickler eval` for
   `config/benchmark.yaml` and `config/own.yaml` reads every result, nothing recomputed), CI
   green on 3.12, 3.15 and the macOS job.
4. No test skipped without a stated reason; the skips on Windows are listed at the checkpoint.

**Out of scope.** CUDA and ROCm on Windows (the GPU environments' `bin/python` stays);
MuseScore's place on Windows (the app's PDF comes from WebView2, `win-sheet`); the app's
language from Windows' settings (`win-shell` hands it to the core, as the Mac app does); how
the installer ships `uv`, Python and ffmpeg, long paths and SmartScreen (`win-spike`,
`win-package`); `stickler fetch`, `remote` and the GTK app on Windows (a test of theirs that
cannot hold there is skipped with that reason); ARM64.

**Decided (owner, 2026-11-24), as proposed:**
1. The three folders under `%LOCALAPPDATA%\Stickler` (scope 5), instead of one folder holding
   everything.
2. `taskkill` first, a Job Object only if needed (scope 4).
3. The work happens on a branch `claude/win-core`, pushed to GitHub so the Windows runner sees
   it (the only Windows there is); `main` gets it at the checkpoint.

### Module `win-spike`

> Status: **approved** by the owner on 2026-11-24 (the company laptop is the only Windows PC
> and counts: "wenn er hier läuft, passt das so"; decisions 2 and 3 as proposed). Plan:
> `tasks/plan.md` ("`win-spike`"), tasks 176–180. Nothing of the spike's code is merged: its workflow, installer script and launcher live on a throwaway branch
> (`claude/win-spike`); what stays are its findings, written into this spec and `tasks/todo.md`.

**Objective.** Before any C#: find out whether the way the Windows app is meant to bring its
core along works on a real Windows 11 PC. An installer built on the runner puts `uv`, a Python
with the core, ffmpeg and the adapters' sources on the owner's PC without administrator rights;
from there the Fast models are set up and a song becomes MusicXML, driven through
`stickler-bridge` exactly as the app will drive it. A failure changes `win-shell`'s setup and
`win-package` before either is planned.

**Assumptions** (from `win-core`, the code and the owner's PC, read 2026-11-24):
1. The core runs on Windows x64 (module `win-core`, built): the suite and the three models'
   smoke tests are green on `windows-2025`, from a checkout. Not yet seen: the core started
   from an installed folder, with `STICKLER_PACKAGED=windows` and its folders under
   `%LOCALAPPDATA%\Stickler`.
2. **The owner's PC is a company laptop** (Windows 11 23H2, build 22631, in a domain) with
   Panda Adaptive Defense 360 as its antivirus; Windows Defender is not running and Smart App
   Control is off there. On 2026-11-24 it refused to start the `python.exe` of an environment
   `uv` had just made ("Zugriff verweigert", in `%TEMP%` and under `Documents`), while the
   Python `uv` itself had downloaded started. The owner: the antivirus blocked it, and it may
   let the file run after some time. So on this PC the question is not SmartScreen alone but
   which of Stickler's programs the antivirus holds back, and for how long. A drummer's own PC
   more likely has Windows Defender with SmartScreen; that case is not covered by this PC.
3. The programs in play, none of which Stickler can sign yet: the installer itself, `uv.exe`,
   the shipped `python.exe`, ffmpeg and ffprobe, the Python `uv` downloads for the models
   (3.14 for ADTOF, Beat This! and Demucs), and each environment's `Scripts\python.exe`,
   which is a small launcher. Unconfirmed: which of them carry a signature of their makers,
   and whether an environment's launcher is the same file for every user (the same hash, so
   its reputation could grow) or differs per environment. The spike prints both on the runner.
4. `stickler_app.prefix()` knows only `<prefix>/lib/pythonX.Y/site-packages`; on Windows it
   falls back to `sys.prefix`. The shipped Python's own folder is `sys.prefix` there, so
   `share\stickler\adapters` below it is found, or the launcher sets
   `STICKLER_ADAPTER_SOURCES` (the spike shows which is needed).
5. The longest path below the models' folders is 180 characters (measured on the runner,
   MuScriptor; the Fast models' and Demucs' own longest paths are not yet measured). With
   `C:\Users\<name>\AppData\Local\Stickler\data\adapters\` in front that is close to Windows'
   260. GitHub's runners may have long paths switched on (unconfirmed; the spike reads
   `LongPathsEnabled` and switches it off for its run, which a runner's administrator may).
6. The runner has Inno Setup 6.7.1 (`iscc`); a per-user installer needs
   `PrivilegesRequired=lowest` and installs under `%LOCALAPPDATA%\Programs\Stickler`.

**Scope.**
1. **The installed layout,** built by a throwaway workflow on `windows-2025`:
   `bin\uv.exe`, `bin\ffmpeg.exe`, `bin\ffprobe.exe` (pinned by version and SHA-256; for the
   spike gyan.dev's essentials build, the final choice stays `win-package`'s),
   `python\` (a relocatable Python 3.14 with the core and its locked dependencies installed
   into it, no environment and no launcher of its own), `python\share\stickler\adapters\`
   (the sources of ADTOF, Beat This!, Demucs and `_common`, with their locks), and a
   launcher script. The licences of what is shipped go along, as in the Mac app.
2. **The launcher without an interface:** `Stickler-Spike.cmd` (a Start menu entry, and a
   song can be dropped on it). It sets `STICKLER_PACKAGED=windows` and a `PATH` of the
   installed `bin`, and runs a small driver of the spike's own with the shipped Python on the
   song (made from `scripts/bridge_demo.py`: it first agrees to the download and sets the Fast
   models up through the bridge's own commands, as the app's setup assistant will, then opens
   the song and saves its MusicXML), and writes everything to
   `%LOCALAPPDATA%\Stickler\spike-log.txt`: each step, each program started with its exit
   code, the seconds, and at the end "MusicXML written" or the first error in words. The owner
   sends that file back; nothing is uploaded by the script.
3. **On the runner, before the owner sees anything:** the installer is built, installed
   silently for the runner's user, the launcher run on a synthetic clip, the program removed
   through its uninstaller. Twice: once as it is, once with `LongPathsEnabled=0` and
   `LOCALAPPDATA` pointed at a folder whose path is as long as a long user name's (a profile
   name of 20 characters). The job summary lists: the installer's size; for every `.exe`
   shipped or created (the environments' launchers included) its SHA-256, its signer or
   "not signed", and whether two environments' launchers are the same file; the longest path
   per model; the seconds of setup and analysis; whether the uninstaller left Stickler's data
   folders alone; whether a screenshot of the runner's desktop can be taken (for `win-shell`'s
   tests).
4. **On the owner's PC** (the installer downloaded with a browser from the run's artifacts,
   so that it carries the mark of a download): what the browser, SmartScreen and the antivirus
   say at the download and at the start; install without administrator rights; the launcher
   with a song of the owner's. If a program is held back: which one (the log names the last
   step), what the antivirus's own message or log says, and the same try again after an hour
   and the next day (the owner's observation that it may be let through later). Then
   uninstall through Settings › Apps and look at what is left.
5. **The findings written down:** this section gets an "Answered" paragraph per question
   below; open questions 3 and 4 of "Release 11" are closed or restated with what was seen;
   `win-shell`'s and `win-package`'s specs start from them. The branch is deleted afterwards.

**Questions the spike answers.**
1. Does the core start from the installed folder and find its adapters' sources
   (assumption 4), and do setup and analysis of the Fast models work there, offline after the
   setup?
2. Which programs does the owner's PC hold back, at which step, and does that pass with time
   (assumption 2)? Does the installer itself run there, and what does the browser show?
3. Are the programs signed by their makers, and is an environment's launcher one file for
   everybody (assumption 3)? If the launcher is what gets held back: does starting the models
   with the downloaded Python directly (no environment's launcher) avoid it? Tried on the
   runner first; a change to how adapters are started is its own decision afterwards, not
   part of the spike.
4. Do the models install and run under a long user name without `LongPathsEnabled`
   (assumption 5)? If not: how short must Stickler's folder be.
5. Does the uninstaller remove the program and leave the data, and is there an entry in
   Settings › Apps?

**Success criteria.**
1. The runner's job is green in both runs (plain, and long path without `LongPathsEnabled`),
   or the failing step is understood and written down with what it means for the app.
2. On the owner's PC the outcome is known for each program of assumption 3: runs, held back
   and released after a known time, or held back for good. "Held back for good" is a valid
   result of the spike, not a failure of it.
3. Each of the five questions has its "Answered" paragraph with the evidence (the run's
   number, the log's lines, the date).
4. `main` and `claude/win-core` hold no file of the spike; Linux, macOS and Windows CI stay
   green.

**Boundaries.**
- **Always:** only this PC's own messages and logs are read; nothing in its security software
  is switched off, excluded or worked around (found 2026-11-24 and left alone). If the
  antivirus blocks, the spike reports it and waits.
- **Ask first:** asking the company's IT to allow Stickler's programs; installing anything
  on the PC besides the spike's installer; publishing the installer anywhere but as a
  workflow artifact.
- **Never:** a release, a tag or a download link on the website from the spike; model weights
  or a song of the owner's in the artifact or the repository.

**Out of scope.** Any interface (`win-shell`); the final installer, its texts, icons and the
release job (`win-package`); SignPath (applied for in `win-package`; the spike shows how much
depends on it); Demucs and the drum track's export on the owner's PC (its setup is measured
on the runner only; it is the largest download of the three); CUDA; a Windows PC with Defender and SmartScreen
(the owner has none, decision 1).

**Decided (owner, 2026-11-24):**
1. **Which PC counts:** the company laptop. The owner has no private Windows PC; if Stickler
   runs on this one, that is enough ("wenn er hier läuft, passt das so"). Its result is
   written down as that of a managed company PC with Panda Adaptive Defense 360. How Windows
   Defender and SmartScreen treat the installer on a PC without such software stays
   unconfirmed until someone has one (noted for `win-package` and the website's guide).
2. **If the antivirus holds the programs back for good** (as proposed): the Windows app is
   still built and checked on the runner; the owner's checks on the laptop wait for the signed
   release or for the company's IT, who are asked only after the spike shows what is blocked.
3. **Demucs on the owner's PC** is left out of the spike (as proposed); its setup is measured
   on the runner.

**Findings on the runner** (2026-11-24, `windows-2025`, workflow `win-spike` on the branch
`claude/win-spike`, run 45389618481, read from its log by the main session; the owner's PC,
question 2, is still open, task 179). The runner has no SmartScreen prompt, no Smart App
Control and no third-party antivirus, so nothing below says what a user's PC does.

1. **Question 1, answered for the runner: yes.** Installed under
   `%LOCALAPPDATA%\Programs\Stickler`, the shipped Python reports `packaged = 'windows'`,
   `prefix()` equal to `sys.prefix` (`...\Programs\Stickler\python`) and its folders under
   `%LOCALAPPDATA%\Stickler\{data,cache,config}`. `STICKLER_ADAPTER_SOURCES` is **not**
   needed: the launcher leaves it unset and `packaged_env()` finds
   `python\share\stickler\adapters`. The folder also works after being moved to a path with
   spaces. Through the bridge: Fast setup 62.5 s, analysis of a ten-second clip 11.1 s,
   MusicXML written. A second song with the network refused (`UV_OFFLINE=1`,
   `HF_HUB_OFFLINE=1`, the proxies at `127.0.0.1:9`) is analysed in 5.0 s. Demucs' setup
   took 32.4 s, 158.4 s and 27.1 s in the job's three installs (it is mostly a download). The data after all three models: 4.2 GB, of which `data\adapters` 3.2 GB,
   `cache\uv` 0.9 GB and `data\python` 0.13 GB. The installer is 98 MB.
2. **Question 3, the signatures: only `uv.exe` is signed** (valid, signer "OpenAI OpCo, LLC",
   uv 0.13.9). Not signed: `ffmpeg.exe` and `ffprobe.exe` (gyan.dev essentials 9.1),
   `python.exe` and `pythonw.exe` (python-build-standalone 3.14.10, the shipped one and the
   one `uv` downloads are the same file), every environment's `Scripts\python.exe`, the
   other `.exe` files inside the environments (setuptools, pip, torch's `protoc.exe`), the
   installer and its uninstaller. **The environments' launchers are one file:** the three
   `Scripts\python.exe` are byte-identical (46,592 bytes, SHA-256 `f50e21b4…415b9`), and
   differ from the base `python.exe` (`df5ddcdd…d6a6`). The entry-point `.exe` files in
   `Scripts` differ per environment (they hold paths); the models do not start through them.
   **Without the launcher:** the downloaded base `python.exe` ran ADTOF's `run.py` with
   `PYTHONPATH` set to the environment's `site-packages` and `_common\src`, exit code 0,
   `drums.mid` and `meta.json` written. `_common\src` had to be named by hand, because a
   `.pth` file is not read from `PYTHONPATH`. So that way of starting a model exists if the
   owner's PC holds back the launcher only; whether it does is task 179's.
3. **Question 4, answered for the runner: yes, it works without `LongPathsEnabled`.** The
   runner has `LongPathsEnabled=1` as found; the job set it to 0. With a profile name of 20
   characters (the longest full path 240) and of 50 characters (the longest 270, so beyond
   260) setup, analysis and Demucs' setup all worked. A control in the same job shows the
   setting took effect: `cmd.exe` and both Pythons failed to make a 326-character folder
   (`WinError 206`). What this does and does not show: the longest paths in every environment
   are licence files inside torch's `dist-info` (173 characters below `adapters\`), which
   `uv` writes and no model opens; `uv` evidently writes beyond 260 on its own. The longest
   path a model **opens** at run time was not measured, and neither was a profile name longer
   than 50. Inno's `{localappdata}` does not follow the `LOCALAPPDATA` variable, so the
   installer got `/DIR=` in these runs; only the data folder was moved.
4. **Question 5, answered for the runner: yes.** After the silent uninstall the program
   folder is gone with nothing left, `%LOCALAPPDATA%\Stickler` is untouched, and the key
   `HKCU\...\Uninstall\{...}_is1` (what Settings › Apps lists) existed after the install and
   is gone afterwards. The script has `[UninstallDelete]` for the program folder, because
   Python writes `__pycache__` there; without it was not tried. Settings › Apps itself is
   looked at on the owner's PC.
5. **A screenshot of the runner's desktop can be taken** (1024 × 768, `CopyFromScreen`).

**Notes for `win-shell` and `win-package`** (from the spike, not decided):
- The bridge has no event for "the models are set up, nothing to ask": the driver waits 20 s
  for a `consent` and takes silence as ready. `win-shell`'s setup assistant should not need
  such a wait; if it does, that is a change to the bridge with its own task.
- `stickler.doctor` calls `Path.home()` at import, so the core needs `USERPROFILE` or `HOME`.
  Every Windows session has one; a service or a stripped environment would not.
- The spike ships the whole Python (headers, test modules, pip, entry-point `.exe` files that
  hold the build's paths). `win-package` prunes it as `scripts/mac_bundle_tools.py prune`
  does for the Mac, adds the translations, and pins Python by SHA-256 (the spike lets `uv`
  download 3.14 and check it itself).
- `cache\uv` holds 0.9 GB of wheels next to 3.2 GB of environments after setup. Whether it
  can go after setup without a second download later: untried.
- ffmpeg's SHA-256 in the spike is the digest GitHub shows for the release asset of
  `GyanD/codexffmpeg` 9.1, not a checksum published by gyan.dev. The final source of ffmpeg
  is `win-package`'s decision.

### Module `win-shell`

> Status: **being built** from 2026-11-25 on the owner's word "Bitte mach so weit du kommst,
> den Spike-Lauf verschieben wir lieber darauf, bis du fertig bist": Claude's proposals for
> open questions 2–4 are taken (Claude's reading; to be confirmed at the checkpoint), open
> question 1 waits for the spike's retry, which comes after this module. Plan:
> `tasks/plan.md` ("`win-shell`"), tasks 181–188, on the branch `claude/win-shell`. Modelled
> on `mac-shell`, with the Windows screens of `win-design`.

**Objective.** The first Stickler that runs as a Windows app: the WinUI 3 window of
`win-design` (W1–W5, W7, W8, light and dark) over the core that `core-bridge` made and
`win-core` made portable. A drummer opens or drops a song, agrees to the download on the first
start, watches the steps, cancels, sees errors, saves MusicXML and the drum track, and backs up
or restores Stickler's data (release 10). The sheet music and the PDF come with `win-sheet`,
playback with `win-playback`, the installer and "Uninstall Stickler…" with `win-package`.

**Assumptions** (from the code, this PC and the web on 2026-11-25):
1. The bridge (`docs/bridge.md`) carries every state, command and text this module needs,
   translated, including release 10's `back_up`, `backup_summary` and `restore`; the app
   enables buttons and menu items from the state's `can_*` fields alone, as the Mac app does.
2. The core runs on Windows x64 from a checkout (`win-core`: the suite on `windows-2025` and,
   since 2026-11-25, natively on the owner's PC) and from an installed folder with
   `STICKLER_PACKAGED=windows` (`win-spike`, 2026-11-25: the bridge answers, the folders are
   under `%LOCALAPPDATA%\Stickler`, the adapters' sources are found).
3. **The owner's PC** (task 179, 2026-11-25): the company network inspects TLS, so `uv`
   downloads only with the system's certificates (`UV_SYSTEM_CERTS=1`); Panda Adaptive
   Defense 360 refused uv 0.13.9's environment launcher (`.venv\Scripts\python.exe`) while
   uv's downloaded Python and an older launcher start; the retry after an hour is pending.
   Python's own downloads (Beat This!'s weights through `urllib`) use Windows' certificate
   store and should pass; not yet seen.
4. **This PC has no .NET SDK and no Visual Studio**, only the .NET 10.0.15 runtimes (checked
   2026-11-25). GitHub's `windows-2025` image has Visual Studio 2026 with the .NET 10 SDK
   since the June 2026 migration (the release's tech stack still names 2022 17.14; read
   from the runner's log in the first task).
5. The Windows App SDK's own pickers (`Microsoft.Windows.Storage.Pickers`, from 1.8) take the
   window's `AppWindow.Id`; Microsoft's pages do not say whether they work in an unpackaged
   app (read 2026-11-25). The older `Windows.Storage.Pickers` work there with
   `InitializeWithWindow`. The first task tries the new ones and falls back.
6. Whether `dotnet build` alone compiles a WinUI 3 app's XAML without Visual Studio is
   unconfirmed here; on the runner Visual Studio is there. The first task finds out on this PC
   (open question 2).

**Scope.**
1. **`SticklerCore`, a `net10.0` class library without Windows APIs** (`win/SticklerCore/`),
   the counterpart of `mac/SticklerCore`:
   - starts the core as a subprocess (from a checkout `uv run python -m
     stickler_app.bridge`: not the `stickler-bridge.exe` uv writes for the entry point, which
     has a hash of its own that Panda held back on 2026-11-25, while the environment's
     `python.exe` is one file for every environment of a uv release; from an installed app
     `win-package`'s command), writes commands as UTF-8 JSON lines ending in `\n`, reads its
     lines on a task of its own, decodes `hello`, `state`, `recent`, `notice` and replies
     into C# records that mirror `docs/bridge.md` (read with `JsonDocument` field by field, no
     reflection), matches each reply to its command by `id`, and notices
     when the process ends (exit code and stderr's last 40 lines kept for the error page);
   - **always passes `UV_SYSTEM_CERTS=1`** to the core (assumption 3; harmless where no proxy
     inspects TLS, since uv then reads the same roots from Windows' store) unless open
     question 3 moves it into the core;
   - an `AppModel` (plain `INotifyPropertyChanged`, no MVVM package) with the latest state,
     the recent songs and the notices; it never decides a flow, it only forwards commands;
   - the string lookup over `scripts/winstrings.py`'s JSON tables: the user's first
     preferred UI language that `po/` has, else English; named placeholders and the plural
     rule `n != 1`, as `scripts/xcstrings.py` maps them;
   - builds and tests on Linux (WSL here, `ubuntu` in CI) and on Windows.
2. **The app, `win/Stickler/`** (WinUI 3, C#, unpackaged and self-contained as the release
   decided, `WindowsPackageType=None`):
   - **Window** (W4, W5, W8): Mica, the standard title bar with the 16 px icon and
     "Stickler"; the menu bar File, View, Help; once a song is open, the header with its
     title, artist, tempo and time signature, and "Open" and "Export" at its right. The empty
     window: the drop area (files dropped from Explorer), "Open a Song…", the recent songs (a
     missing file dimmed with a remove button, as in GTK). The step list with Cancel for
     analysis and drum track (a progress ring for the running step). The error page with
     "Technical Details" (an expander), "Open Another Song…" and "Try Again" when
     `can_retry`. Minimum window size 640 × 480 effective pixels.
   - **Result placeholder** (until `win-sheet`): the grey desk with one centred line, as on
     the Mac. Never in a release: `win-package` requires `win-sheet`.
   - **Setup** (W1–W3) as ContentDialogs over the dimmed empty window: consent with the
     models, their licences and sizes, "Download 2.2 GB" · "Not Now"; the download's step list
     with a determinate progress bar and "Cancel"; a failed download naming the server,
     "Technical Details", "Try Again" · "Later". **How the models are started is open
     question 1** (the spike's outcome).
   - **File menu** (W8): Open… (Ctrl+O), Open Recent (the core's recent songs, Clear Menu),
     Export, Close Song (Ctrl+W, `close`, while `can_close`; open question 4), Back Up…,
     Restore Backup…, Remove Downloaded Models…, Exit. "Remove Downloaded
     Models…": a ContentDialog with the sizes from `removal_sizes`, the checkbox for settings,
     recent songs and corrections, a destructive button. Back Up and Restore: the GTK app's
     and the Mac app's flow and texts (`backup_summary` before restoring), with the save and
     open pickers.
   - **Exports** (W7): Export's menu with MusicXML…, Drum Track…, Open With… (one line each,
     the other apps' second lines as tooltips); the save picker with the core's file name;
     the drum track's cost in a ContentDialog first (`drum_track_cost`). Open With… opens the
     MusicXML with Windows' "Open with" chooser (`Launcher` with the application picker shown).
     "Sheet Music (PDF)…" comes with `win-sheet`. After saving: the flyout under Export,
     "Saved “<file>”" with "Show in Folder" (Explorer with the file selected); other notices
     in a flyout of the same kind.
   - **View and Help:** View's zoom entries come with `win-sheet` (until then View holds
     nothing and is hidden); Help: Stickler Help (the README on GitHub), Licences (the folder
     of shipped licences, from `win-package`; until then the repository's licence page),
     About Stickler (W8's dialog).
   - **The core stopped:** "Stickler Stopped Unexpectedly", the technical details (exit code,
     stderr's last lines) and "Start Again", as on the Mac.
   - **Where the core is** (until `win-package`): a development build takes the checkout from
     `STICKLER_CHECKOUT` or asks once with a folder picker, remembers it, and checks it holds
     `pyproject.toml` and `adapters/`. `uv` is looked for on `PATH` and in winget's and uv's
     own folders. Gone in `win-package`, whose installer brings the core along.
   - **Quitting** sends `quit` and waits at most 3 s, then ends the core's process tree
     (`taskkill /T`, as `win-core` ends a model).
   - **Texts:** every text from `po/` through `scripts/winstrings.py`; the new ones ("Show in
     Folder", "Exit", "Back Up…" where the Windows wording differs) go into
     `src/stickler_app/win_texts.py` with German and Spanish, as `mac_texts.py`.
3. **The solution** `win/Stickler.sln` with SDK-style projects, the Windows App SDK pinned
   (the newest 2.x when this module starts; 2.7 on 2026-11-17), MSTest with
   Microsoft.Testing.Platform and its coverage; `Directory.Build.props` with
   `TreatWarningsAsErrors`, `AnalysisLevel=latest-recommended`, `EnforceCodeStyleInBuild`,
   `Nullable=enable`.
4. **CI, `.github/workflows/win.yml`** on `windows-2025`: build, `dotnet format
   --verify-no-changes`, tests with coverage gated at 95 % for `SticklerCore` and the app's
   logic types (a script over the Cobertura file, as `scripts/xccov_gate.py`), screenshots of
   every screen in light and dark from fixed states (the app started with a recorded core,
   the window captured; the spike showed the runner's desktop can be captured), and the built
   app folder as a zip artifact for the owner. `SticklerCore`'s tests also on `ubuntu` in the
   same workflow, against the real bridge with stand-in models.
5. **CONSTRAINTS.md for C#** (the release's quality bar): no `#pragma warning disable`,
   `[SuppressMessage]`, `<NoWarn>` or `.editorconfig` severities lowered to `none`; no
   placeholder `throw new NotImplementedException()`; no `[Ignore]` without a reason in the
   commit; the build's analyzers and `dotnet format` clean; coverage as in scope 4.
   `scripts/floor_guard.py` learns the C# patterns.
6. **`docs/win-development.md`:** the owner's PC set up once (what open question 2 decides,
   `uv`, ffmpeg, the checkout), starting a development build or the CI's zip, what to check at
   the checkpoint, and what Panda may hold back.

**Testing.**
- `SticklerCore` on Linux and Windows: decoding of every example line in `docs/bridge.md`
  (the same lines the Python doc test checks), replies matched to commands, lines split
  across reads, `\r\n` never written, a core that exits (code and stderr kept), the string
  tables' lookup and plurals, and the real bridge as a subprocess with stand-in models:
  `hello`, `open` until `result`, `cancel`, `quit`.
- The app's logic types with a fake core (MSTest): each state to what the window offers, the
  setup dialogs, the export, backup and restore flows up to the picker's answer (pickers and
  the launcher behind a small interface with a fake), the core stopped and started again.
- Screenshots: W1–W5, W7, W8, the stopped core and the error page, light and dark; the owner
  compares them with the canvas.
- By hand on the owner's PC: a song from the drop to the saved MusicXML through a
  development build, keyboard only once (Tab order, Alt for the menu bar), high contrast once.

**Success criteria.**
1. On the owner's PC, a development build (built here or the CI's zip) finds the checkout,
   asks for consent, downloads the Fast models into `%LOCALAPPDATA%\Stickler`, and turns a
   dropped song into a result; Cancel works during the analysis and the download.
2. MusicXML and the drum track are saved; "Show in Folder" shows the file; a backup made here
   restores in the GTK app and the other way round.
3. Ending the core (Task Manager) shows the stopped page; "Start Again" works.
4. Every screen matches the canvas in light and dark (screenshots, the owner's check); English,
   German and Spanish follow Windows' display language.
5. `win.yml` is green on every push: build with warnings as errors, format, tests, coverage
   ≥ 95 % outside pure views; `SticklerCore`'s tests green on Linux too. The Linux and Mac
   apps and the core unchanged (`scripts/check.sh task` green, no adapter file touched).

**Out of scope.** The sheet music, zoom and the PDF (`win-sheet`); playback (`win-playback`);
the installer, the bundled core, "Uninstall Stickler…", the app icon's `.ico` and the install
guide (`win-package`); corrections, Quality, CUDA; ARM64.

**Risks.**
- Panda holds back the development build's own `Stickler.exe` (unsigned, a new hash on every
  build): the CI's zip and builds here are tried at the first checkpoint; if it is held back
  for good, the owner's checks wait for the signed release or the company's IT (as
  `win-spike` decided), and the runner's screenshots carry the module.
- The unpackaged app's pickers fail (assumption 5): the older pickers with
  `InitializeWithWindow`.
- Screenshots on the runner are blank or partial (no GPU, Mica falls back to a plain colour):
  accepted for the comparison; the owner's look on the PC counts.
- WinUI's drag and drop gives no file for a song dragged from a browser's download bar: only
  files from Explorer are promised.

**Open questions** (the owner's):
1. **How the setup starts the models**, after the spike's retry: if Panda releases uv
   0.13.9's launcher after a while, nothing changes; if it holds it back for good, either the
   core starts each model with uv's downloaded Python directly (no environment launcher; a
   change to `stickler.adapters` with its own task and `digests.yaml` pairs if
   behaviour-neutral), or the owner's checks wait for signing or IT. Claude's proposal: decide
   after the retry and the next day's, not now.
2. **The .NET 10 SDK on this PC:** install it for the user (Microsoft's `dotnet-install.ps1`,
   no administrator rights, under `%LOCALAPPDATA%\Microsoft\dotnet`), so Claude builds and
   tests here and not only on the runner? Visual Studio is not needed if `dotnet build`
   compiles the XAML (assumption 6). Claude's proposal: yes.
3. **System certificates for every packaged app:** `UV_SYSTEM_CERTS=1` set by
   `stickler_app.paths.packaged_env` for all three apps (a company network on Linux or a Mac
   has the same problem), instead of in the Windows app alone. Claude's proposal: in the core,
   as a task of this module.
4. **"Close Song" (Ctrl+W) on Windows:** the Mac and GTK apps have it (owner, 2026-11-18);
   `win-design`'s File menu does not. With "the same features everywhere", Claude's proposal:
   add it to File, between Export and Back Up….

Sources (read 2026-11-25): Microsoft Learn, "Save a file with Windows App SDK pickers" and
"Using file and folder pickers"; GitHub's changelog on the `windows-2025` image's move to
Visual Studio 2026 (2026-05-14).

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
