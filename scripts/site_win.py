"""The Windows app's pictures for the website's "A look around" (SPEC.md "Website", "Change
2026-11-27"): checks the eight pictures taken in the Windows test VM and puts them into
site/images/ as win-*.png with their WebP, as scripts/site_mac.py does for the Mac's.

    uv run python scripts/site_win.py take <folder with win-*.png>
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import site_mac

SHOTS = ("empty", "analysing", "sheet", "corrections")
SIZE = (1000, 700)


def names() -> list[str]:
    return [f"win-{shot}{look}.png" for shot in SHOTS for look in ("", "-dark")]


def take(folder: Path, images: Path = site_mac.IMAGES) -> list[Path]:
    """The pictures of `folder`, checked (all there, each 1000 × 700) and copied into `images`."""
    for name in names():
        picture = folder / name
        if not picture.is_file():
            raise FileNotFoundError(f"{folder} has no {name}")
        if site_mac.png_size(picture) != SIZE:
            raise ValueError(f"{name} is {site_mac.png_size(picture)}, not {SIZE}")
    images.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copyfile(folder / name, images / name)) for name in names()]


def main(argv: list[str]) -> int:
    if argv[:1] == ["take"] and len(argv) == 2:
        taken = take(Path(argv[1]).resolve())
        for png in taken:
            subprocess.run(site_mac._webp_command(png), check=True)
        print(f"site-win: {len(taken)} pictures in {site_mac.IMAGES}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
