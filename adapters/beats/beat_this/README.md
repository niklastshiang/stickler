# Adapter `beat_this`

Beat This!: Beat- und Downbeat-Tracking ohne DBN-Nachbearbeitung (Transformer auf dem Spektrogramm).
Stickler nutzt die Beats, um die Noten eigener Songs auf die Audio-Zeit zu legen (`stickler align`),
und später für die Quantisierung in Notenschrift.

| | |
|---|---|
| Paper | Foscarin, Schlüter, Widmer: *Beat this! Accurate beat tracking without DBN postprocessing*, ISMIR 2024 (arXiv:2407.21658) |
| Code | https://github.com/CPJKU/beat_this, PyPI `beat-this==1.1.0` (letzter Push 2026-05-28) |
| Gewichte | Checkpoint `final0` (Standard der Bibliothek), von cloud.cp.jku.at, 78 MB |
| Lizenz | MIT (Code und Gewichte) |

## Nutzung
```bash
uv run stickler setup --adapter beat_this
```

## Ausgabe
`beats.json` = `{"beats": [s, …], "downbeats": [s, …]}`. Downbeats sind eine Teilmenge der Beats.

## Messung (2026-11-12, CPU)
- **RATATATA** (Electric Callboy, 216 s, laut Noten 140 BPM): 15 s Laufzeit, 554 MB Peak-RAM.
- **Ergebnis:** 499 Beats und 127 Downbeats.
- **Tempo:** Der mittlere Beat-Abstand ergibt 142,9 BPM. Die Abweichung zu 140 BPM kommt vom 20-ms-Raster des Modells (50 Frames/s), einzelne Beats streuen um ±20 ms. Für den Zeitabgleich wird deshalb eine glatte Tempokurve angepasst, statt jeden Beat einzeln zu übernehmen.

Keine GPU-Variante: 15 s je Song auf der CPU, und die Radeon 840M war bisher bei jedem Modell langsamer (ADR 0003).
