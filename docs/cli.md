# Stickler command line guide

`stickler` turns songs into drum sheet music and benchmarks the models behind it. This guide
covers every command; what you need on your machine is listed in the
[requirements](requirements.md), the results in the [report](report.md).

All commands run inside the project with `uv run stickler …`. `uv run stickler --help` and
`uv run stickler <command> --help` show the options. `-v` before the command prints debug output.

---

## 1. Install

```console
git clone https://github.com/niklastshiang/stickler.git
cd stickler/
uv sync                                  # the harness environment (Python 3.12)
uv run stickler setup                    # every model's environment and weights (CPU)
uv run stickler doctor                   # what is still missing?
```

`setup` builds one environment per model under `adapters/<stage>/<model>/` and downloads its
weights; this takes a while and several GB (see [requirements](requirements.md)). Options:

| Option | Meaning |
|---|---|
| `--adapter adtof` | set up one model only (e.g. just what *Fast* needs: `adtof`, `beat_this`) |
| `--device cuda` | additional environment with PyTorch for NVIDIA GPUs |
| `--device rocm` | additional environment for AMD GPUs (only models that declare ROCm support) |

**MuScriptor's weights are gated:** accept the licence on its Hugging Face page, then log in once
with `uvx hf auth login` before running `setup`.

`stickler doctor` checks the GPU, each model's environments and weights, the Hugging Face login,
MuseScore and the datasets, and says how to fix what is missing.

---

## 2. Sheet music from a song: `notate`

```console
uv run stickler notate "Foo Fighters - Everlong.flac"
```

Separates the drums (depending on the pipeline), transcribes them, finds the beats, quantises
the hits to the beat grid and writes **MusicXML** to `results/notation/<song>.musicxml`. If
MuseScore 4 is installed (e.g. `flatpak install flathub org.musescore.MuseScore`), it also writes
a **PDF** next to it.

| Option | Meaning |
|---|---|
| `--out notes.musicxml` | where to write the MusicXML |
| `--pipeline none+adtof` | `separator+transcriber`, see the [report](report.md) for the choices |
| `--title`, `--artist` | override what is read from the file's tags |
| `--drums drums.flac` | also save the separated drum track (needs a separator in the pipeline) |
| `--no-pdf` | MusicXML only |
| `--device auto\|cpu\|gpu` | where to compute |

Every step is cached in `cache/`; running `notate` again on the same song is instant.

**Audio formats** (tested with every model on 2026-11-13):

| Format | How it is handled |
|---|---|
| WAV, FLAC, MP3, Ogg Vorbis, Opus, AIFF | read directly by every model |
| M4A/AAC, WMA and anything else `ffmpeg` decodes | converted to FLAC once (`cache/_decoded/`), then read by every model |

Cache entries belong to the original file's content, so the conversion never changes results.

---

## 3. Benchmark

### 3.1 Datasets: `fetch`

```console
uv run stickler fetch mdb                # MDB Drums from GitHub (CC BY-NC-SA)
uv run stickler fetch enst               # ENST-Drums: builds the evaluation mixes
```

**ENST-Drums** is only available on request (personal scientific use, see
[`enst-request.md`](enst-request.md)). Unpack the archive so that `data/enst/drummer_<n>/`
contains `annotation/`, `audio/wet_mix/` and `audio/accompaniment/`, then run `fetch enst`.
ENST data never leaves `data/enst/` (gitignored).

### 3.2 Compute, score, report

```console
uv run stickler run                      # compute everything config/benchmark.yaml asks for
uv run stickler eval                     # → results/metrics.csv, results/summary.csv
uv run stickler report                   # → results/report.html
```

`run` is resumable: every result is cached by input content and model code, an interrupted run
continues where it stopped, a failing model does not stop the others. `eval` computes nothing;
it scores what is in the cache and prints the ranking.

`--config config/own.yaml` selects another configuration (results then go to
`results/own/`); `run --device gpu` overrides the configured device.

### 3.3 Configuration files

A benchmark configuration (`config/*.yaml`) lists what to compute and how to score it:

```yaml
datasets: [mdb]                          # mdb, enst, own
separators: [none, oracle, demucs, roformer]
transcribers: [adt_str, adtof, muscriptor_m]
skip: ["none+muscriptor_m"]              # pairs not computed
device: auto                             # auto | cpu | gpu
schemes: ["5", "3"]                      # class schemes from config/classes.yaml
timeout:
  separators: 1800                       # seconds per call
  transcribers: {factor: 10, min: 120}   # 10 × song length, at least 120 s
```

Optional entries build further pipelines from cached results, without computing anything new:

