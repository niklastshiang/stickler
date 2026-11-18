#!/usr/bin/env python3
"""The website's example (SPEC.md "Website"): the first seconds of a song as the app plays it
with "Both", the song a little down and a click on every hit Stickler detected, so a visitor
hears what was written down.

Analyses the song with the app's Fast analysis (the checkout's models) in a private cache, renders
the clicks as the app does (`api.render_hits`) and mixes both with the app's default volumes.

Usage: uv run python scripts/site_clip.py <song> <out dir>
       writes <out dir>/<name>.ogg (Opus) and <name>.mp3, <name> from the song's file name.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SECONDS = 20
FADE = 1.5


def mix_command(song: Path, clicks: Path, out: Path) -> list[str]:
    from stickler_app.settings import Settings

    codec = (
        ["-c:a", "libopus", "-b:a", "64k"]
        if out.suffix == ".ogg"
        else ["-c:a", "libmp3lame", "-b:a", "96k"]
    )
    graph = (
        f"[0:a]volume={Settings.song_volume}[song];[1:a]volume={Settings.hits_volume}[hits];"
        f"[song][hits]amix=inputs=2:normalize=0,afade=t=out:st={SECONDS - FADE}:d={FADE}"
    )
    return (
        ["ffmpeg", "-v", "error", "-y", "-i", str(song), "-i", str(clicks)]
        + ["-filter_complex", graph, "-t", str(SECONDS), "-ac", "2"]
        + codec
        + [str(out)]
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    song, out_dir = Path(argv[0]).resolve(), Path(argv[1])
    name = re.sub(r"[^a-z0-9]+", "-", song.stem.lower()).strip("-")
    with tempfile.TemporaryDirectory() as tmp:
        # private settings and caches, as scripts/gtk.sh demo: the user's are never touched
        for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            os.environ[var] = str(Path(tmp) / var.lower())
        os.environ["STICKLER_RESULTS_CACHE"] = str(Path(tmp) / "results")
        from stickler import api
        from stickler_app import analysis

        clicks = Path(tmp) / "clicks.wav"
        analysis.analyse(
            song, Path(tmp) / "score.musicxml", lambda _step: None, api.CancelToken(), clicks
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        for kind in ("ogg", "mp3"):
            subprocess.run(mix_command(song, clicks, out_dir / f"{name}.{kind}"), check=True)
    print(f"site-clip: {out_dir / name}.ogg and .mp3")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
