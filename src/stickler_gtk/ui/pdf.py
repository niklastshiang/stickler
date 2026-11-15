"""Sheet music as PDF (SPEC.md, module `sheet-view`): Verovio's A4 pages drawn with librsvg into
a cairo PDF. The Leipzig font reaches librsvg through fontconfig, so the tempo mark is drawn."""

from __future__ import annotations

from pathlib import Path

import cairo
from gi.repository import Rsvg

from stickler_gtk.logic import engraving

A4_POINTS = (595.28, 841.89)  # 210 × 297 mm


def write_pdf(pages: list[engraving.Page], dest: Path, *, title: str = "") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    surface = cairo.PDFSurface(str(dest), *A4_POINTS)
    if title:
        surface.set_metadata(cairo.PDFMetadata.TITLE, title)
    surface.set_metadata(cairo.PDFMetadata.CREATOR, "Stickler")
    cr = cairo.Context(surface)
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y = 0, 0
    viewport.width, viewport.height = A4_POINTS
    for page in pages:
        Rsvg.Handle.new_from_data(page.svg.encode()).render_document(cr, viewport)
        cr.show_page()
    surface.finish()
    return dest
