#!/usr/bin/env python3
"""Checks the PDF the Windows app saved on the runner (SPEC.md, module `win-sheet`, scope 7):
the number of pages, each A4 (595 × 842 points, give or take one), and the title when the PDF
names one (whether WebView2 takes it from the page's <title> is unconfirmed: a missing title
is reported, not failed).

Usage: uv run python scripts/check_pdf.py <file.pdf> --pages N [--title TEXT]"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path

A4 = (595.28, 841.89)

PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
MEDIA_BOX = re.compile(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]")
TITLE = re.compile(rb"/Title\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)")
STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)


def _readable(data: bytes) -> bytes:
    """The file with its compressed streams opened, so dictionaries kept in object streams
    are found too."""
    parts = [data]
    for raw in STREAM.findall(data):
        try:
            parts.append(zlib.decompress(raw))
        except zlib.error:
            continue
    return b"\n".join(parts)


def _text(token: bytes) -> str:
    """A PDF string, literal or hex, in PDFDocEncoding or UTF-16 with its byte order mark."""
    if token.startswith(b"<"):
        raw = bytes.fromhex(re.sub(rb"\s", b"", token[1:-1]).decode("ascii"))
    else:
        raw = re.sub(rb"\\(.)", lambda m: m.group(1), token[1:-1])
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be")
    return raw.decode("latin-1")


def inspect(data: bytes) -> tuple[int, list[tuple[float, float]], str | None]:
    """Pages, their sizes in points and the title (None when there is none)."""
    text = _readable(data)
    boxes = [
        (float(x1) - float(x0), float(y1) - float(y0)) for x0, y0, x1, y1 in MEDIA_BOX.findall(text)
    ]
    title = TITLE.search(text)
    return len(PAGE.findall(text)), boxes, _text(title.group(1)) if title else None


def problems(path: Path, pages: int, title: str | None) -> list[str]:
    """What is wrong with the PDF; empty when it is right."""
    if not path.is_file() or not path.read_bytes().startswith(b"%PDF-"):
        return [f"{path} is no PDF"]
    found, boxes, named = inspect(path.read_bytes())
    wrong = []
    if found != pages:
        wrong.append(f"{found} pages, not {pages}")
    for width, height in boxes:
        if abs(width - A4[0]) > 1 or abs(height - A4[1]) > 1:
            wrong.append(f"a page of {width:g} × {height:g} points, not A4")
            break
    if not boxes:
        wrong.append("no page size")
    if title is not None and named is not None and named != title:
        wrong.append(f"the title is {named!r}, not {title!r}")
    return wrong


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", type=int, required=True)
    parser.add_argument("--title")
    args = parser.parse_args(argv)
    wrong = problems(args.pdf, args.pages, args.title)
    for line in wrong:
        print(f"{args.pdf}: {line}", file=sys.stderr)
    if not wrong:
        _, _, named = inspect(args.pdf.read_bytes())
        print(f"{args.pdf}: {args.pages} A4 pages, title {named!r}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
