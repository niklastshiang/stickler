# Adapter `demucs`

Hybrid Transformer Demucs (v4), variant `htdemucs_ft`, separates the drum stem from the mix.

| | |
|---|---|
| Paper | Rouard, Massa, Défossez: *Hybrid Transformers for Music Source Separation*, ICASSP 2023 |
| Code | https://github.com/adefossez/demucs (maintained fork, ADR 0001), PyPI `demucs==4.1.0` (release 2026-07-11), as of commit `829d218` (2026-10-26) |
| Weights | Hugging Face, loaded via `demucs.api` (since v4.1.0), stored in `weights/` |
| License | MIT (code and weights) |
| Stems | drums, bass, other, vocals. Only `drums` is used |

## Usage
```bash
uv run stickler setup --adapter demucs                # CPU
uv run stickler setup --adapter demucs --device rocm  # additionally GPU environment
```
Inference runs via `demucs.api.Separator(model="htdemucs_ft").separate_audio_file(...)` with the default parameters of the command line. The drum stem is saved as a 24-bit WAV at the model's sample rate (44.1 kHz, stereo).

## Measurements (2026-11-11, MDB `MusicDelta_Punk`, 29 s)
| | Runtime | Macro-F1 with `adt_str` |
|---|---|---|
| `oracle` (real drum stem) | – | 0.811 |
| `demucs`, CPU | 68 s | 0.790 |
| `demucs`, GPU (ROCm) | 120 s | 0.792 |

The GPU is slower on the Radeon 840M in fp32, so `prefer_gpu = false` applies (ADR 0003). The stems from CPU and GPU differ slightly (SNR 27 dB). One reason is the random time offset with `shifts=1`, Demucs's default value. Results are therefore not bit-exactly reproducible, but the cache stores them.
