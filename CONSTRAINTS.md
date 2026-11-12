# Constraints

Last reviewed: 2026-11-12 by the project owner (interview: no further dimensions, violations block; coverage raised from 80% to 95% on 2026-11-12)

Applies to the harness (`src/stickler/`, `tests/`, `scripts/`). Adapters under `adapters/` are thin wrappers around third-party model code. The floor and lint apply to them, but no coverage limit.

## Floor (always enforced, no setup required)

- No new suppression comments: `# noqa`, `# type: ignore`, `# pragma: no cover`, `# ruff: noqa`
- No unimplemented stubs: `raise NotImplementedError`, `except …: pass`, `TODO` instead of an implementation
- No skipped or deleted tests without a reason in the commit message: `@pytest.mark.skip`, `pytest.skip(` …
- No secrets in source: Hugging Face tokens (`hf_…`) only come via `HF_TOKEN` or `hf auth login`
- No audio, datasets or model weights in git: `.wav/.mp3/.flac/.ckpt/.pth/.safetensors` are in `.gitignore`
- This file does not get weakened to make a change pass

Checked by `uv run python scripts/floor_guard.py` (diff-based, exit 0 clean / 1 violation / 2 guard could not run). It is a Python port of the reference from `agent-skills/constraint-driven-development`.

## Enforced with numbers

| Dimension | Rule | Checked by | Runs at |
|-----------|------|-----------|---------|
| Lint | Zero errors from our ruff config | `uv run ruff check .` | every edit |
| Format | Zero files needing reformat | `uv run ruff format --check .` | every edit |
| Floor | Zero floor violations in the diff | `uv run python scripts/floor_guard.py` | every edit |
| Tests | All tests pass | `uv run pytest -q` | task end, pre-commit |
| Coverage | `src/stickler` line coverage >= 95% (excluding `cli.py`) | `uv run pytest -q --cov --cov-fail-under=95` | task end, pre-commit |

Reasons:
- **80% fixed:** The project started from zero, so the number was reachable for new code from the beginning. It forces tests for the scoring logic, on which the meaningfulness of the whole benchmark depends.
- **Raised to 95% (2026-11-12):** At the project owner's request, at a level of 97.5%. The margin to 100% leaves room for paths that only run with a real GPU or real models.
- **Violations block:** The git hook `.githooks/pre-commit` runs `scripts/check.sh task`. A red check prevents the commit.
- **Time budget:** `scripts/check.sh fast` < 5 s, `scripts/check.sh task` < 90 s. Slow model tests (`pytest -m adapters`) are not part of the default run and run for tasks that concern adapters.

## Measured, not yet enforced

| Metric | Today | Direction |
|--------|-------|-----------|
| – | – | – |

## Exceptions

| ID | Rule | Path | Reason | Owner | Expires |
|----|------|------|--------|-------|---------|
