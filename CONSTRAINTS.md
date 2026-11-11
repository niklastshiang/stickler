# Constraints

Last reviewed: 2026-11-11 vom Projektinhaber (Interview: keine weiteren Dimensionen, Verstöße blockieren, Abdeckung 80 % fest)

Gilt für den Harness (`src/stickler/`, `tests/`, `scripts/`). Adapter unter `adapters/` sind dünne Wrapper um fremden Modellcode. Für sie gelten der Floor und Lint, aber keine Abdeckungsgrenze.

## Floor (always enforced, no setup required)

- No new suppression comments: `# noqa`, `# type: ignore`, `# pragma: no cover`, `# ruff: noqa`
- No unimplemented stubs: `raise NotImplementedError`, `except …: pass`, `TODO` statt Implementierung
- No skipped or deleted tests without a reason in the commit message: `@pytest.mark.skip`, `pytest.skip(` …
- No secrets in source: Hugging-Face-Tokens (`hf_…`) kommen nur über `HF_TOKEN` oder `hf auth login`
- No audio, datasets or model weights in git: `.wav/.mp3/.flac/.ckpt/.pth/.safetensors` stehen in `.gitignore`
- This file does not get weakened to make a change pass

Geprüft durch `uv run python scripts/floor_guard.py` (diff-basiert, Exit 0 sauber / 1 Verstoß / 2 Guard konnte nicht laufen). Es ist eine Python-Portierung der Referenz aus `agent-skills/constraint-driven-development`.

## Enforced with numbers

| Dimension | Rule | Checked by | Runs at |
|-----------|------|-----------|---------|
| Lint | Zero errors from our ruff config | `uv run ruff check .` | every edit |
| Format | Zero files needing reformat | `uv run ruff format --check .` | every edit |
| Floor | Zero floor violations in the diff | `uv run python scripts/floor_guard.py` | every edit |
| Tests | All tests pass | `uv run pytest -q` | task end, pre-commit |
| Coverage | `src/stickler` line coverage >= 80% (ohne `cli.py`) | `uv run pytest -q --cov --cov-fail-under=80` | task end, pre-commit |

Gründe:
- **80 % fest:** Das Projekt startet bei null, damit ist die Zahl für neuen Code von Anfang an erreichbar. Sie zwingt zu Tests für die Bewertungslogik, an der die Aussagekraft des ganzen Benchmarks hängt.
- **Verstöße blockieren:** Der Git-Hook `.githooks/pre-commit` führt `scripts/check.sh task` aus. Ein roter Check verhindert den Commit.
- **Zeitbudget:** `scripts/check.sh fast` < 5 s, `scripts/check.sh task` < 90 s. Langsame Modell-Tests (`pytest -m adapters`) zählen nicht zum Standardlauf und laufen bei Aufgaben, die Adapter betreffen.

## Measured, not yet enforced

| Metric | Today | Direction |
|--------|-------|-----------|
| – | – | – |

## Exceptions

| ID | Rule | Path | Reason | Owner | Expires |
|----|------|------|--------|-------|---------|
