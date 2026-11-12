# Adapter `muscriptor_s`

MuScriptor **small**: Mehrinstrumenten-Transkription (Transformer-Sprachmodell über Audio-Tokens). Stickler übernimmt nur die Drum-Spur.

| | |
|---|---|
| Paper | Rouard, Krause, Roebel, Simon-Gabriel, Défossez: *MuScriptor: An Open Model for Multi-Instrument Music Transcription*, ISMIR 2026 (arXiv:2607.08168) |
| Code | https://github.com/muscriptor/muscriptor (Kyutai × Mirelo), PyPI `muscriptor==0.4.0`, Stand Commit `8a1ef88` (2026-10-20) |
| Gewichte | https://huggingface.co/MuScriptor/muscriptor-small, **gated**: Lizenz akzeptieren, `uvx hf auth login` |
| Lizenz | Code MIT, Gewichte CC BY-NC 4.0 (ADR 0002) |
| Eingabe | Mix oder Stem (trainiert auf echten Mehrinstrumenten-Aufnahmen) |

## Nutzung
```bash
uv run stickler setup --adapter muscriptor_s
```

## Abweichung von der Doku-Empfehlung
Die Doku empfiehlt `transcribe_and_postprocess`, wenn genaues Timing zählt. Dessen Zeitkorrektur über das Beat-Raster (beat_this) verschob die Noten auf MDB `MusicDelta_Punk` aber um 15–40 ms **zu früh**. Die rohen Ereignisse aus `transcribe` sind dagegen schon pünktlich (Kick-Median +10 ms auf dem Mix, 0 ms auf dem Demucs-Stem). Der Adapter nutzt deshalb `transcribe` (greedy, alle Instrumente erlaubt).

| small, MDB Punk | Mix | Demucs-Stem |
|---|---|---|
| `transcribe_and_postprocess` | 0,474 | 0,319 |
| `transcribe` (roh) | 0,793 | 0,733 |

## Messungen (2026-11-12, MDB `MusicDelta_Punk`, 29 s, parallel zum laufenden Benchmark)
| Modell | Eingabe | Laufzeit | Macro-F1 |
|---|---|---|---|
| small | Mix | 96 s (CPU) | 0,793 |
| small | Demucs | 16 s (CPU) | 0,726 |
| medium | Mix | 213 s (CPU), 357 s (GPU) | 0,825 |
| medium | Demucs | 46 s (CPU), 54 s (GPU) | 0,813 |

Die GPU nutzt fp16-Autocast und ist trotzdem langsamer. Das Dekodieren ist durch die Speicherbandbreite begrenzt, und die iGPU teilt sich den Arbeitsspeicher. Deshalb gilt `prefer_gpu = false`.
