# Adapter `adtof`

ADTOF Frame_RNN: CNN + bidirectional GRUs on a spectrogram, trained on the ADTOF dataset (crowdsourced annotations of real songs from rhythm games).

| | |
|---|---|
| Papers | Zehren, Alunno, Bientinesi: *ADTOF: A large dataset of non-synthetic music for ADT*, ISMIR 2021. *High-Quality and Reproducible ADT from Crowdsourced Data*, Signals 4 (2023) |
| Original | https://github.com/MZehren/ADTOF (TensorFlow/Keras + madmom) |
| Port | https://github.com/xavriley/ADTOF-pytorch, commit `85c192e` (2025-11-11). Weights converted from the original; according to the port, −0.2% F-measure on MDBDrums++ |
| License | Original: CC BY-NC-SA 4.0. The port has **no LICENSE file of its own**, so the original's license applies (ADR 0002) |
| Classes | 5: Kick 35, Snare 38, Toms 47, Hi-Hat 42, Cymbals/Ride 49 |
| Input | Mix or drum stem. Trained on real songs, therefore no `input = "stem"` |

## Usage
```bash
uv run stickler setup --adapter adtof
```
Inference uses `adtof_pytorch.transcribe_to_midi(...)` with the default thresholds `[0.22, 0.24, 0.32, 0.22, 0.30]` and 100 fps.

## Measurements (2026-11-12, MDB `MusicDelta_Punk`, 29 s, CPU)
| Input | Runtime | Macro-F1 (5 classes) | for comparison `adt_str` |
|---|---|---|---|
| Mix (`none`) | 3.6 s | 0.803 | – (stems only) |
| `demucs` | 1.3 s | 0.854 | 0.790 |
| `oracle` | 1.1 s | 0.871 | 0.811 |

No GPU variant: the CPU needs about 1 s per song.
