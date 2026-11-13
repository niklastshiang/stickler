# ADR 0006: Sequential version numbers instead of SemVer

- Status: accepted
- Date: 2026-11-12

## Context
Stickler is a private tool with no external users who rely on API compatibility.
Distinguishing major, minor and patch brings no benefit here. The project owner wants plain release numbers that increase by one with every release, similar to Firefox.

## Decision
- **Format:** The version is an integer. `0` stands for the state before the first release; then `1`, `2`, `3` and so on follow.
- **Release steps:**
  0. Go through the open Dependabot alerts (added 2026-11-13; an alert in a local tool is often not exploitable, but it needs a decision).
  1. Increase the version in `pyproject.toml` and `src/stickler/__init__.py` by one.
  2. Create the commit "Release N".
  3. Set the Git tag `vN` and upload it with `git push --tags`.
- **Compatibility:** A single integer is PEP 440-compliant; `uv` and `importlib.metadata` handle it.
- **Adapters:** The versions in the adapter `pyproject.toml` files (`package = false`) are not published and remain untouched. What matters is the respective model (version or commit), documented in `meta.json` and in the adapter's README.

## Consequences
- The version jump does not show whether a release is incompatible. What changed is stated in the release description.
- A test checks that the version is an integer and that the package and `pyproject.toml` match.
