"""Compares what two uv.lock files resolve for Linux (SPEC.md, module `mac-core`).

Widening an adapter's platforms (macOS, later Windows) relocks it; its results stay valid on
Linux only if Linux gets exactly the same packages. This lists every package reachable on Linux
from the lock's root, with its version, source, sdist hash and the hashes of its Linux and
pure-Python wheels, and prints what differs between the two locks.

Reachability follows the dependencies' markers. A marker is taken as false on Linux only when
each of its `or` clauses names another platform (`sys_platform == 'darwin'`, …); anything less
clear counts as Linux, so the script errs towards reporting a difference.

    uv run python scripts/lock_platforms.py before.lock after.lock   # exit 1 on a difference
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

OTHER_PLATFORM = re.compile(
    r"sys_platform\s*==\s*'(darwin|win32|cygwin)'|platform_system\s*==\s*'(Darwin|Windows)'"
)


def false_on_linux(marker: str | None) -> bool:
    """True only when every `or` clause of the marker names another platform."""
    if not marker:
        return False
    return all(OTHER_PLATFORM.search(clause) for clause in marker.split(" or "))


def _applies(entry: dict) -> bool:
    markers = entry.get("resolution-markers")
    return not markers or not all(false_on_linux(m) for m in markers)


def _linux_wheel(url: str) -> bool:
    platform = Path(url).name.removesuffix(".whl").split("-")[-1]
    return platform == "any" or "linux" in platform


def view(text: str) -> dict[tuple[str, str], tuple]:
    """(name, version) → (source, sdist hash, Linux and pure-Python wheel hashes) of every
    package reachable on Linux."""
    packages = tomllib.loads(text).get("package", [])
    by_name: dict[str, list[dict]] = {}
    for entry in packages:
        by_name.setdefault(entry["name"], []).append(entry)
    roots = [e for e in packages if {"virtual", "editable"} & set(e.get("source", {}))]
    todo = [e for e in roots if _applies(e)]
    seen: dict[tuple[str, str], dict] = {}
    while todo:
        entry = todo.pop()
        key = (entry["name"], entry["version"])
        if key in seen:
            continue
        seen[key] = entry
        deps = list(entry.get("dependencies", []))
        for extras in entry.get("optional-dependencies", {}).values():
            deps.extend(extras)
        for dep in deps:
            if false_on_linux(dep.get("marker")):
                continue
            for target in by_name.get(dep["name"], []):
                if "version" in dep and target["version"] != dep["version"]:
                    continue
                if _applies(target):
                    todo.append(target)
    return {
        key: (
            str(sorted(e.get("source", {}).items())),
            e.get("sdist", {}).get("hash"),
            tuple(sorted(w["hash"] for w in e.get("wheels", []) if _linux_wheel(w["url"]))),
        )
        for key, e in seen.items()
    }


def compare(before: str, after: str) -> list[str]:
    """Lines describing what Linux gets differently from `after` than from `before`."""
    old, new = view(before), view(after)
    lines = [f"- {n} {v}" for n, v in sorted(old.keys() - new.keys())]
    lines += [f"+ {n} {v}" for n, v in sorted(new.keys() - old.keys())]
    lines += [f"~ {n} {v}" for n, v in sorted(old.keys() & new.keys()) if old[n, v] != new[n, v]]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    before = args.before.read_text(encoding="utf-8")
    lines = compare(before, args.after.read_text(encoding="utf-8"))
    for line in lines:
        print(line)
    print(f"Linux: {len(view(before))} packages, {len(lines)} differences")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
