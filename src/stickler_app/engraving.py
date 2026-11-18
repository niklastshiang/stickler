"""Engraving with Verovio (SPEC.md, module `sheet-view`): MusicXML → SVG pages for a width and
zoom, and for every written bar its page and rectangle.

The rectangles come from the staff lines in Verovio's SVG (each measure is a group holding its
staff's five lines), not from librsvg, whose rectangles are wrong for bars with dotted notes.
No GTK here, so all of it is tested without a display."""

from __future__ import annotations

import contextlib
import locale
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import verovio

BASE_SCALE = 50  # Verovio's scale (percent) at zoom 1: a staff about 36 px high
STAFF_UNITS = 720  # Verovio units from the top to the bottom staff line (4 spaces of 180)
PAD = 0.5  # the rectangle reaches this many staff heights above and below the staff
PAGE_HEIGHT = 60000  # Verovio's largest page: a screen shows one long page per song

# Verovio's fonts. Its Python module sets this path for toolkits made on the main thread only;
# on another thread (the bridge's reader) the default is the wheel's build folder and no font
# loads, so every toolkit is given the path itself.
RESOURCES = str(Path(verovio.__file__).parent / "data")
SVG = "{http://www.w3.org/2000/svg}"
MEI = "{http://www.music-encoding.org/ns/mei}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
# A text part starting or ending with no-break spaces, as in Verovio's tempo mark " = "
EDGE_SPACES = re.compile(
    '(<tspan[^>]*?font-size="(\\d+)px"[^>]*?)>(\u00a0*)([^<\u00a0]+)(\u00a0*)</tspan>'
)
SPACE_EM = 0.25  # a no-break space in Times, as a share of the font size (Verovio counts it)
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


@contextlib.contextmanager
def c_numbers() -> Iterator[None]:
    """Verovio (C++) writes numbers in the process's locale. GTK sets the user's, and under
    German Verovio wrote "scale(0,72, 0,72)", which librsvg rejects: every notehead was lost.
    Inside this block numbers have a decimal point."""
    before = locale.setlocale(locale.LC_NUMERIC)
    locale.setlocale(locale.LC_NUMERIC, "C")
    try:
        yield
    finally:
        locale.setlocale(locale.LC_NUMERIC, before)


A4 = (2100, 2970)  # Verovio units (tenths of a millimetre): a staff 7.2 mm high in print


# Room for the legend (module `legend`): a blank header line, right-aligned at the bottom of the
# header, pushes page 1's music down (Verovio stacks top-aligned lines between title and band).
BLANK_CREDIT = (
    '<credit page="1"><credit-words justify="right" valign="bottom">\u00a0</credit-words></credit>'
)
LEGEND_GAP = 0.25  # staff heights between the band and the legend
MAX_BLANKS = 80
# The legend is engraved on a page this wide and cut to its staff (Verovio's adjustPageWidth),
# so its names keep their natural spacing; wider than the page (more than about 12 entries in
# German) it is drawn smaller rather than squeezed, where names would overlap.
LEGEND_WIDTH = 6000


def a4_pages(musicxml: str, legend: str | None = None) -> list[Page]:
    """Pages for printing: A4, the title and artist on the first (Verovio's header). With a
    `legend` (its MusicXML, `logic.legend.score`) page 1 gets room under the band and the legend
    is drawn into it; the blank header lines that make the room exist only here, never in the
    MusicXML that is stored or exported. Bars may move to later pages (owner, 2026-11-17)."""
    settings = options(*A4, scale=BASE_SCALE)
    settings.update({"adjustPageHeight": False, "header": "auto"})
    if not legend:
        return render(musicxml, settings)
    key = render(
        legend, options(LEGEND_WIDTH, PAGE_HEIGHT, BASE_SCALE) | {"adjustPageWidth": True}
    )[0]
    pages = render(musicxml, settings)
    fit = min(1.0, pages[0].width / key.width)
    start = _staff_top(pages[0])  # what sits above the staff (tempo, cymbals) keeps its room
    gap = LEGEND_GAP * STAFF_UNITS * pages[0].scale
    blanks = 0
    while _staff_top(pages[0]) - start < key.height * fit + gap and blanks < MAX_BLANKS:
        blanks += 1
        pages = render(
            musicxml.replace("<part-list>", BLANK_CREDIT * blanks + "<part-list>", 1), settings
        )
    return [_with_legend(pages[0], key, header_bottom(pages[0]) + gap, fit), *pages[1:]]


