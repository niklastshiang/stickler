# Implementation Plan: Stickler

## Overview
Stickler vergleicht Pipelines aus Drum-Stem-Trennung und Schlagzeug-Transkription auf MDB Drums, später ENST, und auf eigenen Songs. Die beste Pipeline erzeugt MusicXML. Grundlage ist [SPEC.md](../SPEC.md), die Qualitätsgrenzen stehen in [CONSTRAINTS.md](../CONSTRAINTS.md). Die Aufgaben stehen in [todo.md](todo.md).

## Architecture Decisions
- **Adapter als Subprozess mit eigener uv-Umgebung:** Die Modelle haben unverträgliche Abhängigkeiten (Torch-Versionen, ROCm vs. CPU). Der Harness importiert nie Modellcode, er redet nur über Dateien (`drums.wav`, `drums.mid`, `beats.json`, `meta.json`) mit ihnen.
- **Bibliotheks-API zuerst:** `stickler.api` enthält die gesamte Logik, die CLI ist eine dünne Schicht. So kann die spätere GTK-Oberfläche dieselbe API nutzen.
- **Einheitliches Zwischenformat `Onsets`:** Onset-Zeiten pro Klasse (5er-/3er-Schema). Alle Referenzen und Modellausgaben werden darauf abgebildet, und nur darauf wird bewertet (`mir_eval.onset`, ±50 ms).
- **Cache-Schlüssel:** Hash aus Audio-Datei, Adapter-ID, Adapter-Version und Gerät. Ein zweiter Lauf rechnet nichts neu.
- **Vertikal schneiden:** Zuerst läuft eine Kombination (`none` × `adt_str`) komplett von Daten bis Metrik. Danach kommen Kandidaten in die Breite.
- **Riskantes früh:** Die ROCm-GPU wird gleich nach dem ersten Durchstich getestet (Task 6), noch vor den übrigen Adaptern.

## Phasen (Index; Details in todo.md)
| Phase | Tasks | Ergebnis |
|---|---|---|
| 0 Doku | 0 | ADRs für bereits getroffene Entscheidungen |
| 1 Durchstich | 1–5 | `none` × `adt_str` auf MDB → `metrics.csv` |
| 2 GPU | 6 | ROCm auf gfx1152 läuft oder ist begründet verworfen (ADR) |
| 3 Kandidaten | 7–12 | volle Matrix auf MDB |
| 4 Report & eigene Songs | 13–16 | HTML-Report, Alignment eigener Songs, ENST-Antrag |
| 5 Noten | 17–18 | `stickler notate` → MusicXML/PDF |

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| ROCm-Wheels für gfx1152 laufen instabil | Mittel | CPU-Fallback bleibt Pflicht. Kanal 7.14 vs. 10.x im Spike vergleichen, Entscheidung per ADR |
| YourMT3/ADTOF ohne offiziellen CLI | Mittel | Inferenz aus Space-/Notebook-Code nachbauen, Quelle und Commit pinnen. Scheitert das: Kandidat per ADR streichen |
| MuScriptor gated | Niedrig | User loggt sich ein (zugesagt). `doctor` prüft den Login |
| MDB-Daten stecken im Training einzelner Modelle | Mittel | Hinweis im Report. Die eigenen Songs gelten als sauberer Test |
| Alignment eigener Songs scheitert an Beat-Fehlern | Mittel | Click-Check-WAV zum Abhören, manueller Anker in der YAML-Datei |
| CPU-Laufzeit der Gesamtmatrix | Niedrig | Caching, Lauf über Nacht, GPU wo möglich |

## Voraussetzungen durch den User
- Bis Task 10: Lizenz für MuScriptor auf Hugging Face akzeptieren und `uvx hf auth login` ausführen.
- Bis Task 15: mindestens einen Song aus `Projekte/Schlagzeug` in MuseScore nachbauen und als MIDI exportieren (Wiederholungen ausgeschrieben).
- Optional: den ENST-Antrag (Entwurf aus Task 16) abschicken.

## Open Questions
- keine. Der ROCm-Kanal wird in Task 6 entschieden.
