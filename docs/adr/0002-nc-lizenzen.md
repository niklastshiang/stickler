# ADR 0002: Model weights under non-commercial licenses are allowed

- Status: accepted
- Date: 2026-11-11

## Context
Some of the strongest open drum and multi-instrument transcribers have open code, but their weights are under non-commercial licenses:
- ADTOF: CC BY-NC-SA 4.0
- MuScriptor: code MIT, weights CC BY-NC 4.0, download on Hugging Face only after accepting the license

Stickler is used exclusively privately.

## Decision
NC-licensed weights may be included in the benchmark if code and weights are publicly accessible. Closed-source services and proprietary APIs remain excluded.

## Consequences
- Every adapter README names the license of the code **and** of the weights.
- The report marks NC models, so that if Stickler is later used commercially (e.g. a published GTK app), it is clear which pipelines would drop out.
- Weights are never checked into the repository (CONSTRAINTS.md).
