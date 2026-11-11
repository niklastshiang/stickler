# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Spezifikation: SPEC.md (lebendes Dokument, bei Entscheidungsänderungen zuerst SPEC.md anpassen)
- Plan und Aufgaben: tasks/plan.md, tasks/todo.md
- Entscheidungen: docs/adr/
- Kommunikation, Kommentare und Docstrings auf Deutsch, Bezeichner auf Englisch.
- Prüfen: `scripts/check.sh fast` nach Änderungen, `scripts/check.sh task` vor jedem Commit (läuft auch als pre-commit-Hook).
- Nur Open-Source-Modelle und aktiv gepflegte Projekte; die Quelle (README/Paper, Version/Commit) steht im README jedes Adapters.
