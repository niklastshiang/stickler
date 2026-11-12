#!/usr/bin/env bash
# Mirrors the "Checked by" column in CONSTRAINTS.md. On any deviation, CONSTRAINTS.md wins.
#   fast: after every change (< 5 s)   task: end of task / pre-commit (< 90 s)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
stage="${1:-task}"
uv run ruff check .
uv run ruff format --check .
uv run python scripts/floor_guard.py
if [[ "$stage" == "task" ]]; then
  uv run pytest -q --cov --cov-fail-under=95
fi
