#!/usr/bin/env bash
# Spiegelt die "Checked by"-Spalte in CONSTRAINTS.md. Bei Abweichung gilt CONSTRAINTS.md.
#   fast: nach jeder Änderung (< 5 s)   task: Aufgabenende / pre-commit (< 90 s)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
stage="${1:-task}"
uv run ruff check .
uv run ruff format --check .
uv run python scripts/floor_guard.py
if [[ "$stage" == "task" ]]; then
  uv run pytest -q --cov --cov-fail-under=95
fi
