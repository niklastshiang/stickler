"""The C# coverage gate (CONSTRAINTS.md, "C# coverage"; SPEC.md, module `win-shell`).

Reads the Cobertura file Microsoft.Testing.Platform's code coverage writes and checks the line
coverage of the files it is told to count: `SticklerCore` and the app's logic types, not the
pure XAML views. Prints each counted file's coverage and, with `--show`, the lines no test ran.

    uv run python scripts/cobertura_gate.py coverage.cobertura.xml --include "win/SticklerCore/*.cs"
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MINIMUM = 95.0


def lines_by_file(cobertura: str) -> dict[str, dict[int, bool]]:
    """Each source file (with `/`) and whether each of its lines ran; a line that several
    classes or methods share counts as run when any of them ran it."""
    root = ET.fromstring(cobertura)
    sources = [(s.text or "").replace("\\", "/").rstrip("/") for s in root.iter("source")]
    out: dict[str, dict[int, bool]] = {}
    for cls in root.iter("class"):
        name = cls.get("filename", "").replace("\\", "/")
        # read as text, not as this system's paths: a Windows report is read on Linux too
        absolute = name.startswith("/") or re.match(r"^[A-Za-z]:/", name)
        path = name if absolute or not sources else f"{sources[0]}/{name}"
        seen = out.setdefault(path, {})
        for line in cls.iter("line"):
            number = int(line.get("number", "0"))
            seen[number] = seen.get(number, False) or int(line.get("hits", "0")) > 0
    return out


def counted(
    files: dict[str, dict[int, bool]], include: list[str], exclude: list[str]
) -> dict[str, dict[int, bool]]:
    def matches(path: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatch(path, f"*{pattern}") for pattern in patterns)

    return {
        p: lines for p, lines in files.items() if matches(p, include) and not matches(p, exclude)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cobertura", type=Path)
    parser.add_argument(
        "--include", action="append", required=True, help="a glob, e.g. win/SticklerCore/*.cs"
    )
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--minimum", type=float, default=MINIMUM)
    parser.add_argument("--show", action="store_true", help="print the lines no test ran")
    args = parser.parse_args(argv)
    files = counted(
        lines_by_file(args.cobertura.read_text(encoding="utf-8")), args.include, args.exclude
    )
    if not files:
        print("cobertura-gate: no file matches --include", file=sys.stderr)
        return 2
    total = sum(len(lines) for lines in files.values())
    ran = sum(sum(lines.values()) for lines in files.values())
    for path, lines in sorted(files.items()):
        missed = sorted(n for n, hit in lines.items() if not hit)
        share = 100.0 * (len(lines) - len(missed)) / len(lines) if lines else 100.0
        note = f"  missed: {', '.join(map(str, missed))}" if args.show and missed else ""
        print(f"{share:6.1f} %  {path}{note}")
    share = 100.0 * ran / total if total else 100.0
    print(f"{share:6.1f} %  total ({ran} of {total} lines), minimum {args.minimum:.0f} %")
    return 0 if share >= args.minimum else 1


if __name__ == "__main__":
    sys.exit(main())
