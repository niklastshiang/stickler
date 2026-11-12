<h1 align="center">
  <code>STICKLER://DRUMS</code>
</h1>

<p align="center">
  <strong>Song in, sheet music out. Local, with open-source models.</strong><br/>
  <em>Stickler: a pedant. And someone who holds the sticks.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff8800?style=flat-square&labelColor=0d1117" /></a>
  <img src="https://img.shields.io/badge/python-3.12-ff8800?style=flat-square&logo=python&logoColor=ff8800&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/environments-uv-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/language-english-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/models-8%20adapters-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/tests-154%20%2B%208%20smoke-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/coverage-97%25-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/version-0-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/status-benchmark%20running-ff8800?style=flat-square&labelColor=0d1117" />
</p>

<br/>

<pre align="center">
<code>
  ╔═════════════════════════════════════════════════════════════════════════════╗
  ║                                                                             ║
  ║        ███████╗████████╗██╗ ██████╗██╗  ██╗██╗     ███████╗██████╗          ║
  ║        ██╔════╝╚══██╔══╝██║██╔════╝██║ ██╔╝██║     ██╔════╝██╔══██╗         ║
  ║        ███████╗   ██║   ██║██║     █████╔╝ ██║     █████╗  ██████╔╝         ║
  ║        ╚════██║   ██║   ██║██║     ██╔═██╗ ██║     ██╔══╝  ██╔══██╗         ║
  ║        ███████║   ██║   ██║╚██████╗██║  ██╗███████╗███████╗██║  ██║         ║
  ║        ╚══════╝   ╚═╝   ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝         ║
  ║                                                                             ║
  ║                       🥁 SONG IN  //  SHEET MUSIC OUT                       ║
  ║         DRUM SHEET MUSIC FROM ANY SONG  //  OPEN SOURCE  //  LOCAL          ║
  ║                                                                             ║
  ╚═════════════════════════════════════════════════════════════════════════════╝
</code>
</pre>

---

## `> WHAT IS THIS`

**Stickler** is becoming a desktop application that turns a song into drum sheet music: drag in
an MP3 or FLAC, get the notes as MusicXML or PDF, and only correct them in MuseScore. It has a
GTK 4 interface and ships as a Flatpak and an AppImage.

**Right now Stickler is a test bench.** Before the application can be built, one question must
be answered that reading papers cannot settle: **Which combination of drum separation and
transcription model produces the best notes?** Measurement uses benchmark data and, above all,
real music. Each model lives in its own adapter with its own Python environment and competes
against the same references: kick, snare, toms, hi-hat and cymbals, with every hit accurate to
±50 ms. The winning pipeline becomes the core of the application.

Only **open-source models from actively maintained projects** are allowed. No cloud service, no
black box; everything runs locally on your own machine.

---

## `> WHY`

I'm a beginner on the drums. Do you know how hard it is to find sheet music for even slightly
niche music?
I do, because I looked.

Then I found a few services that can transcribe songs into sheet music. But I'm not crazy
enough to spend €20 when I already have an active AI subscription.

And just like that, the thought was born: rebuilding this can't be rocket science. Even
better: locally, so it runs on my own PC.

A dream come true.

---

## `> WARNINGS`

> **⚠ FIGURES ARE PRELIMINARY.** The first complete run over MDB Drums is still in progress. The
> table below is a sample from a single song.

> **⚠ FOR PRIVATE USE ONLY.** Some weights are under non-commercial licenses (ADTOF, MuScriptor,
> presumably BS-RoFormer). For publication they would have to be replaced, see
> [ADR 0002](docs/adr/0002-nc-lizenzen.md).

> **⚠ TRAINED ON MDB?** Some models have seen MDB Drums during training or evaluation. The honest
> test is your own songs.

---

## `> SAMPLE`

Macro-F1 over 5 classes on MDB `MusicDelta_Punk` (29 s), CPU. **One song, no verdict.**

| Transcriber | Original mix | Demucs stem | Oracle stem¹ |
|---|---|---|---|
| **ADTOF** | 0.803 | **0.854** | 0.871 |
| **MuScriptor medium** | **0.825** | 0.813 | – |
| **MuScriptor small** | 0.793 | 0.726 | – |
| **ADT_STR** | –² | 0.790 | 0.811 |
| **YourMT3+** (PS) | 0.588 | – | 0.670 |

¹ The isolated drum stem from the dataset, i.e. perfect separation as an upper bound.<br/>
² ADT_STR only accepts separated drum tracks and takes forever on the mix.

On the Radeon 840M the GPU was slower than the CPU for **every** model. The benchmark runs
therefore compute on the CPU ([ADR 0003](docs/adr/0003-rocm-kanal.md)).

---

## `> HOW IT WORKS`

