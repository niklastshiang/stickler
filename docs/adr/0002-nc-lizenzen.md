# ADR 0002: Modellgewichte unter Non-Commercial-Lizenz sind erlaubt

- Status: angenommen
- Datum: 2026-11-11

## Kontext
Einige der stärksten offenen Schlagzeug- und Mehrinstrumenten-Transkriber haben zwar offenen Code, ihre Gewichte stehen aber unter Non-Commercial-Lizenzen:
- ADTOF: CC BY-NC-SA 4.0
- MuScriptor: Code MIT, Gewichte CC BY-NC 4.0, Download auf Hugging Face erst nach Zustimmung zur Lizenz

Stickler wird ausschließlich privat genutzt.

## Entscheidung
NC-lizenzierte Gewichte dürfen in den Benchmark aufgenommen werden, wenn Code und Gewichte öffentlich zugänglich sind. Closed-Source-Dienste und proprietäre APIs bleiben ausgeschlossen.

## Konsequenzen
- Jedes Adapter-README nennt die Lizenz von Code **und** Gewichten.
- Der Report markiert NC-Modelle, damit bei einer späteren kommerziellen Nutzung (z. B. veröffentlichte GTK-App) klar ist, welche Pipelines dann wegfallen.
- Gewichte werden nie ins Repository eingecheckt (CONSTRAINTS.md).