| Entry | What it scores | Name in the results |
|---|---|---|
| `combos` | each class from another pipeline, e.g. `{quality: {demucs+muscriptor_m: [KD, SD, TT], none+adtof: [HH, CY]}}` | `combo + quality` |
| `fusions` | ADTOF's frame probabilities of several inputs averaged, thresholds per class (see `tune`) | `fusion + <name>` |
| `votes` | a hit counts if `min_agree` of the listed pipelines detect it | `vote + <name>` |
| `grid` | listed pipelines also after snapping to the beat grid, as the sheet music shows them | `<transcriber>@grid` |
| `consensus` | with `grid`: fill in hits that most similar bars have | `<transcriber>@rep` |

Combos may use fusions and votes as parts (`fusion+<name>`, `vote+<name>`).

### 3.4 Your own songs: `align`

The honest test is music you care about. For each song you need a recording and a drum
transcription as MIDI (for example one you made in MuseScore, or one you are allowed to
download).

1. Put the score under `data/own/<song>/score.mid` (and the PDF as `score.pdf` if you like).
2. Describe the song in `references/own/<song>.yaml`:

   ```yaml
   title: "Foo Fighters – Everlong"
   audio: "Foo Fighters - Everlong.flac"
   exclude: []                  # optional: [[start, end], …] in audio seconds to ignore
   ```

   `audio` is just the file name. Stickler looks for it in `data/own/<song>/` first, then
   anywhere below your music folder (`STICKLER_MUSIC_DIR`, otherwise your desktop's music
   folder, otherwise `~/Music`), so the file reveals nothing about how your collection is
   organised. A full path also works.
3. Align and check:

   ```console
   uv run stickler align                # all songs, or: uv run stickler align everlong
   ```

`align` lays the notes onto the recording and prints the quality checks (see the
[report](report.md#how-the-own-songs-become-references)). Only songs that pass take part in
`--config config/own.yaml`. Listen to `data/own/<song>/click.wav` (recording left, clicks on the
reference hits right) to judge a borderline song yourself; to accept it anyway, add
`approved_by_ear: "<why>"` to its YAML file.

Recordings, scores and alignments stay on your machine (`data/` is gitignored).

### 3.5 Tuning: `tune`

```console
uv run stickler tune --config config/benchmark.yaml --inputs none,demucs --name fused
```

Searches, per class, the fusion weights of ADTOF's probabilities on the given inputs and the
peak-picking threshold that maximise F1 on the cached runs of the given configurations, and
prints a `fusions` entry to paste into a configuration. Tune on one dataset and check the result
on another; settings tuned on MDB did not transfer to rock and metal recordings (report,
section 6).

---

## 4. Development helpers

### 4.1 Rented GPU: `remote`

```console
uv run stickler remote root@203.0.113.7 --port 22077 --config config/enst.yaml \
    --pod-id abc123 --wipe
```

Runs a configuration on a machine reachable over SSH (e.g. a RunPod pod): installs the tools,
uploads the code, the data and audio the configuration needs and the cache, builds CUDA
environments, runs with `--device gpu`, downloads the new cache entries and the scores.

| Option | Meaning |
|---|---|
| `--pod-id` | stop this RunPod pod afterwards (also on failure); needs the API key in `RUNPOD_API_KEY` or `~/.config/stickler/runpod.env` |
| `--wipe` | delete everything uploaded from the machine before stopping it (licensed data, your music) |

The Hugging Face token goes over the SSH connection's input, never onto a command line or disk.

### 4.2 Cache maintenance

| Command | Use |
|---|---|
| `stickler cache-migrate [--dry-run]` | move entries from older cache keys to the current ones; nothing is deleted (duplicates go to `cache/_superseded/`, unknown entries to `cache/_orphaned/`) |
| `stickler cache-digests <file>` | snapshot every model's code digest before an edit that does not change behaviour (e.g. a translated message) |
| `stickler cache-migrate --rekey-from <file>` | after such an edit, move the results to the new digests; never after a real code change |

### 4.3 Tests and checks

```console
scripts/check.sh fast                    # lint, format, floor guard (after every change)
scripts/check.sh task                    # plus the tests with coverage ≥ 95 % (before each commit)
uv run pytest -m adapters                # smoke tests with the real models (slow)
git config core.hooksPath .githooks      # run `check.sh task` before every commit
```

---

## 5. Where things are

| Path | Content | In git |
|---|---|---|
| `config/` | benchmark configurations, class schemes | yes |
| `adapters/<stage>/<model>/` | one folder per model: `run.py`, `setup.py`, `pyproject.toml`, README | yes (environments and weights not) |
| `references/own/` | descriptions of your own songs | yes |
| `data/` | datasets, your recordings and scores, alignments | no |
| `cache/` | every computed stem, transcription and beat track | no |
| `results/` | scores (`metrics.csv`, `summary.csv`) and `report.html` | no |
