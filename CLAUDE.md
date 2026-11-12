# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Specification: SPEC.md (living document; when a decision changes, update SPEC.md first)
- Plan and tasks: tasks/plan.md, tasks/todo.md
- Decisions: docs/adr/
- Everything in English: code, comments, docstrings, messages, documentation and commit messages (since 2026-11-12). Talk to the user in German.
- Adapter cache keys hash `run.py`, `setup.py` and `pyproject.toml` without comments and docstrings. Any other edit (strings, TOML values) invalidates cached results. For an edit that does not change behaviour, run `stickler cache-digests <file>` before it and `stickler cache-migrate --rekey-from <file>` after it; never rekey after a real code change.
- Check: `scripts/check.sh fast` after changes, `scripts/check.sh task` before every commit (also runs as the pre-commit hook).
- Only open-source models from actively maintained projects; each adapter README states the source (README/paper, version/commit).
