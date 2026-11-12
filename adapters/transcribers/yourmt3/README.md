# Adapter `yourmt3`

YourMT3+ **YPTF.MoE+Multi (PS)**: Mehrinstrumenten-Transkription (Perceiver-TF-Encoder mit Mixture of Experts, Multi-Channel-T5-Decoder). Stickler übernimmt nur die Drum-Spur.

| | |
|---|---|
| Paper | Chang, Benetos, Kirchhoff, Dixon: *YourMT3+: Multi-instrument Music Transcription with Enhanced Transformer Architectures and Cross-dataset Stem Augmentation*, IEEE MLSP 2024 (arXiv:2407.04822) |
| Code | Inferenz-Code aus dem Hugging-Face-Space https://huggingface.co/spaces/mimbres/YourMT3, Revision `5e66c1e` (2025-01-31). Das GitHub-Repo mimbres/YourMT3 (letzter Commit 2024-11-29) enthält nur die README. |
| Gewichte | Im selben Space: `amt/logs/2024/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b80_ps2/checkpoints/model.ckpt` (759 MB). Die Space-Voreinstellung (noPS) ist beim Schlagzeug deutlich schwächer, siehe ADR 0005. |
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
Variantenvergleich auf 7 MDB-Proben: siehe `docs/adr/0005-yourmt3-variante.md`. Im Mittel erreicht PS einen Macro-F1 von 0,759 (5 Klassen), noPS 0,550.

Laufzeit: auf dem Mix etwa 3,5-mal so lang wie das Audio, weil alle Instrumente dekodiert werden. Auf dem Drum-Stem etwa so lang wie das Audio. Peak-RAM: ~2,5 GB.

Das Timing stimmt, der Kick-Median-Versatz liegt bei −0,4 ms. Verbleibende Schwächen sind Modellqualität:
- Offene Hi-Hats werden als Becken erkannt.
- Bei schnellem Swing-Jazz (CoolJazz) sinkt die Erkennung auf 0,44.

Keine GPU-Variante: Bei allen bisherigen Modellen war die Radeon 840M langsamer als die CPU (ADR 0003).
