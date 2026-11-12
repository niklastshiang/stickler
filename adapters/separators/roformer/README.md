# Adapter `roformer`

Band-Split RoFormer, checkpoint **BS-Roformer-SW** (6 stems), via [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator).

| | |
|---|---|
| Architecture | Lu et al.: *Music Source Separation with Band-Split RoPE Transformer*, ICASSP 2024. Implementation after [lucidrains/BS-RoFormer](https://github.com/lucidrains/BS-RoFormer) (MIT) |
| Library | `audio-separator[cpu]==0.48.0` (MIT, 2026-10-29) |
| Weights | `BS-Roformer-SW.ckpt` from jarredou, SHA-256 `24e7d35ee9c6…775916e`. Origin and license only partially clarified, see **ADR 0004** |
| Stems | bass, drums, guitar, other, piano, vocals. Only `Drums` is used |

## Usage
```bash
uv run stickler setup --adapter roformer                # CPU
uv run stickler setup --adapter roformer --device rocm  # additionally GPU environment
```

## Measurements (2026-11-12, MDB `MusicDelta_Punk`, 29 s, in parallel with the running benchmark)
| Separator | Runtime | Macro-F1 with `adt_str` |
|---|---|---|
| `oracle` (real drum stem) | – | 0.811 |
| `demucs`, CPU | 68 s | 0.790 |
| `roformer`, CPU | 212 s | 0.747 |
| `roformer`, GPU (ROCm) | 256 s | 0.747 |

The GPU is also slower on the Radeon 840M in fp32, so `prefer_gpu = false` applies (ADR 0003).
`output_single_stem` does not work reliably with this checkpoint: all 6 stems are written, and the adapter selects the file with "(drums)" in its name.
