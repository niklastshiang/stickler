# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Specification: SPEC.md (living document; when a decision changes, update SPEC.md first)
- Plan and tasks: tasks/plan.md, tasks/todo.md
- Decisions: docs/adr/
- Everything in English: code, comments, docstrings, messages, documentation and commit messages (since 2026-11-12). Talk to the user in German.
- Until the adapter cache key ignores comments: do not edit an adapter's `run.py`, `setup.py` or `pyproject.toml` just to translate it. They are part of the cache key, and any change invalidates benchmark results.
- Check: `scripts/check.sh fast` after changes, `scripts/check.sh task` before every commit (also runs as the pre-commit hook).
- Only open-source models from actively maintained projects; each adapter README states the source (README/paper, version/commit).
