# Adapter `demucs`

Hybrid Transformer Demucs (v4), Variante `htdemucs_ft`, trennt den Drum-Stem aus dem Mix.

| | |
|---|---|
| Paper | Rouard, Massa, Défossez: *Hybrid Transformers for Music Source Separation*, ICASSP 2023 |
| Code | https://github.com/adefossez/demucs (gepflegter Fork, ADR 0001), PyPI `demucs==4.1.0` (Release 2026-07-11), Stand Commit `829d218` (2026-10-26) |
| Gewichte | Hugging Face, geladen über `demucs.api` (seit v4.1.0), Ablage `weights/` |
| Lizenz | MIT (Code und Gewichte) |
| Stems | drums, bass, other, vocals. Genutzt wird nur `drums` |

## Nutzung
```bash
uv run stickler setup --adapter demucs                # CPU
uv run stickler setup --adapter demucs --device rocm  # zusätzlich GPU-Umgebung
```
Die Inferenz läuft über `demucs.api.Separator(model="htdemucs_ft").separate_audio_file(...)` mit den Standardparametern der Kommandozeile. Der Drum-Stem wird als 24-bit-WAV in der Modell-Abtastrate (44,1 kHz, Stereo) gespeichert.

## Messungen (2026-11-11, MDB `MusicDelta_Punk`, 29 s)
| | Laufzeit | Macro-F1 mit `adt_str` |
|---|---|---|
| `oracle` (echter Drum-Stem) | – | 0,811 |
| `demucs`, CPU | 68 s | 0,790 |
| `demucs`, GPU (ROCm) | 120 s | 0,792 |

Die GPU ist in fp32 auf der Radeon 840M langsamer, deshalb gilt `prefer_gpu = false` (ADR 0003). Die Stems von CPU und GPU unterscheiden sich leicht (SNR 27 dB). Ein Grund ist der zufällige Zeitversatz bei `shifts=1`, dem Standardwert von Demucs. Ergebnisse sind deshalb nicht bitgenau reproduzierbar, der Cache hält sie aber fest.
