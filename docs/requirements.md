# What Stickler needs

Measured on the development laptop (AMD Ryzen AI 5 340, 12 threads, 30 GB RAM, Radeon 840M) and
on rented NVIDIA GPUs. How the commands work: [CLI guide](cli.md).

## Software

| What | Why | Install (Fedora / Debian) |
|---|---|---|
| Linux | the only platform Stickler is built and tested on | – |
| [`uv`](https://docs.astral.sh/uv/) | Python environments; it fetches Python 3.12 and PyTorch for each model itself | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `ffmpeg` | decoding audio; converts formats the models cannot read (M4A/AAC, WMA, …) to FLAC | `sudo dnf install ffmpeg-free` / `sudo apt install ffmpeg` |
| `git` | cloning; MDB Drums is downloaded with git | usually present |
| MuseScore 4 (optional) | PDF sheet music | `flatpak install flathub org.musescore.MuseScore` |
| Hugging Face account (for MuScriptor) | its weights are gated | accept the licence, `uvx hf auth login` |

A GPU is optional. NVIDIA (CUDA) speeds up the slow models 10–30×; on the integrated Radeon 840M
(ROCm) every model was slower than on the CPU.

## By mode

Time for a 4-minute song on the laptop CPU; GPU figures in the table below.

| Mode | Models | Time | RAM | Disk (environments + weights) |
|---|---|---|---|---|
| **Fast** | ADTOF, Beat This! | ~15 s | ~1 GB | ~2.2 GB |
| **Quality** | + Demucs, MuScriptor medium | ~14 min | ~4 GB | ~5.6 GB |
| **Full benchmark** | all 8 models | several hours on the CPU (MDB: 23 songs, ~5 h) | ~4 GB | ~13 GB |

Add a few GB for `uv`'s package cache and the result cache (`cache/`: stems and transcriptions,
about 60 MB per song for the full matrix).

## Per model

| Model | Environment (CPU) | Weights | Peak RAM (CPU) | RTF laptop CPU | RTF GPU |
|---|---|---|---|---|---|
| ADTOF | 1.3 GB | in the package | ~0.7 GB (max 1.6) | 0.03 | 0.02 |
| Beat This! | 0.8 GB | 78 MB | ~0.5 GB | ~0.03 | – |
| Demucs `htdemucs_ft` | 0.9 GB | 321 MB | ~2.7 GB (max 4.0) | 1.84 | ~0.2 |
| BS-RoFormer | 1.4 GB | 668 MB | ~2.4 GB (max 2.7) | 4.17 | 0.13 |
| MuScriptor medium | 0.9 GB | 1.2 GB | ~2.6 GB | 1.65 | 0.14 |
| ADT_STR | 1.0 GB | 277 MB | ~0.7 GB (max 3.7) | 0.59 | 0.07 |
| YourMT3+ | 1.4 GB | 1.3 GB | ~2.6 GB | 1.76 | ~0.2 |
| MuScriptor small (not in the default matrix) | 0.9 GB | 393 MB | ~1.0 GB | – | – |

RTF (real-time factor) = processing time ÷ song length: 0.5 means a 4-minute song takes 2 minutes.
GPU: RTX 4090 (5-min song) or RTX 3090 (ENST, incl. model loading). A GPU environment
(`setup --device cuda` or `rocm`) adds about 5–6 GB per model.

Peak RAM is per model; models run one after another, so the largest one counts.

## Datasets

| Dataset | Size on disk | How to get it |
|---|---|---|
| MDB Drums | ~0.6 GB | `stickler fetch mdb` (CC BY-NC-SA) |
| ENST-Drums (minus-one) | 9.6 GB download, ~1.9 GB kept | `stickler fetch enst` from Zenodo (CC BY-NC-ND 4.0, research only) |
| Own songs | your recordings | see the [CLI guide](cli.md#34-your-own-songs-align) |
