# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Specification: SPEC.md (living document; when a decision changes, update SPEC.md first)
- Plan and tasks: tasks/plan.md, tasks/todo.md
- Decisions: docs/adr/
- Everything in English: code, comments, docstrings, messages, documentation and commit messages (since 2026-11-12). Talk to the user in German.
- Adapter cache keys hash `run.py`, `setup.py` and `pyproject.toml` without comments and docstrings. Any other edit (strings, TOML values) invalidates cached results. For an edit that does not change behaviour, run `stickler cache-digests <file>` before it and `stickler cache-migrate --rekey-from <file>` after it; never rekey after a real code change.
- Check: `scripts/check.sh fast` after changes, `scripts/check.sh task` before every commit (also runs as the pre-commit hook).
- Only open-source models from actively maintained projects; each adapter README states the source (README/paper, version/commit). Check maintenance status and licence on the web before recommending a project, not from memory (e.g. Demucs is maintained in the fork adefossez/demucs). Non-commercial weights are fine; Stickler never ships them.
- Releases are numbered 1, 2, 3 … (+1 per release, no SemVer, ADR 0006); every release counts, fixes included.
- Secrets (`~/.config/stickler/runpod.env`, the Hugging Face token): never `source`, `cat` or print them, never print raw API responses (a RunPod pod response contains the pod's Jupyter password). Check files only by metadata or a silent pattern match, and print only the fields you need (status, IP, port).
