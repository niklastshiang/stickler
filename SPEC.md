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
| Transcription | `yourmt3` | mimbres/YourMT3 (YourMT3+ YPTF.MoE+Multi) | GPL-3.0 |
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

### Later: GTK interface (not part of v1)
- GTK 4 + libadwaita via PyGObject, separate package `stickler-gtk` that only uses `stickler.api`.
- For this to work, v1 needs: a public API in `stickler/api.py` (`run_benchmark`, `evaluate`, `transcribe_song`, `notate`) with progress callbacks and cancellation support, no `print`s in the logic (logging instead), and results as data objects, not only as files.
- **Design together first:** before any GTK code, the owner and Claude design the interface together, following current design principles, above all the GNOME Human Interface Guidelines (libadwaita patterns, adaptive layout, accessibility). Mockups first, then implementation.
- Features requested by the owner:
  - **Two modes instead of a model choice:** "Fast" and "Quality" (pipelines decided after the benchmark).
  - **Readable sheet music:** fold repeated bars and passages into repeat signs.
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
