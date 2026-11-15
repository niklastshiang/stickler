"""Engraving with Verovio (SPEC.md, module `sheet-view`): MusicXML → SVG pages for a width and
zoom, and for every written bar its page and rectangle.

The rectangles come from the staff lines in Verovio's SVG (each measure is a group holding its
staff's five lines), not from librsvg, whose rectangles are wrong for bars with dotted notes.
No GTK here, so all of it is tested without a display."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import verovio

BASE_SCALE = 50  # Verovio's scale (percent) at zoom 1: a staff about 36 px high
STAFF_UNITS = 720  # Verovio units from the top to the bottom staff line (4 spaces of 180)
PAD = 0.5  # the rectangle reaches this many staff heights above and below the staff
PAGE_HEIGHT = 60000  # Verovio's largest page: a screen shows one long page per song

SVG = "{http://www.w3.org/2000/svg}"
MEI = "{http://www.music-encoding.org/ns/mei}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
LINE = re.compile(r"M\s*(-?[\d.]+)\s+(-?[\d.]+)\s+L\s*(-?[\d.]+)\s+(-?[\d.]+)")


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


@dataclass(frozen=True)
class Page:
    svg: str
    width: float  # pixels
    height: float
    scale: float  # pixels per Verovio unit
    bars: dict[int, Box] = field(default_factory=dict)  # written bar number → rectangle


def options(page_width: int, page_height: int, scale: int) -> dict:
    """Verovio's options: only page size, scale and breaks (SPEC.md: anything else asks)."""
    return {
        "pageWidth": page_width,
        "pageHeight": page_height,
        "scale": scale,
        "adjustPageHeight": True,
        "breaks": "auto",
        "header": "none",
        "footer": "none",
    }


def engrave(musicxml: str, width: float, zoom: float = 1.0) -> list[Page]:
    """Pages `width` pixels wide; `zoom` makes the music larger at the same width."""
    scale = max(1, round(BASE_SCALE * zoom))
    page_width = max(100, round(width * 100 / scale))
    return render(musicxml, options(page_width, PAGE_HEIGHT, scale))


def render(musicxml: str, settings: dict) -> list[Page]:
    verovio.enableLog(verovio.LOG_ERROR)  # layout warnings (tight bars) are not the user's
    toolkit = verovio.toolkit()
    toolkit.setOptions(settings)
    toolkit.loadData(musicxml)
    numbers = _measure_numbers(toolkit.getMEI())
    return [_page(toolkit.renderToSVG(k), numbers) for k in range(1, toolkit.getPageCount() + 1)]


def _measure_numbers(mei: str) -> dict[str, int]:
    """Verovio's measure id → the written bar number (MusicXML's `number`, MEI's `n`)."""
    root = ET.fromstring(mei)
    return {
        m.get(XML_ID): int(m.get("n"))
        for m in root.iter(f"{MEI}measure")
        if m.get("n", "").lstrip("-").isdigit()
    }


def _translate(value: str | None) -> tuple[float, float]:
    found = re.search(r"translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)", value or "")
    return (float(found.group(1)), float(found.group(2))) if found else (0.0, 0.0)


def _page(svg: str, numbers: dict[str, int]) -> Page:
    root = ET.fromstring(svg)
    width, height = (
        float(root.get("width").removesuffix("px")),
        float(root.get("height").removesuffix("px")),
    )
    inner = next(e for e in root.iter(f"{SVG}svg") if e.get("class") == "definition-scale")
    scale = width / float(inner.get("viewBox").split()[2])
    margin = next((e for e in inner.iter(f"{SVG}g") if e.get("class") == "page-margin"), None)
    dx, dy = _translate(margin.get("transform") if margin is not None else None)
    pad = PAD * STAFF_UNITS
    bars: dict[int, Box] = {}
    for measure in root.iter(f"{SVG}g"):
        if measure.get("class") != "measure" or measure.get("id") not in numbers:
            continue
        lines = [
            tuple(map(float, found.groups()))
            for staff in measure.iter(f"{SVG}g")
            if staff.get("class") == "staff"
            for path in staff.findall(f"{SVG}path")
            if (found := LINE.match(path.get("d", "")))
        ]
        if not lines:
            continue
        left = min(min(x1, x2) for x1, _y1, x2, _y2 in lines)
        right = max(max(x1, x2) for x1, _y1, x2, _y2 in lines)
        top = min(y1 for _x1, y1, _x2, _y2 in lines)
        bottom = max(y1 for _x1, y1, _x2, _y2 in lines)
        bars[numbers[measure.get("id")]] = Box(
            (left + dx) * scale,
            (top - pad + dy) * scale,
            (right - left) * scale,
            (bottom - top + 2 * pad) * scale,
        )
    return Page(svg, width, height, scale, bars)
