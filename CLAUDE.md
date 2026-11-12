# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Spezifikation: SPEC.md (lebendes Dokument, bei Entscheidungsänderungen zuerst SPEC.md anpassen)
- Plan und Aufgaben: tasks/plan.md, tasks/todo.md
- Entscheidungen: docs/adr/
- Code und Dokumentation auf Englisch: Kommentare, Docstrings, Ausgaben, Fehlermeldungen, README, SPEC, ADRs, Aufgaben (Umstellung läuft seit 2026-11-12). Mit dem User wird Deutsch gesprochen.
- Ausnahme bis auf Weiteres: `run.py`, `setup.py` und `pyproject.toml` der Adapter nicht nur für Übersetzungen ändern (sie gehen in den Cache-Schlüssel ein; jede Änderung macht Benchmark-Ergebnisse ungültig). CONSTRAINTS.md wird separat übersetzt (Floor-Guard).
- Prüfen: `scripts/check.sh fast` nach Änderungen, `scripts/check.sh task` vor jedem Commit (läuft auch als pre-commit-Hook).
- Nur Open-Source-Modelle und aktiv gepflegte Projekte; die Quelle (README/Paper, Version/Commit) steht im README jedes Adapters.
