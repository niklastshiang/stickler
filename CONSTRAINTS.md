# Constraints

Last reviewed: 2026-11-12 by the project owner (interview: no further dimensions, violations block; coverage raised from 80% to 95% on 2026-11-12)

Applies to the harness (`src/stickler/`, `tests/`, `scripts/`), the GTK application (`src/stickler_gtk/`, from 2026-11-14), the Mac app (`mac/`) and the Windows app (`win/`). Adapters under `adapters/` are thin wrappers around third-party model code. The floor and lint apply to them, but no coverage limit.

## Floor (always enforced, no setup required)

- No new suppression comments: `# noqa`, `# type: ignore`, `# pragma: no cover`, `# ruff: noqa`
- Swift (`mac/`, from 2026-11-18): no `swiftlint:disable` or other `// swiftlint:` comments; no placeholder `fatalError()` / `preconditionFailure()` (empty, "TODO", "not implemented"); no `XCTSkip` or `@Test(.disabled…)` without a reason in the commit message
- C# (`win/`, from 2026-11-25): no `#pragma warning disable`, `[SuppressMessage]`, `[ExcludeFromCodeCoverage]`, `<NoWarn>` or `.editorconfig` severities lowered to `none`/`silent`; no `NotImplementedException`; no `[Ignore]` or `Assert.Inconclusive` without a reason in the commit message
- No unimplemented stubs: `raise NotImplementedError`, `except …: pass`, `TODO` instead of an implementation
- No skipped or deleted tests without a reason in the commit message: `@pytest.mark.skip`, `pytest.skip(` …
- No secrets in source: Hugging Face tokens (`hf_…`) only come via `HF_TOKEN` or `hf auth login`
- No audio, datasets or model weights in git: `.wav/.mp3/.flac/.ckpt/.pth/.safetensors` are in `.gitignore`
- This file does not get weakened to make a change pass

Checked by `uv run python scripts/floor_guard.py` (diff-based, exit 0 clean / 1 violation / 2 guard could not run). It is a Python port of the reference from `agent-skills/constraint-driven-development`.

## Enforced with numbers

| Dimension | Rule | Checked by | Runs at |
|-----------|------|-----------|---------|
| Lint | Zero errors from our ruff config | `uv run ruff check .` | every edit, CI |
| Format | Zero files needing reformat | `uv run ruff format --check .` | every edit, CI |
| Floor | Zero floor violations in the diff | `uv run python scripts/floor_guard.py` (CI: `--base` = the state before the push) | every edit, CI |
| Tests | All tests pass | `uv run pytest -q` | task end, pre-commit, CI |
| Coverage | `src/stickler`, `src/stickler_app` and `src/stickler_gtk` line coverage >= 95% (excluding `cli.py`, `stickler_gtk/main.py` and `stickler_gtk/ui/`) | `uv run pytest -q --cov --cov-fail-under=95` | task end, pre-commit, CI |
| Swift lint | Zero SwiftLint findings with `--strict` (config `.swiftlint.yml`, SwiftLint pinned in CI) | `swiftlint --strict` | CI (`.github/workflows/mac.yml`) |
| Swift tests | All XCTest and Swift Testing tests pass, `SticklerCore` on Linux and macOS | `swift test`, `xcodebuild test` | CI (`.github/workflows/mac.yml`) |
| Swift coverage | `SticklerCore` and the app's models line coverage >= 95% (pure SwiftUI views excluded, as `stickler_gtk/ui/`); in the app target, the functions of its logic types (`Exports`, `Removal`, `Panels`, `SheetPDF`, `PageLoad`, `SheetHTML`, `ZoomMenu`, `Backups`, `Uninstalling`, `Player`, `ControlsMenu`, `CorrectionsMenu`) >= 95%, the AppKit-only `SystemAsking` and `RemovalQuestion` excluded | `scripts/swift_coverage.py`, `scripts/xccov_gate.py` | CI (`.github/workflows/mac.yml`) |
| C# build | Zero warnings: `TreatWarningsAsErrors`, `AnalysisLevel=latest-recommended`, `EnforceCodeStyleInBuild`, `Nullable=enable` (`win/Directory.Build.props`) | `dotnet build win/Stickler.sln` | CI (`.github/workflows/win.yml`), on the owner's PC |
| C# format | Zero files needing reformat | `dotnet format win/Stickler.sln --verify-no-changes` | CI (`.github/workflows/win.yml`) |
| C# tests | All MSTest tests pass, `SticklerCore` on Linux and Windows | `dotnet test` | CI (`.github/workflows/win.yml`) |
| C# coverage | `SticklerCore` and the app's logic types line coverage >= 95% (pure XAML views and their code-behind excluded, as `stickler_gtk/ui/`) | `scripts/cobertura_gate.py` | CI (`.github/workflows/win.yml`) |
| GTK boundary | No `gi` import in `src/stickler` or `src/stickler_app`; `stickler_app` imports no `stickler_gtk`, `stickler` neither app package | `tests/gtk/test_boundaries.py` | task end, pre-commit, CI |
| Secrets | No secrets anywhere in the git history | `gitleaks git . --redact --no-banner` | CI (`.github/workflows/check.yml`) |

Reasons:
- **80% fixed:** The project started from zero, so the number was reachable for new code from the beginning. It forces tests for the scoring logic, on which the meaningfulness of the whole benchmark depends.
- **Raised to 95% (2026-11-12):** At the project owner's request, at a level of 97.5%. The margin to 100% leaves room for paths that only run with a real GPU or real models.
- **Violations block:** The git hook `.githooks/pre-commit` runs `scripts/check.sh task`. A red check prevents the commit.
- **CI (2026-11-13):** `.github/workflows/check.yml` runs the same checks on every push to main and every pull request, plus gitleaks over the whole history as a check that does not depend on our own tests.
- **GTK application (2026-11-14, approved with the `app-shell` spec):** the app's decisions live in `stickler_gtk/logic`, which imports no GTK and counts for coverage like the harness; `stickler_gtk/ui` and `main.py` only show what the logic decides and are excluded like `cli.py`. Widget smoke tests need a display and run with `scripts/gtk.sh test`, not in CI.
- **Shared app logic (2026-11-17, approved with the `shared-core` spec):** `stickler_gtk/logic` moved to `stickler_app`, shared by the GTK app and the Mac app; the same rules apply to it (no GTK, counted for coverage), and it may depend on neither app.
- **Swift (2026-11-18, approved with the `mac-shell` spec):** the same bar as Python (SPEC.md "Release 8"). No one here has Xcode, so the Swift checks run in CI on every push; `SticklerCore` also builds and tests on Linux (`swift test` in `mac/SticklerCore`), so most of it is checked before a push.
- **C# (2026-11-25, with the `win-shell` spec):** the same bar as Swift (SPEC.md "Release 11"). The owner's Windows PC has the .NET SDK (no Visual Studio), so `SticklerCore` is built and tested there and in WSL before a push; the WinUI app is checked on GitHub's Windows runner on every push.
- **Time budget:** `scripts/check.sh fast` < 5 s, `scripts/check.sh task` < 90 s. Slow model tests (`pytest -m adapters`) are not part of the default run and run for tasks that concern adapters.

## Measured, not yet enforced

| Metric | Today | Direction |
|--------|-------|-----------|
| – | – | – |

## Exceptions

| ID | Rule | Path | Reason | Owner | Expires |
|----|------|------|--------|-------|---------|
