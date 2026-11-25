"""Renders the README badges with shieldcn.dev into docs/badges/*.svg.

The SVGs live in the repository, so the README does not depend on the service being up.
Each row is a rainbow: every badge's gradient starts where the previous one ends; the two rows at
the top (facts, then the shimmering burger) share one rainbow, so the second row goes on where
the first stops. Hues run from
the project's orange over pink, violet and blue to cyan; yellow and green are left out because
white text is hard to read on them. Test count and coverage are measured by running the tests.
The value (second half) is set bold: shieldcn has no font weight, so the value's glyph path
gets a white outline of its own (owner's wish: easier to read, and without shieldcn's split the
badges need less room).

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
STYLE = {"font": "jetbrains-mono", "split": "false"}
# shieldcn draws the text as two white paths: the label (slightly transparent) and the value
VALUE_PATH = '<path fill="#fff" d='
BOLD = 'stroke="#fff" stroke-width="0.8" stroke-linejoin="round" '

# Hue path in degrees: orange → red → pink → violet → blue → cyan (no yellow/green)
HUE_START, HUE_END = 30.0, -170.0


def facts() -> dict[str, str]:
    """Version from pyproject.toml, tests and coverage from a test run."""
    version = re.search(
        r'^version = "(\d+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M
    )
    run = subprocess.run(
        ["uv", "run", "pytest", "-q", "--cov", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    passed = re.search(r"(\d+) passed", run.stdout)
    total = re.search(r"^TOTAL\s.*?(\d+)%", run.stdout, re.M)
    smoke = subprocess.run(
        ["uv", "run", "pytest", "-q", "-m", "adapters", "--collect-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    collected = re.search(r"(\d+)/\d+ tests collected", smoke.stdout)
    if not (version and passed and total and collected):
        sys.exit("could not read version, tests or coverage")
    return {
        "version": version.group(1),
        "tests": passed.group(1),
        "coverage": total.group(1),
        "smoke": collected.group(1),
        **ai_figures(),
    }


def ai_figures() -> dict[str, str]:
    """What building Stickler with Claude Code cost, summed over every device's record in
    docs/usage/ (scripts/ai_usage.py --record), not one machine's logs."""
    import ai_usage  # next to this script

    _rows, total = ai_usage.summary()
    return {
        "ai_cost": f"≈ {total['cost']:,.0f} USD",
        "ai_tokens": f"{total['tokens'] / 1e6:,.0f} M",
    }


def rows(f: dict[str, str]) -> dict[str, list[tuple[str, str, str]]]:
    """(file name, label, message) per row; the joke row shimmers."""
    return {
        "facts": [
            ("license", "license", "GPL-3.0"),
            ("python", "python", "3.12 · 3.15"),
            ("coverage", "coverage", f"{f['coverage']}%"),
            ("version", "version", f["version"]),
            ("local", "runs", "100% local"),
        ],
        "fun": [
            ("burgers", "burgers received", "0"),
        ],
        "origin": [
            ("built-with", "built with", "Claude Code"),
            ("code", "code", "100% AI"),
            ("decisions", "decisions", "100% human"),
            ("ai-cost", "AI cost", f["ai_cost"]),  # at API prices, see README > ORIGIN
            ("tokens", "tokens", f["ai_tokens"]),
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


def bold_value(svg: bytes, file: str) -> bytes:
    """Sets the value bold by outlining its glyph path."""
    text = svg.decode("utf-8")
    if text.count(VALUE_PATH) != 1:
        sys.exit(f"{file}: shieldcn's SVG changed, the value path was not found exactly once")
    return text.replace(VALUE_PATH, VALUE_PATH.replace("d=", BOLD + "d=")).encode("utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows = rows(facts())
    top = len(all_rows["facts"]) + len(all_rows["fun"])  # one rainbow over the two top rows
    for name, badges in all_rows.items():
        count, offset = (
            (top, len(all_rows["facts"]) if name == "fun" else 0)
            if name
            in (
                "facts",
                "fun",
            )
            else (len(badges), 0)
        )
        step = (HUE_END - HUE_START) / count
        for i, (file, label, message) in enumerate(badges):
            start = HUE_START + (offset + i) * step
            link = url(label, message, start, start + step, shimmer=name == "fun")
            request = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                svg = response.read()
            if not svg.lstrip().startswith(b"<svg"):
                sys.exit(f"{file}: no SVG returned")
            (OUT / f"{name}-{file}.svg").write_bytes(bold_value(svg, file))
            print(f"{name}-{file}.svg  {label}: {message}")


if __name__ == "__main__":
    main()
