# Adapter `muscriptor_m`

MuScriptor **medium**: multi-instrument transcription (transformer language model over audio tokens). Stickler only takes the drum track.

| | |
|---|---|
| Paper | Rouard, Krause, Roebel, Simon-Gabriel, Défossez: *MuScriptor: An Open Model for Multi-Instrument Music Transcription*, ISMIR 2026 (arXiv:2607.08168) |
| Code | https://github.com/muscriptor/muscriptor (Kyutai × Mirelo), PyPI `muscriptor==0.4.0`, as of commit `8a1ef88` (2026-10-20) |
| Weights | https://huggingface.co/MuScriptor/muscriptor-medium, **gated**: accept the license, then `uvx hf auth login` |
| License | Code MIT, weights CC BY-NC 4.0 (ADR 0002) |
| Input | Mix or stem (trained on real multi-instrument recordings) |

## Usage
```bash
uv run stickler setup --adapter muscriptor_m
```

## Deviation from the documentation's recommendation
The documentation recommends `transcribe_and_postprocess` when exact timing matters. However, its time correction via the beat grid (beat_this) shifted the notes on MDB `MusicDelta_Punk` **too early** by 15–40 ms. The raw events from `transcribe`, by contrast, are already on time (kick median +10 ms on the mix, 0 ms on the Demucs stem). The adapter therefore uses `transcribe` (greedy, all instruments allowed).

| small, MDB Punk | Mix | Demucs stem |
|---|---|---|
| `transcribe_and_postprocess` | 0.474 | 0.319 |
| `transcribe` (raw) | 0.793 | 0.733 |

## Measurements (2026-11-12, MDB `MusicDelta_Punk`, 29 s, in parallel with the running benchmark)
| Model | Input | Runtime | Macro-F1 |
|---|---|---|---|
| small | Mix | 96 s (CPU) | 0.793 |
| small | Demucs | 16 s (CPU) | 0.726 |
| medium | Mix | 213 s (CPU), 357 s (GPU) | 0.825 |
| medium | Demucs | 46 s (CPU), 54 s (GPU) | 0.813 |

The GPU uses fp16 autocast and is still slower. Decoding is limited by memory bandwidth, and the iGPU shares system memory. Therefore `prefer_gpu = false` applies.
