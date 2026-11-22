#!/usr/bin/env python3
"""The pictures of the website's "How it works" story (SPEC.md "Website", "Change 2026-11-22"):
drawn from Stickler's real output for the example song, not from screenshots.

    uv run python scripts/site_story.py analyse <song>   # once, needs the checkout's models
    uv run python scripts/site_story.py draw             # the pictures from the stored data

`analyse` runs the app's Fast analysis of the song in private caches (as scripts/site_clip.py)
and keeps what the pictures need in `site/story/`: `story.json` (the first seconds' loudness and
hits) and `notes.svg` (the first two systems of the engraved sheet music, with the bars' places
in `story.json`). `draw` turns that data into the inline pictures of both index pages, between
`<!-- story:NAME -->` and `<!-- /story:NAME -->`; it needs no models, and a test checks that the
pages hold what it draws.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STORY = SITE / "story"
DATA = STORY / "story.json"
NOTES = STORY / "notes.svg"
PAGES = (SITE / "index.html", SITE / "de" / "index.html")

SECONDS = 20  # as the example clip (scripts/site_clip.py)
COLUMNS = 160  # loudness values over those seconds
GROUPS = ("kick", "snare", "cymbals")  # stickler.align._group: 0 kick, 1 snare and toms, 2 metals
NOTES_WIDTH = 900  # pixels the sheet music is engraved at
SYSTEMS = 2

# the waveform picture's own coordinates
WIDTH, WAVE_HEIGHT, LANE = 1000, 160, 26


# ---------- analyse: the song → story.json and notes.svg ----------


def envelope(samples, rate: int, seconds: float = SECONDS, columns: int = COLUMNS) -> list[float]:
    """The loudest sample of each column of the first `seconds`, scaled so the loudest is 1."""
    import numpy as np

    part = np.abs(np.asarray(samples[: round(seconds * rate)], dtype=float))
    peaks = [float(chunk.max()) if chunk.size else 0.0 for chunk in np.array_split(part, columns)]
    top = max(peaks) or 1.0
    return [round(p / top, 3) for p in peaks]


def first_hits(hits: list[tuple[float, int, int]], seconds: float = SECONDS) -> list[list]:
    """The hits of the first `seconds` as [time, group], the group as the clicks have it."""
    from stickler import align

    return [[round(t, 3), GROUPS[align._group(pitch)]] for t, pitch, _ in hits if t < seconds]


def _drop_systems(svg: str, keep: int) -> str:
    """The SVG without the systems after the first `keep` (Verovio's `<g class="system">`) and
    without the tempo mark, whose note is a glyph of a font the site does not load."""
    import xml.etree.ElementTree as ET

    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(svg)
    for parent in root.iter():
        systems = [child for child in parent if child.get("class") == "system"]
        for system in systems[keep:]:
            parent.remove(system)
        for tempo in [child for child in parent if child.get("class") == "tempo"]:
            parent.remove(tempo)
    return ET.tostring(root, encoding="unicode")


def first_systems(svg: str, boxes: dict[int, tuple], systems: int = SYSTEMS) -> tuple[str, dict]:
    """The page cut below its `systems`-th system: the SVG with its new height and the bars of
    those systems as [left, top, width, height] fractions of the cut picture."""
    rows = sorted({round(box[1]) for box in boxes.values()})[:systems]
    kept = {bar: box for bar, box in boxes.items() if round(box[1]) in rows}
    svg = _drop_systems(svg, systems)
    width = float(re.search(r'<svg[^>]*\bwidth="([\d.]+)px"', svg).group(1))
    old_height = float(re.search(r'<svg[^>]*\bheight="([\d.]+)px"', svg).group(1))
    height = round(max(y + h for _x, y, _w, h in kept.values()) + 24)
    svg = re.sub(r'(<svg[^>]*?\bheight=")[\d.]+px(")', rf"\g<1>{height}px\g<2>", svg, count=1)

    def scale(found: re.Match) -> str:  # Verovio's own units, cut by the same share
        units_w, units_h = float(found.group(2)), float(found.group(3))
        return f'{found.group(1)}0 0 {units_w:g} {round(units_h * height / old_height)}"'

    svg = re.sub(
        r'(<svg class="definition-scale"[^>]*?viewBox=")0 0 ([\d.]+) ([\d.]+)"', scale, svg, count=1
    )
    svg = svg.replace("<svg ", f'<svg viewBox="0 0 {width:g} {height}" ', 1)
    bars = {
        str(bar): [
            round(x / width, 4),
            round(y / height, 4),
            round(w / width, 4),
            round(h / height, 4),
        ]
        for bar, (x, y, w, h) in sorted(kept.items())
    }
    return svg, bars


def analyse(song: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # private settings and caches, as scripts/site_clip.py: the user's are never touched
        for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            os.environ[var] = str(Path(tmp) / var.lower())
        os.environ["STICKLER_RESULTS_CACHE"] = str(Path(tmp) / "results")
        from stickler import api, audio
        from stickler_app import analysis, engraving

        score = Path(tmp) / "score.musicxml"
        _info, notation = analysis.analyse(song, score, lambda _step: None, api.CancelToken())
        rate = 8000
        loudness = envelope(audio.load_mono(song, rate), rate)
        (page, *_rest) = engraving.engrave(score.read_text(encoding="utf-8"), NOTES_WIDTH)
        boxes = {bar: (b.x, b.y, b.width, b.height) for bar, b in page.bars.items()}
        svg, bars = first_systems(page.svg, boxes)
    STORY.mkdir(parents=True, exist_ok=True)
    NOTES.write_text(svg, encoding="utf-8")
    data = {
        "song": song.name,
        "seconds": SECONDS,
        "loudness": loudness,
        "hits": first_hits(notation.transcription.hits),
        "bars": bars,
    }
    DATA.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"site-story: {len(data['hits'])} hits, {len(bars)} bars in {DATA.relative_to(ROOT)}")


# ---------- draw: story.json → the inline pictures ----------


def _range(start: float, end: float) -> str:
    """A part of the step's view timeline, as the CSS custom properties the motion reads."""
    return f"--from: {start:.0f}%; --to: {end:.0f}%"


def waveform(data: dict) -> str:
    """The loudness as mirrored bars and the hits as dots in three lanes (kick, snare and toms,
    cymbals), each dot with the part of the scroll it appears in."""
    loudness, seconds = data["loudness"], data["seconds"]
    step = WIDTH / len(loudness)
    middle = WAVE_HEIGHT / 2
    bars = "".join(
        f"M{(i + 0.5) * step:.1f} {middle - max(v, 0.02) * middle * 0.9:.1f}"
        f"V{middle + max(v, 0.02) * middle * 0.9:.1f}"
        for i, v in enumerate(loudness)
    )
    lanes_top = WAVE_HEIGHT + 18
    height = lanes_top + LANE * len(GROUPS)
    dots = []
    for t, group in data["hits"]:
        x = t / seconds * WIDTH
        y = lanes_top + LANE * GROUPS.index(group) + LANE / 2
        start = 20 + t / seconds * 50  # the dots appear from 20 % to 70 % of the step
        dots.append(
            f'<circle class="story-hit {group}" cx="{x:.1f}" cy="{y:.1f}" r="7" '
            f'style="{_range(start, start + 4)}"/>'
        )
    lines = "".join(
        f'<path class="story-lane" d="M0 {lanes_top + LANE * k + LANE / 2:.1f}H{WIDTH}"/>'
        for k in range(len(GROUPS))
    )
    return (
        f'<svg class="story-wave" viewBox="0 0 {WIDTH} {height:.0f}" aria-hidden="true">'
        f'<path class="story-loudness" d="{bars}" stroke-width="{step * 0.55:.1f}"/>'
        f"{lines}{''.join(dots)}</svg>"
    )


def bar_marks(data: dict) -> str:
    """One mark per bar of the shown systems over the sheet music, each lit in its own part of
    the scroll, bar after bar; the last one stays lit."""
    bars = list(data["bars"].values())
    share = 60 / len(bars)
    marks = []
    for k, (x, y, w, h) in enumerate(bars):
        start = 20 + k * share
        end = start + share if k < len(bars) - 1 else 100
        marks.append(
            f'<rect class="story-bar" x="{x * 100:.2f}%" y="{y * 100:.2f}%" '
            f'width="{w * 100:.2f}%" height="{h * 100:.2f}%" rx="4" '
            f'style="{_range(start, end)}"/>'
        )
    return f'<svg class="story-marks" aria-hidden="true">{"".join(marks)}</svg>'


def pictures(data: dict) -> dict[str, str]:
    return {"wave": waveform(data), "marks": bar_marks(data)}


def fill(html: str, drawn: dict[str, str]) -> str:
    """The page with each `<!-- story:NAME -->…<!-- /story:NAME -->` holding its picture."""
    for name, picture in drawn.items():
        pattern = re.compile(rf"(<!-- story:{name} -->).*?(<!-- /story:{name} -->)", re.DOTALL)
        if not pattern.search(html):
            raise ValueError(f"the page has no place for the story's {name}")
        html = pattern.sub(lambda m, p=picture: m.group(1) + p + m.group(2), html)
    return html


def draw() -> None:
    drawn = pictures(json.loads(DATA.read_text(encoding="utf-8")))
    for page in PAGES:
        page.write_text(fill(page.read_text(encoding="utf-8"), drawn), encoding="utf-8")
    print(f"site-story: {', '.join(drawn)} drawn into {len(PAGES)} pages")


def main(argv: list[str]) -> int:
    if argv[:1] == ["analyse"] and len(argv) == 2:
        analyse(Path(argv[1]).resolve())
        return 0
    if argv == ["draw"]:
        draw()
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
