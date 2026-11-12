# Adapter `yourmt3`

YourMT3+ **YPTF.MoE+Multi (noPS)**: Mehrinstrumenten-Transkription (Perceiver-TF-Encoder mit Mixture of Experts, Multi-Channel-T5-Decoder). Stickler übernimmt nur die Drum-Spur.

| | |
|---|---|
| Paper | Chang, Benetos, Kirchhoff, Dixon: *YourMT3+: Multi-instrument Music Transcription with Enhanced Transformer Architectures and Cross-dataset Stem Augmentation*, IEEE MLSP 2024 (arXiv:2407.04822) |
| Code | Inferenz-Code aus dem Hugging-Face-Space https://huggingface.co/spaces/mimbres/YourMT3, Revision `5e66c1e` (2025-01-31). Das GitHub-Repo mimbres/YourMT3 (letzter Commit 2024-11-29) enthält nur die README. |
| Gewichte | Im selben Space: `amt/logs/2024/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/checkpoints/last.ckpt` (537 MB inkl. Code), Standard-Modell des Space und bestes Modell im Paper |
| Lizenz | Space Apache-2.0, GitHub-Repo GPL-3.0 |
| Eingabe | Mix oder Stem (trainiert auf Mehrinstrumenten-Mixes mit Stem-Augmentation) |

## Nutzung
```bash
uv run stickler setup --adapter yourmt3
```

## Umsetzung
Es gibt keinen offiziellen CLI. `run.py` lädt das Modell über `load_model_checkpoint` aus `model_helper.py` des Space, mit denselben Argumenten wie `app.py`. Danach baut es `transcribe()` nach: Mono, 16 kHz, Segmente à `input_frames`, Batch 8, Detokenisierung je Decoder-Kanal.

Abweichungen vom Space:
- **Präzision fp32 statt fp16**, weil der Adapter auf der CPU läuft.
- **Audio per soundfile** statt `torchaudio.load`, das in neueren Versionen torchcodec braucht.
- **MIDI-Ausgabe:** Den Drum-MIDI schreibt der gemeinsame Helfer. Das Modell liefert die Drum-Pitches bereits im GM-Schema, Velocity ist fest 100.

## Messungen (2026-11-12, CPU, parallel zum laufenden Benchmark)
| MDB-Track | Eingabe | Laufzeit | Macro-F1 (5 Klassen) |
|---|---|---|---|
| Punk (29 s) | Oracle-Stem | 29 s | 0,494 |
| Punk (29 s) | Mix | 101 s | 0,481 |
| 80sRock (36 s) | Mix | 110 s | 0,664 |

Das Timing stimmt: Der Kick-Versatz auf Punk liegt im Median bei −0,4 ms. Die Schwächen sind Modellqualität und kein Adapterfehler:
- Auf Punk erkennt das Modell die Hi-Hat kaum (Oracle: 7 von 50) und hört sie oft als China- oder Splash-Becken.
- Toms erzeugen viele Fehlalarme.

Auf dem Mix dekodiert das Modell alle Instrumente, deshalb dauert es dort etwa 3,5-mal so lange wie das Audio. Peak-RAM: ~2,5 GB.

Keine GPU-Variante: Bei allen bisherigen Modellen war die Radeon 840M langsamer als die CPU (ADR 0003).
