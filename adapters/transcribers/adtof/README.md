# Adapter `adtof`

ADTOF Frame_RNN: CNN + bidirektionale GRUs auf einem Spektrogramm, trainiert auf dem ADTOF-Datensatz (Crowdsourcing-Annotationen echter Songs aus Rhythmusspielen).

| | |
|---|---|
| Papers | Zehren, Alunno, Bientinesi: *ADTOF: A large dataset of non-synthetic music for ADT*, ISMIR 2021. *High-Quality and Reproducible ADT from Crowdsourced Data*, Signals 4 (2023) |
| Original | https://github.com/MZehren/ADTOF (TensorFlow/Keras + madmom) |
| Port | https://github.com/xavriley/ADTOF-pytorch, Commit `85c192e` (2025-11-11). Gewichte aus dem Original konvertiert, laut Port −0,2 % F-Measure auf MDBDrums++ |
| Lizenz | Original: CC BY-NC-SA 4.0. Der Port hat **keine eigene LICENSE-Datei**, es gilt deshalb die Lizenz des Originals (ADR 0002) |
| Klassen | 5: Kick 35, Snare 38, Toms 47, Hi-Hat 42, Becken/Ride 49 |
| Eingabe | Mix oder Drum-Stem. Trainiert auf echten Songs, deshalb kein `input = "stem"` |

## Nutzung
```bash
uv run stickler setup --adapter adtof
```
Die Inferenz nutzt `adtof_pytorch.transcribe_to_midi(...)` mit den Standard-Schwellen `[0.22, 0.24, 0.32, 0.22, 0.30]` und 100 fps.

## Messungen (2026-11-12, MDB `MusicDelta_Punk`, 29 s, CPU)
| Eingabe | Laufzeit | Macro-F1 (5 Klassen) | zum Vergleich `adt_str` |
|---|---|---|---|
| Mix (`none`) | 3,6 s | 0,803 | – (nur Stems) |
| `demucs` | 1,3 s | 0,854 | 0,790 |
| `oracle` | 1,1 s | 0,871 | 0,811 |

Keine GPU-Variante: Die CPU braucht etwa 1 s je Song.
