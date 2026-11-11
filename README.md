# Stickler

Benchmark für automatische Schlagzeug-Transkription (Audio → Noten) mit ausschließlich Open-Source-Modellen.

- Was und warum: [SPEC.md](SPEC.md)
- Qualitätsgrenzen: [CONSTRAINTS.md](CONSTRAINTS.md)

```bash
uv sync
git config core.hooksPath .githooks   # Pre-Commit-Prüfung aktivieren
scripts/check.sh task
```
