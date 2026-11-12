# ADR 0001: Demucs via the maintained fork adefossez/demucs

- Status: accepted
- Date: 2026-11-11

## Context
The original repository `facebookresearch/demucs` has been archived since January 1, 2025 and is read-only. Alexandre Défossez, the main author, has since maintained the fork `github.com/adefossez/demucs` and describes it as the officially maintained version. According to his note, no new features are planned. Two requirements apply to Stickler: open source only, and actively maintained projects only.

## Decision
The separator adapter `demucs` installs Demucs from `adefossez/demucs`, pinned to a commit or release. The archived meta repo and third-party PyPI packages (e.g. `demucs-infer`, `demucs-torchcodec`) are not used.

## Consequences
- Compatibility fixes (new PyTorch versions, torchaudio → torchcodec) come from the fork.
- Demucs is the baseline for comparison alongside newer separators (BS-/Mel-RoFormer), not a fixed choice.
- If the fork breaks with ROCm wheels, this is documented in the adapter README and, if necessary, only the CPU is used.

## Sources
- https://github.com/facebookresearch/demucs (archive notice)
- https://github.com/adefossez/demucs
