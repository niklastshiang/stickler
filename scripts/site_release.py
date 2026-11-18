#!/usr/bin/env python3
"""Fills the website's download cards from a release (SPEC.md "Website").

The pages in site/ link every download to the newest release's page and hold no version; this
copies site/ and points each card at its file in the given release, with the file's size and
name. A package the release does not have keeps its link to the release page (and a warning).

Usage: python scripts/site_release.py <release.json> <site dir> <out dir>
       release.json is `gh release view <tag> --json tagName,assets`; <out dir> must not exist.
Exit 0 when the copy is written, 2 when the release cannot be read or <out dir> exists.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

KINDS = {  # a card's data-asset → how its file's name ends
    "dmg": ".dmg",
    "flatpak": ".flatpak",
    "appimage": "-x86_64.AppImage",
}


def size_text(size: int, *, decimal: str = ".") -> str:
    """Decimal units, as the app's own sizes: 33 MB, 134 MB, 1.2 GB."""
    if size >= 1_000_000_000:
        return f"{size / 1e9:.1f} GB".replace(".", decimal)
    return f"{round(size / 1e6)} MB"


def packages(release: dict) -> dict[str, dict]:
    found = {}
    for asset in release["assets"]:
        for kind, ending in KINDS.items():
            if asset["name"].endswith(ending):
                found[kind] = asset
    return found


def fill(html: str, found: dict[str, dict]) -> str:
    german = re.search(r'<html lang="de"', html) is not None
    for kind, asset in found.items():
        html = re.sub(
            rf'(data-asset="{kind}"\s+href=")[^"]*(")', rf"\g<1>{asset['url']}\g<2>", html
        )
        size = size_text(asset["size"], decimal="," if german else ".")
        html = re.sub(rf'(<span data-size="{kind}">)[^<]*(</span>)', rf"\g<1>{size}\g<2>", html)
        html = re.sub(
            rf'(<span data-name="{kind}">)[^<]*(</span>)', rf"\g<1>{asset['name']}\g<2>", html
        )
    return html


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    release_file, site, out = (Path(a) for a in args)
    try:
        release = json.loads(release_file.read_text(encoding="utf-8"))
        found = packages(release)
        tag = release["tagName"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"site-release: cannot read {release_file}: {exc}", file=sys.stderr)
        return 2
    if out.exists():
        print(f"site-release: {out} exists; choose a new folder", file=sys.stderr)
        return 2
    for kind in KINDS:
        if kind not in found:
            print(
                f"site-release: no {kind} in {tag}; its card links to the release page",
                file=sys.stderr,
            )
    shutil.copytree(site, out)
    for page in out.rglob("*.html"):
        page.write_text(fill(page.read_text(encoding="utf-8"), found), encoding="utf-8")
    print(f"site-release: {out} names the files of {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
