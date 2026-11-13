"""Renders the README badges with shieldcn.dev into docs/badges/*.svg.

The SVGs live in the repository, so the README does not depend on the service being up.
Each row is a rainbow: every badge's gradient starts where the previous one ends. Hues run from
the project's orange over pink, violet and blue to cyan; yellow and green are left out because
white text is hard to read on them. Test count and coverage are measured by running the tests.

    uv run python scripts/badges.py          # after changes that move the numbers
"""

from __future__ import annotations

import colorsys
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "badges"
SERVICE = "https://shieldcn.dev/badge"
USER_AGENT = "stickler-badges (+https://github.com/niklastshiang/stickler)"
STYLE = {"font": "jetbrains-mono", "split": "true"}
# Hue path in degrees: orange → red → pink → violet → blue → cyan (no yellow/green)
HUE_START, HUE_END = 30.0, -170.0


def facts() -> dict[str, str]:
    """Version from pyproject.toml, tests and coverage from a test run."""
    version = re.search(r'^version = "(\d+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    run = subprocess.run(
        ["uv", "run", "pytest", "-q", "--cov", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    passed = re.search(r"(\d+) passed", run.stdout)
    total = re.search(r"^TOTAL\s.*?(\d+)%", run.stdout, re.M)
    smoke = subprocess.run(
        ["uv", "run", "pytest", "-q", "-m", "adapters", "--collect-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    collected = re.search(r"(\d+)/\d+ tests collected", smoke.stdout)
    if not (version and passed and total and collected):
        sys.exit("could not read version, tests or coverage")
    return {
        "version": version.group(1),
        "tests": passed.group(1),
        "coverage": total.group(1),
        "smoke": collected.group(1),
    }


def rows(f: dict[str, str]) -> dict[str, list[tuple[str, str, str]]]:
    """(file name, label, message) per row; the joke row shimmers."""
    return {
        "facts": [
            ("license", "license", "MIT"),
            ("python", "python", "3.12"),
            ("uv", "environments", "uv"),
            ("models", "models", "7 adapters"),
            ("tests", "tests", f"{f['tests']} + {f['smoke']} smoke"),
            ("coverage", "coverage", f"{f['coverage']}%"),
            ("version", "version", f["version"]),
            ("local", "runs", "100% local"),
        ],
        "fun": [
            ("cloud", "cloud", "0 bytes"),
            ("subscription", "subscription", "€0"),
            ("rocket-science", "rocket science", "no"),
            ("drummer", "drummer", "beginner"),
            ("burgers", "burgers received", "0"),
            ("neighbours", "neighbours", "annoyed"),
            ("jazz", "jazz", "it's complicated"),
        ],
        "origin": [
            ("built-with", "built with", "Claude Code"),
            ("code", "code", "100% AI"),
            ("decisions", "decisions", "100% human"),
        ],
    }


def hex_at(hue: float) -> str:
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360, 0.5, 0.85)
    return f"{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def url(label: str, message: str, start: float, end: float, shimmer: bool) -> str:
    def part(text: str) -> str:  # shields syntax: "-" → "--", "_" → "__", then URL-encode
        return urllib.parse.quote(text.replace("-", "--").replace("_", "__"), safe="")

    query = {**STYLE, "gradient": f"{hex_at(start)},{hex_at(end)},90"}
    if shimmer:
        query["animate"] = "shimmer"
    return f"{SERVICE}/{part(label)}-{part(message)}-{hex_at(start)}.svg?" + urllib.parse.urlencode(
        query
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, badges in rows(facts()).items():
        step = (HUE_END - HUE_START) / len(badges)
        for i, (file, label, message) in enumerate(badges):
            start = HUE_START + i * step
            link = url(label, message, start, start + step, shimmer=name == "fun")
            request = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                svg = response.read()
            if not svg.lstrip().startswith(b"<svg"):
                sys.exit(f"{file}: no SVG returned")
            (OUT / f"{name}-{file}.svg").write_bytes(svg)
            print(f"{name}-{file}.svg  {label}: {message}")


if __name__ == "__main__":
    main()
