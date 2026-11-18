#!/usr/bin/env python3
"""Line coverage of a Swift package's own sources (CONSTRAINTS.md "Swift coverage").

Reads the llvm-cov JSON that `swift test --enable-code-coverage` writes (its path from `swift
test --show-codecov-path`) and counts only files under the package's `Sources/`: tests and
dependencies do not count. Exit 0 at or above the minimum, 1 below it, 2 when the report cannot
be read.

Usage: python scripts/swift_coverage.py <codecov.json> <package dir> [--minimum 95]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def coverage(report: dict, sources: Path) -> tuple[int, int, list[tuple[str, int, int]]]:
    """(covered lines, lines, per file) for the files under `sources`."""
    prefix = str(sources.resolve()) + "/"
    per_file = []
    for entry in report["data"][0]["files"]:
        name = entry["filename"]
        if name.startswith(prefix):
            lines = entry["summary"]["lines"]
            per_file.append((name.removeprefix(prefix), lines["covered"], lines["count"]))
    covered = sum(c for _, c, _ in per_file)
    total = sum(n for _, _, n in per_file)
    return covered, total, sorted(per_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("package", type=Path)
    parser.add_argument("--minimum", type=float, default=95.0)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        covered, total, per_file = coverage(report, args.package / "Sources")
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"swift-coverage: cannot read {args.report}: {exc}", file=sys.stderr)
        return 2
    if total == 0:
        print(f"swift-coverage: no source lines under {args.package / 'Sources'}", file=sys.stderr)
        return 2
    for name, c, n in per_file:
        print(f"{name:<60} {c:>5}/{n:<5} {100 * c / n if n else 100:6.1f} %")
    percent = 100 * covered / total
    print(f"TOTAL {covered}/{total} lines, {percent:.2f} % (minimum {args.minimum:g} %)")
    return 0 if percent >= args.minimum else 1


if __name__ == "__main__":
    sys.exit(main())