def header_bottom(page: Page) -> float:
    """Pixels from the top of the page to the bottom of its header (title, band), or to the top
    margin when it has none. Blank lines (the legend's room) do not count."""
    root = ET.fromstring(page.svg)
    dx, dy = _margin(root)
    bottom = 0.0
    for head in root.iter(f"{SVG}g"):
        if head.get("class") != "pgHead":
            continue
        for rend in head.iter(f"{SVG}tspan"):
            y = rend.get("y")
            if y is None or not "".join(rend.itertext()).strip():  # str.strip drops U+00A0 too
                continue
            sizes = [
                float(t.get("font-size").removesuffix("px"))
                for t in rend.iter(f"{SVG}tspan")
                if t.get("font-size")
            ]
            bottom = max(bottom, float(y) + 0.3 * max(sizes, default=0.0))
    return (bottom + dy) * page.scale


def legend_box(page: Page) -> Box | None:
    """Where the legend is drawn on a page, in pixels, or None."""
    for child in ET.fromstring(page.svg):
        if child.tag == f"{SVG}svg" and child.get("class") == "legend":
            return Box(
                float(child.get("x")),
                float(child.get("y")),
                float(child.get("width").removesuffix("px")),
                float(child.get("height").removesuffix("px")),
            )
    return None


def _margin(root: ET.Element) -> tuple[float, float]:
    inner = next(e for e in root.iter(f"{SVG}svg") if e.get("class") == "definition-scale")
    margin = next((e for e in inner.iter(f"{SVG}g") if e.get("class") == "page-margin"), None)
    return _translate(margin.get("transform") if margin is not None else None)


def _staff_top(page: Page) -> float:
    """Pixels from the top of the page to the first staff line on it."""
    return min(b.y for b in page.bars.values()) + PAD * STAFF_UNITS * page.scale


def _with_legend(page: Page, key: Page, top: float, fit: float) -> Page:
    """`page` with the legend's SVG nested at `top`, its size times `fit`."""
    size = f'width="{key.width * fit:.1f}px" height="{key.height * fit:.1f}px"'
    root = re.sub(r'width="[^"]*" height="[^"]*"', size, key.svg, count=1)
    legend = root.replace("<svg ", f'<svg class="legend" x="0" y="{top:.1f}" ', 1)
    head, _, tail = page.svg.rpartition("</svg>")
    return replace(page, svg=head + legend + "</svg>" + tail)


def render(musicxml: str, settings: dict) -> list[Page]:
    verovio.enableLog(verovio.LOG_ERROR)  # layout warnings (tight bars) are not the user's
    with c_numbers():
        toolkit = verovio.toolkit(False)  # its fonts load from RESOURCES, on any thread
        toolkit.setResourcePath(RESOURCES)
        toolkit.setOptions(settings)
        toolkit.loadData(musicxml)
        numbers = _measure_numbers(toolkit.getMEI())
        svgs = [toolkit.renderToSVG(k) for k in range(1, toolkit.getPageCount() + 1)]
    return [_page(_keep_edge_spaces(svg), numbers) for svg in svgs]


def _keep_edge_spaces(svg: str) -> str:
    """librsvg drops a no-break space at the start of a text part (even when preserved) and at
    its end (unless preserved): "♩ = 109" read "♩=109". Leading spaces become an explicit
    shift (dx), trailing ones are kept with xml:space="preserve"; other text is untouched."""

    def fix(found: re.Match) -> str:
        head, size, lead, text, tail = found.groups()
        if not lead and not tail:
            return found.group(0)
        shift = f' dx="{len(lead) * SPACE_EM * int(size):g}"' if lead else ""
        return f'{head}{shift} xml:space="preserve">{text}{tail}</tspan>'

    return EDGE_SPACES.sub(fix, svg)


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
