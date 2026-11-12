# Adapter `roformer`

Band-Split RoFormer, Checkpoint **BS-Roformer-SW** (6 Stems), über [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator).

| | |
|---|---|
| Architektur | Lu et al.: *Music Source Separation with Band-Split RoPE Transformer*, ICASSP 2024. Implementierung nach [lucidrains/BS-RoFormer](https://github.com/lucidrains/BS-RoFormer) (MIT) |
| Bibliothek | `audio-separator[cpu]==0.48.0` (MIT, 2026-10-29) |
| Gewichte | `BS-Roformer-SW.ckpt` von jarredou, SHA-256 `24e7d35ee9c6…775916e`. Herkunft und Lizenz nur teilweise geklärt, siehe **ADR 0004** |
| Stems | bass, drums, guitar, other, piano, vocals. Genutzt wird nur `Drums` |

## Nutzung
```bash
uv run stickler setup --adapter roformer                # CPU
uv run stickler setup --adapter roformer --device rocm  # zusätzlich GPU-Umgebung
```

## Messungen (2026-11-12, MDB `MusicDelta_Punk`, 29 s, parallel zum laufenden Benchmark)
| Separator | Laufzeit | Macro-F1 mit `adt_str` |
|---|---|---|
| `oracle` (echter Drum-Stem) | – | 0,811 |
| `demucs`, CPU | 68 s | 0,790 |
| `roformer`, CPU | 212 s | 0,747 |
| `roformer`, GPU (ROCm) | 256 s | 0,747 |

Die GPU ist in fp32 auf der Radeon 840M auch hier langsamer, deshalb gilt `prefer_gpu = false` (ADR 0003).
`output_single_stem` greift bei diesem Checkpoint nicht zuverlässig: Es werden alle 6 Stems geschrieben, und der Adapter wählt die Datei mit „(drums)“ im Namen.
