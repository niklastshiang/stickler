#!/usr/bin/env python3
"""Line coverage of the Mac app's logic outside views (CONSTRAINTS.md "Swift coverage", task
117).

The app target mixes SwiftUI views with the logic around AppKit's panels in the same files, so
this counts functions, not files: every function of a logic type (LOGIC), closures in them
included. Views and `SystemAsking`/`RemovalQuestion` (AppKit only, every decision made by their
callers) are left out, as `stickler_gtk/ui/` is in Python.

Usage: xcrun xccov view --report --json test.xcresult > report.json
       python scripts/xccov_gate.py report.json [--minimum 95]
Exit 0 at or above the minimum, 1 below it, 2 when the report has no app or no logic in it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

APP = "Stickler.app"
LOGIC = (
    "Exports",
    "Removal",
    "Panels",
    "SheetPDF",
    "PageLoad",
    "SheetHTML",
    "ZoomMenu",
    "Backups",
    "Uninstalling",
    "Player",
)


def coverage(report: dict, types: tuple[str, ...]) -> tuple[int, int, list[tuple[str, int, int]]]:
    """(covered lines, lines, per function) for the app's functions of `types`."""
    owner = re.compile(r"(?:^|[\s(])(?:" + "|".join(map(re.escape, types)) + r")\.")
    rows = []
    for target in report["targets"]:
        if target["name"] != APP:
            continue
        for file in target["files"]:
            for function in file["functions"]:
                if owner.search(function["name"]):
                    rows.append(
                        (function["name"], function["coveredLines"], function["executableLines"])
                    )
    rows.sort()
    return sum(c for _, c, _ in rows), sum(n for _, _, n in rows), rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--minimum", type=float, default=95.0)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        covered, total, rows = coverage(report, LOGIC)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"xccov-gate: cannot read {args.report}: {exc}", file=sys.stderr)
        return 2
    if total == 0:
        print(f"xccov-gate: no logic of {APP} in {args.report}", file=sys.stderr)
        return 2
    for name, c, n in rows:
        print(f"{name:<70} {c:>4}/{n:<4} {100 * c / n if n else 100:6.1f} %")
    percent = 100 * covered / total
    print(f"TOTAL {covered}/{total} lines, {percent:.2f} % (minimum {args.minimum:g} %)")
    return 0 if percent >= args.minimum else 1


if __name__ == "__main__":
    sys.exit(main())
