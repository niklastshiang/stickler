#!/usr/bin/env python3
"""Floor-Guard: diff-basierte Prüfung des Floors aus CONSTRAINTS.md.

Python-Portierung der Referenz aus agent-skills/constraint-driven-development
(references/floor-guard.md). Vertrag: Exit 0 = sauber, 1 = Verstoß, 2 = Guard konnte
nicht laufen. Meldet Regel und Fundstelle, nie den Wert eines Secrets.

Aufruf: python scripts/floor_guard.py [--base <ref>]   (Standard: HEAD = uncommittete Arbeit)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass


def git(args: list[str], *, diff_exit: bool = False) -> str | None:
    """Git aufrufen; None bei Fehler. `diff --no-index` endet bei Unterschieden mit 1."""
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode == 0 or (diff_exit and proc.returncode == 1):
        return proc.stdout
    return None


def bail(msg: str) -> None:
    print(f"floor-guard: {msg}", file=sys.stderr)
    sys.exit(2)


@dataclass
class Line:
    file: str
    text: str


SUPPRESSIONS = re.compile(
    r"#\s*noqa|#\s*type:\s*ignore|#\s*pragma:\s*no\s*cover|#\s*ruff:\s*noqa|#\s*pyright:\s*ignore"
    r"|#\s*mypy:\s*ignore|gitleaks:allow"
)
STUBS = re.compile(
    r"raise\s+NotImplementedError|except\b[^:]*:\s*pass\b|\bTODO\b|\bFIXME\b|\bpass\s*#\s*stub"
)
SKIPS = re.compile(r"@pytest\.mark\.(skip|xfail)\b|\bpytest\.skip\(|\bunittest\.skip\b")
# Nur Muster, der Wert wird nie ausgegeben.
SECRETS = re.compile(
    r"\bhf_[A-Za-z0-9]{30,}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|BEGIN [A-Z ]*PRIVATE KEY"
)
BINARIES = re.compile(r"\.(wav|mp3|flac|ogg|ckpt|pth|pt|safetensors|onnx)$", re.IGNORECASE)
EXCEPTION_ROW = re.compile(r"^\| *(W|E)\d+ *\|")

MIN_BEFORE = re.compile(
    r"(>=|>|≥|at least|minimum|\bmin\b|no less than|not fall|not drop|mindestens)\s*$"
)
MAX_BEFORE = re.compile(
    r"(<=|<|≤|at most|maximum|\bmax\b|no more than|under|below|not grow|not exceed|höchstens)\s*$"
)
MIN_AFTER = re.compile(r"^\s*\S*\s*(?:\|\s*)?(or more|or higher|must not fall|must not drop)")
MAX_AFTER = re.compile(r"^\s*\S*\s*(?:\|\s*)?(or less|or lower|must not grow|must not exceed)")


def is_test(path: str) -> bool:
    return bool(re.search(r"(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$", path))


def is_constraints(path: str) -> bool:
    return path.endswith("CONSTRAINTS.md")


def is_guard(path: str) -> bool:
    """Der Guard selbst und seine Tests enthalten die Muster absichtlich."""
    return path.endswith("scripts/floor_guard.py") or path.endswith("tests/test_floor_guard.py")


def rule_key(text: str) -> str | None:
    s = text.strip()
    if s.startswith("|"):
        cells = [c.strip() for c in s.split("|") if c.strip()]
        return cells[0] if cells else ""
    if re.match(r"^[-*] ", s):
        return s[2:].split(":")[0].strip()
    return None


def thresholds(text: str) -> list[tuple[float, str | None]]:
    out: list[tuple[float, str | None]] = []
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        before = text[max(0, m.start() - 24) : m.start()].lower()
        after = text[m.end() : m.end() + 40].lower()
        if MIN_BEFORE.search(before) or MIN_AFTER.search(after):
            direction: str | None = "min"
        elif MAX_BEFORE.search(before) or MAX_AFTER.search(after):
            direction = "max"
        else:
            direction = None
        out.append((float(m.group()), direction))
    return out


def parse_diff(diff: str) -> tuple[list[Line], list[Line], list[str], list[str]]:
    """Unified Diff → hinzugefügte/entfernte Zeilen, gelöschte und neue Dateien."""
    added: list[Line] = []
    removed: list[Line] = []
    deleted: list[str] = []
    created: list[str] = []
    file = old_file = ""
    in_header = False

    def path_of(s: str) -> str:
        return re.sub(r"^[ab]/", "", s)

    for line in diff.split("\n"):
        if line.startswith("diff "):
            in_header = True
        elif line.startswith("@@"):
            in_header = False
        elif in_header:
            if line.startswith("--- "):
                old_file = path_of(line[4:])
            elif line.startswith("+++ "):
                new_file = path_of(line[4:])
                file = old_file if new_file == "/dev/null" else new_file
                if new_file == "/dev/null":
                    deleted.append(file)
                elif old_file == "/dev/null":
                    created.append(file)
        elif line.startswith("+"):
            added.append(Line(file, line[1:]))
        elif line.startswith("-"):
            removed.append(Line(file, line[1:]))
    return added, removed, deleted, created


def check(diff: str) -> list[tuple[str, str, str]]:
    added, removed, deleted, created = parse_diff(diff)
    findings: list[tuple[str, str, str]] = []

    def flag(rule: str, path: str, text: str) -> None:
        findings.append((rule, path, text.strip()[:120]))

    for f in created:
        if BINARIES.search(f):
            flag("binary-in-git", f, "Audio/Gewichte gehören nicht ins Repo")

    for ln in added:
        if is_guard(ln.file):
            continue
        is_doc = ln.file.endswith(".md")  # Doku nennt die Muster, ohne sie anzuwenden
        if SUPPRESSIONS.search(ln.text) and not is_doc:
            flag("silenced-checker", ln.file, ln.text)
        if STUBS.search(ln.text) and not is_doc:
            flag("unfinished-work", ln.file, ln.text)
        if SKIPS.search(ln.text) and not is_doc:
            flag("test-made-easier", ln.file, ln.text)
        if SECRETS.search(ln.text):
            flag("secret", ln.file, "<redacted>")
        if is_constraints(ln.file) and EXCEPTION_ROW.match(ln.text.strip()):
            flag("new-exception", ln.file, ln.text)

    for f in deleted:
        if is_test(f):
            flag("test-deleted", f, "file deleted")
    for ln in removed:
        if (
            is_test(ln.file)
            and ln.file not in deleted
            and re.search(r"\bassert\b|pytest\.raises|approx\(", ln.text)
        ):
            flag("assertion-removed", ln.file, ln.text)

    removed_rules = [r for r in removed if is_constraints(r.file) and rule_key(r.text) is not None]
    added_rules = [a for a in added if is_constraints(a.file) and rule_key(a.text) is not None]
    for r in removed_rules:
        a = next((x for x in added_rules if rule_key(x.text) == rule_key(r.text)), None)
        if a is None:
            if not EXCEPTION_ROW.match(r.text.strip()):
                flag("rule-removed", r.file, r.text)
            continue
        before, after = thresholds(r.text), thresholds(a.text)
        verdict = None
        for direction in ("min", "max", None):
            was = [n for n, d in before if d == direction]
            now = [n for n, d in after if d == direction]
            for i, b in enumerate(was):
                if verdict:
                    break
                if i >= len(now):
                    verdict = "threshold-removed"
                elif now[i] == b:
                    continue
                elif (
                    (direction == "min" and now[i] < b)
                    or (direction == "max" and now[i] > b)
                    or direction is None
                ):
                    verdict = "threshold-loosened" if direction else "threshold-changed"
        if verdict:
            flag(verdict, r.file, f"{r.text}  ->  {a.text}")
    return findings


def collect_diff(base: str) -> str:
    top = git(["rev-parse", "--show-toplevel"])
    if not top:
        bail("not inside a git work tree")
    os.chdir(top.strip())
    merge_base = git(["merge-base", base, "HEAD"])
    if not merge_base:
        bail(f"no merge base against {base}")
    tracked = git(["diff", "--unified=0", merge_base.strip(), "--"])
    if tracked is None:
        bail("could not diff")
    untracked_list = git(["ls-files", "--others", "--exclude-standard"])
    if untracked_list is None:
        bail("could not list untracked files")
    parts = [tracked]
    for f in filter(None, untracked_list.split("\n")):
        d = git(["diff", "--no-index", "--unified=0", "/dev/null", f], diff_exit=True)
        if d is None:
            bail(f"could not diff untracked file {f}")
        parts.append(d)
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD")
    args = parser.parse_args()
    findings = check(collect_diff(args.base))
    if not findings:
        print("floor-guard: clean")
        sys.exit(0)
    print(f"floor-guard: {len(findings)} floor violation(s):", file=sys.stderr)
    for rule, path, text in findings:
        print(f"  [{rule}] {path}: {text}", file=sys.stderr)
    print(
        "\nJeder Fund senkt die Latte. Code reparieren oder eine eingetragene Exception nutzen.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
