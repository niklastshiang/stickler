#!/usr/bin/env python3
"""The Mac app's pictures for the website's "A look around" (SPEC.md "Website",
"Change 2026-11-25"): drawn by the `mac` workflow from Stickler's real transcription of the
example song, not taken by hand.

    uv run python scripts/site_mac.py fixture <song>   # once, needs the checkout's models
    uv run python scripts/site_mac.py fetch <run>      # the pictures of a `mac` workflow run

`fixture` runs the app's Fast analysis of the song in private caches (as scripts/site_story.py)
and stores what the Mac test needs to draw its window: the core's `pages` reply for the
website window's width in `mac/SticklerTests/Fixtures/eyesplit_pages.json` (the shape of
`pages.json`), and the core's `result` state for the song in `eyesplit_result.json`, with the
paths of a Mac user's folder instead of this computer's.

`fetch` downloads a `mac` workflow run's `screenshots` artifact with `gh` and puts the
website's pictures (`site-<name>-light.png`, `-dark.png`, drawn by `WebsiteScreenshotTests`)
into `site/images/` as `mac-<name>.png` and `mac-<name>-dark.png`, each with its WebP.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "mac" / "SticklerTests" / "Fixtures"
PAGES = FIXTURES / "eyesplit_pages.json"
RESULT = FIXTURES / "eyesplit_result.json"
MAC_SONG = Path("/Users/me/Music")  # where the pictures say the song is

IMAGES = ROOT / "site" / "images"
SHOTS = ("empty", "analysing", "sheet")  # WebsiteScreenshotTests' pictures, in the site's order

WINDOW_WIDTH = 1000  # points, as the GTK stills (site/images/*.png)
DESK = 12  # the margin around the sheet on each side (ContentView)
SHEET_WIDTH = WINDOW_WIDTH - 2 * DESK


def pages_reply(pages: list, zoom: float = 1.0) -> dict:
    """The core's answer to `pages`, as the bridge sends it (`pages.json`'s shape)."""
    from stickler_app.bridge import encode_page

    return {"id": 0, "ok": True, "zoom": zoom, "pages": [encode_page(p) for p in pages]}


def result_state(song: Path, info, notation) -> dict:
    """The core's `result` state for the song, as the bridge encodes it, with Mac paths."""
    import dataclasses

    from stickler_app import bridge, session

    shown = dataclasses.replace(notation, musicxml=Path("/c/e.musicxml"), pdf=None)
    state = bridge.encode(session.Result(song=MAC_SONG / song.name, info=info, notation=shown))
    state["clicks"] = "/c/e.wav"  # so the window offers the hits, as after a real analysis
    return state


def fixture(song: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # private settings and caches, as scripts/site_story.py: the user's are never touched
        for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            os.environ[var] = str(Path(tmp) / var.lower())
        os.environ["STICKLER_RESULTS_CACHE"] = str(Path(tmp) / "results")
        from stickler import api
        from stickler_app import analysis, engraving

        score = Path(tmp) / "score.musicxml"
        info, notation = analysis.analyse(song, score, lambda _step: None, api.CancelToken())
        pages = engraving.engrave(score.read_text(encoding="utf-8"), SHEET_WIDTH)
        state = result_state(song, info, notation)
    bars = sum(len(page.bars) for page in pages)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    PAGES.write_text(json.dumps(pages_reply(pages)) + "\n", encoding="utf-8")
    RESULT.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"site-mac: {len(pages)} page(s), {bars} written bars at {SHEET_WIDTH} px; "
        f"{state['title']}, {state['subtitle']}, {len(state['bars'])} played bars"
    )


def png_size(path: Path) -> tuple[int, int]:
    """A PNG's width and height in pixels, from its header."""
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a PNG")
    return struct.unpack(">II", head[16:24])


def site_names(name: str) -> list[tuple[str, str]]:
    """The artifact's two pictures of `name` and what the site calls them."""
    return [
        (f"site-{name}-light.png", f"mac-{name}.png"),
        (f"site-{name}-dark.png", f"mac-{name}-dark.png"),
    ]


def take(folder: Path, images: Path = IMAGES) -> list[Path]:
    """The website's pictures from a downloaded artifact, checked and copied into `images`."""
    expected = (WINDOW_WIDTH, 700)
    taken = []
    for name in SHOTS:
        for source, target in site_names(name):
            picture = folder / source
            if not picture.is_file():
                raise FileNotFoundError(f"the artifact has no {source}")
            if png_size(picture) != expected:
                raise ValueError(f"{source} is {png_size(picture)}, not {expected}")
            images.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(picture, images / target)
            taken.append(images / target)
    return taken


def _webp_command(png: Path) -> list[str]:
    """The same WebP as the GTK stills' (scripts/demo.py)."""
    spec = importlib.util.spec_from_file_location("demo", ROOT / "scripts" / "demo.py")
    assert spec and spec.loader
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    return demo.webp_command(png)


def fetch(run: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "screenshots"  # a new, empty folder for the download
        subprocess.run(
            ["gh", "run", "download", run, "--name", "screenshots", "--dir", str(folder)],
            check=True,
        )
        taken = take(folder)
    for png in taken:
        subprocess.run(_webp_command(png), check=True)
    print(f"site-mac: {len(taken)} pictures from run {run} in {IMAGES.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    if argv[:1] == ["fixture"] and len(argv) == 2:
        fixture(Path(argv[1]).resolve())
        return 0
    if argv[:1] == ["fetch"] and len(argv) == 2 and argv[1].isdigit():
        fetch(argv[1])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
