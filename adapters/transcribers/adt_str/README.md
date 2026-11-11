# Adapter `adt_str`

Transformer-basierte Schlagzeug-Transkription, trainiert auf realistischen synthetischen Daten.

| | |
|---|---|
| Paper | Melucci, Merialdo, Akama: *Towards Realistic Synthetic Data for Automatic Drum Transcription*, arXiv:2601.09520 (Jan. 2026) |
| Code | https://github.com/pier-maker92/ADT_STR, v1.0.0 (Commit `77dbef2`, 2026-09-19) |
| Gewichte | https://huggingface.co/Pierfrancesco/adt-str, Revision `a33c5c6` (2026-09-17), Variante `setting-tau-0.8` |
| Lizenz | CC BY-SA 4.0 (Code und Gewichte, laut Repository) |
| Klassen | 26 GM-Klassen (47 GM-Percussion-Noten zusammengefasst) |
| Audio | 24 kHz, Abschnitte von 2,56 s |

Laut Paper erreicht das Modell neue Bestwerte auf ENST und MDB. Achtung: MDB ist damit kein unabhängiger Test für dieses Modell.

## Nutzung
```bash
uv run stickler setup --adapter adt_str      # Umgebung bauen + Bundle laden (~Gewichte nach weights/)
```
Die Inferenz nutzt `ADTTranscriber.from_pretrained(...)` aus dem HF-Bundle, wie im offiziellen README beschrieben. Zwei Anpassungen, beide aus dem offiziellen Repository übernommen:

1. **Normalisierung pro Abschnitt:** Die offizielle Auswertung (`eval.py` → `utils.audio_utils.normalize`) normalisiert jeden 2,56-s-Abschnitt auf Spitzenpegel, `ADTTranscriber.transcribe` macht das nicht. Ohne diesen Schritt ergab der 10-s-Ausschnitt von MDB `MusicDelta_Rock` (Drum-Stem) Macro-F1 0,48, mit ihm 0,75. Die Laufzeit sank von 215 s auf 9 s, weil der Decoder nicht mehr bis `max_length` läuft.
2. **Nummerierung:** Das Modell gibt eigene Klassennummern (35–60) aus, kein GM. Der Adapter übersetzt sie mit `MappingUtils.GM_custom_midi_to_Gm_standard_Mapping` aus dem Bundle zurück und schreibt das Ergebnis nach dem Stickler-Vertrag auf Kanal 10.

**Beobachtung:** Auf dem kompletten Mix ist das Modell deutlich schwächer (Hi-Hats werden als Toms erkannt). Es ist auf reinen Schlagzeug-Signalen trainiert, deshalb gehört vor diesen Adapter ein Separator.