```
  Song ──┬──► Separation ─────► Drum stem ───► Transcription ────► drums.mid
         │    none · demucs     (or mix)       adtof · adt_str              │
         │    roformer · oracle                muscriptor · yourmt3         │
         │                                                                  ▼
         └──► Beat tracking ──► beats.json ──────────────────────► Scoring against
              beat_this                                            the reference
                                                                   ±50 ms · 5/3 classes
```

- **One adapter per model.** Each model gets a folder with its own `pyproject.toml` and its own
  `uv` environment. The harness calls it as a subprocess and never imports model code. A new
  candidate only needs a folder and a config entry.
- **Everything is cached.** The key made from input, adapter code and device determines whether a
  result is reused. An interrupted run resumes where it stopped.
- **Failures don't block anything.** An adapter that crashes or hits its time limit is logged. All
  others keep computing.

---

## `> CANDIDATES`

| Stage | Adapter | Project | License |
|---|---|---|---|
| Separation | `demucs` | [adefossez/demucs](https://github.com/adefossez/demucs) 4.1, `htdemucs_ft` (maintained fork) | MIT |
| Separation | `roformer` | [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator), BS-Roformer-SW | MIT / weights unclear |
| Transcription | `adtof` | [ADTOF-pytorch](https://github.com/xavriley/ADTOF-pytorch) (Zehren et al.) | CC BY-NC-SA |
| Transcription | `adt_str` | [ADT_STR](https://huggingface.co/Pierfrancesco/adt-str) (2026), τ = 0.8 | CC BY-SA |
| Transcription | `muscriptor_s`, `muscriptor_m` | [MuScriptor](https://github.com/muscriptor/muscriptor) (Kyutai/IRCAM, 2026) | MIT / weights CC BY-NC |
| Transcription | `yourmt3` | [YourMT3+](https://huggingface.co/spaces/mimbres/YourMT3) YPTF.MoE+Multi (PS) | Apache-2.0 / GPL-3.0 |
| Beats | `beat_this` | [Beat This!](https://github.com/CPJKU/beat_this) (CPJKU, 2024) | MIT |

Every model decision that was not obvious is recorded as an ADR in [`docs/adr/`](docs/adr/).
Source, version and own measurements are in the README of the respective adapter.

---

## `> OWN SONGS`

Benchmark data is clean, real music is not. That is why Stickler also compares against your own
songs: sheet music as MIDI from musescore.com, and a recording from your own collection.

The problem is that notes and recording don't line up. Intros are missing, tempos drift, and
transcribers leave passages out. `stickler align` therefore lays the notes onto the recording,
hit by hit. It is based on the beats from Beat This! and the rhythm patterns in the Demucs stem,
linked via DTW. Passages without a counterpart are excluded.

**Only good references make it into the scoring.** Checking is done without a transcription
model, so the models are not their own examiners. The thresholds are calibrated on MDB, whose
references are demonstrably correct:

| Criterion | Threshold |
|---|---|
| Paired note beats that sit cleanly on the recording (±70 ms) | ≥ 95% |
| Note hits with an audible attack in the drum stem (±50 ms) | ≥ 85% |
| Clear attacks in the stem that appear in the notes | ≥ 90% |
| Clear attacks in excluded passages | ≤ 20% |

Passages that only exist in the sheet music, such as extra repeats, are dropped from the
reference. They are reported, but they are no reason to reject a song.

To check by ear, `stickler align` writes a `click.wav` per song: the recording on the left, clicks
on the note hits on the right.

---

## `> KEY FIGURES`

```console
scripts/check.sh task
```

```json
{
  "adapter": { "separation": 2, "transcription": 5, "beats": 1 },
  "datasets": { "mdb_drums": 23, "own_songs": 10 },
  "tests": 154,
  "smoke_tests_with_models": 8,
  "coverage_percent": 97.5,
  "coverage_minimum": 95,
  "adrs": 6,
  "version": 0,
  "status": "benchmark running"
}
```

| Key | Meaning |
|---|---|
| `smoke_tests_with_models` | Runs real models, therefore not part of the default run: `uv run pytest -m adapters` |
| `coverage_minimum` | Below this, the pre-commit hook blocks. Limit and rules in [`CONSTRAINTS.md`](CONSTRAINTS.md) |
| `own_songs` | Described in `references/own/`. Only songs that pass the quality criteria enter the scoring |

---

## `> ROADMAP`

**Done**

- [x] Scoring by class, cache, time limits, error log
- [x] Separators Demucs and BS-RoFormer
- [x] Transcribers ADTOF, ADT_STR, MuScriptor small and medium, YourMT3+
- [x] GPU path via ROCm evaluated (slower than the CPU, stays optional)
- [x] Beat tracking with Beat This!
- [x] Alignment and quality criteria for own songs

**In progress**

- [ ] Full run over MDB Drums
- [ ] Align and check own songs
- [ ] Transcriber `drumsep_onset` (DrumSep plus onset detection per drum)

**Afterwards: from measurement to application**

- [ ] HTML report with ranking, classes, runtime and memory
- [ ] ENST-Drums as a third dataset
- [ ] Notes from the winning pipeline: quantization, MusicXML, `stickler notate`
- [ ] Design the interface together, following the GNOME Human Interface Guidelines
- [ ] Application with a GTK 4 and libadwaita interface, app icon in GNOME style, export of the separated drum track
- [ ] Ultrareview of the finished application
- [ ] Release pipeline: Flatpak and AppImage with every release
- [ ] Everything in English: code, output and documentation

---

## `> BUILD IT YOURSELF`

### Prerequisites

Stickler needs **`uv`** for the Python environments and **`ffmpeg`** to decode audio. Everything
else, including Python 3.12 and PyTorch, `uv` fetches for each adapter itself.

**Fedora, Bluefin and related**

```console
brew install uv          # or: curl -LsSf https://astral.sh/uv/install.sh | sh
sudo dnf install ffmpeg-free
```

**Debian, Ubuntu and related**

```console
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install ffmpeg
```

### Setup

```console
git clone https://github.com/niklastshiang/stickler.git
cd stickler/
uv sync
git config core.hooksPath .githooks    # checks before every commit
uv run stickler fetch mdb              # download MDB Drums (CC BY-NC-SA)
uv run stickler setup                  # all adapter environments and weights
uv run stickler doctor                 # what's still missing?
```

> MuScriptor weights are gated: accept the license on Hugging Face, then run `uvx hf auth login`.
> The GPU setup is optional: `stickler setup --device rocm`.

### Benchmark

```console
uv run stickler run      # computes the matrix from config/benchmark.yaml (overnight)
uv run stickler eval     # results/metrics.csv and results/summary.csv
uv run stickler align    # align own songs, check them and write click.wav
```

---

## `> ORIGIN`

<img src="https://img.shields.io/badge/code-Claude%20Code-ff8800?style=flat-square&labelColor=0d1117" />
<img src="https://img.shields.io/badge/decisions-human-ff8800?style=flat-square&labelColor=0d1117" />

**The code of this project comes from an AI.** It was programmed, tested and documented by Claude
(Anthropic) in Claude Code.

The project owner provides the goals, the selection of candidates and the songs. He makes the
decisions and checks the results by ear. To keep the code from quietly getting worse, firm
guardrails apply:

- **Specification first, then code.** What gets built is set out in [`SPEC.md`](SPEC.md), the plan
  in [`tasks/`](tasks/). Decisions made are recorded in [`docs/adr/`](docs/adr/).
- **Tests first** and a minimum coverage of 95%.
- **A floor guard checks every diff.** It triggers when checks are silenced, tests are skipped or
  limits are lowered. Such a commit is blocked, see [`CONSTRAINTS.md`](CONSTRAINTS.md).
- **Measure, don't assert.** Every model choice is justified by measurements, even when the
  result is inconvenient.

---

## `> REPOSITORY LAYOUT`

```
stickler/
├── src/stickler/        # Harness: api, cli, runner, align, onsets, evaluate, datasets/
├── adapters/            # one folder per model, each with its own uv environment
│   ├── _common/         # shared helpers: device selection, meta.json, drum MIDI
│   ├── separators/      # demucs, roformer
│   ├── transcribers/    # adtof, adt_str, muscriptor_s, muscriptor_m, yourmt3
│   └── beats/           # beat_this
├── config/              # benchmark.yaml (matrix), classes.yaml (GM pitch → class)
├── references/own/      # own songs: title, recording, manual exclusions
├── tests/               # pytest; smoke tests with real models under -m adapters
├── scripts/             # check.sh, floor_guard.py
├── docs/adr/            # Architecture Decision Records
├── tasks/               # plan and task list
└── data/ cache/ results/   # datasets, intermediate results, evaluation (not in the repo)
```

---

## `> LICENSE`

**The code of Stickler** is under [**MIT**](LICENSE). This covers the harness, adapters, scripts,
tests and documentation. Using, modifying, redistributing and selling it is permitted, as long as
the copyright notice stays intact.

**The models** are not affected by this. Stickler only downloads them on `stickler setup`; they
are not in the repository and come with their own licenses, see
[`> CANDIDATES`](#-candidates). Weights under non-commercial licenses are only permitted for
private use ([ADR 0002](docs/adr/0002-nc-lizenzen.md)). Anyone distributing Stickler must omit or
replace them.

**Data:** MDB Drums is under CC BY-NC-SA 4.0. Sheet music and recordings of your own songs belong
to their authors and are therefore not in the repository.

---

## `> SUPPORT MY WORK`

Nobody reads this anyway. But if you ever run into me in real life, feel free to buy me a
burger. 🍔

---

<p align="center">
  <strong><code>> COUNT ALONG. THE STICKLER DOES ANYWAY._</code></strong>
</p>
