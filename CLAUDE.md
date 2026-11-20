# Stickler

Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.

- Specification: SPEC.md (living document; when a decision changes, update SPEC.md first)
- Plan and tasks: tasks/plan.md, tasks/todo.md
- Decisions: docs/adr/
- Everything in English: code, comments, docstrings, messages, documentation and commit messages (since 2026-11-12). Talk to the user in German.
- Adapter cache keys hash `run.py`, `setup.py`, the adapter's modules they import, `pyproject.toml`, `uv.lock`, `.python-version` and `adapters/_common`, without comments and docstrings (since 2026-11-16). Any other edit (strings, TOML values, a relock) changes the key. For an edit that does not change behaviour, take the digest with `stickler cache-digests <file>` before and after it and add the pair `{from, to}` to `src/stickler/digests.yaml` in the same commit; cached results are then renamed on first use, in the benchmark and in the app. Never add a pair after a real behaviour change.
- Usage per device (owner, 2026-11-20): every computer that works on Stickler records its Claude Code tokens and active time into the repository: `uv run python scripts/ai_usage.py --record <device>` (a short name of one's own, never the host's), at the end of every working session that commits and before every release, and the file `docs/usage/<device>.json` goes into that commit. `--summary` adds up every device; the README's AI figures and badges come from that sum, not from one machine's logs.
- Subagents (owner, 2026-11-15): use them where they help, e.g. a fresh-context review of a finished task, independent research, or work that splits into independent parts. That is allowed even when it takes longer, but only when the quality does not suffer: no hand-off of work that needs this conversation's context or decisions, and every subagent result is checked before it is used.
- Check: `scripts/check.sh fast` after changes, `scripts/check.sh task` before every commit (also runs as the pre-commit hook).
- Only open-source models from actively maintained projects; each adapter README states the source (README/paper, version/commit). Check maintenance status and licence on the web before recommending a project, not from memory (e.g. Demucs is maintained in the fork adefossez/demucs). Non-commercial weights are fine; Stickler never ships them.
- Releases are numbered 1, 2, 3 … (+1 per release, no SemVer, ADR 0006); every release counts, fixes included.
- Secrets (`~/.config/stickler/runpod.env`, the Hugging Face token): never `source`, `cat` or print them, never print raw API responses (a RunPod pod response contains the pod's Jupyter password). Check files only by metadata or a silent pattern match, and print only the fields you need (status, IP, port).
