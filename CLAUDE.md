# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Specification: SPEC.md (living document; when a decision changes, update SPEC.md first)
- Plan and tasks: tasks/plan.md, tasks/todo.md
- Decisions: docs/adr/
- Everything in English: code, comments, docstrings, messages, documentation and commit messages (since 2026-11-12). Talk to the user in German.
- Adapter cache keys hash every Python module and `pyproject.toml` of the adapter plus `adapters/_common`, without comments and docstrings (since 2026-11-16). Any other edit (strings, TOML values) changes the key. For an edit that does not change behaviour, take the adapter's digest with `stickler cache-digests <file>` before it and add it to `src/stickler/digests.yaml` with the change; cached results are then renamed on first use, in the benchmark and in the app. Never list a digest after a real behaviour change.
- Subagents (owner, 2026-11-15): use them where they help, e.g. a fresh-context review of a finished task, independent research, or work that splits into independent parts. That is allowed even when it takes longer, but only when the quality does not suffer: no hand-off of work that needs this conversation's context or decisions, and every subagent result is checked before it is used.
- Check: `scripts/check.sh fast` after changes, `scripts/check.sh task` before every commit (also runs as the pre-commit hook).
- Only open-source models from actively maintained projects; each adapter README states the source (README/paper, version/commit). Check maintenance status and licence on the web before recommending a project, not from memory (e.g. Demucs is maintained in the fork adefossez/demucs). Non-commercial weights are fine; Stickler never ships them.
- Releases are numbered 1, 2, 3 … (+1 per release, no SemVer, ADR 0006); every release counts, fixes included.
- Secrets (`~/.config/stickler/runpod.env`, the Hugging Face token): never `source`, `cat` or print them, never print raw API responses (a RunPod pod response contains the pod's Jupyter password). Check files only by metadata or a silent pattern match, and print only the fields you need (status, IP, port).
