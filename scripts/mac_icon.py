#!/usr/bin/env python3
"""The Mac app's icon from the GTK icon's layers (SPEC.md, `mac-design`: paper, staff, notes
and sticks on the macOS shape, background #2f5d8c; `docs/design/mac/Icon.dc.html`).

It writes the 1024-pixel master `packaging/icons/ng.tshia.Stickler-macos.svg` and the pictures
of `mac/Stickler/Assets.xcassets/AppIcon.appiconset`. Drawing needs librsvg, which comes with
the GTK environment, so run it there after changing the GTK icon:

    .venv-gtk/bin/python scripts/mac_icon.py

The pictures are kept in git: neither CI nor the Mac build has librsvg.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GTK_ICON = ROOT / "packaging" / "icons" / "ng.tshia.Stickler.svg"
MASTER = ROOT / "packaging" / "icons" / "ng.tshia.Stickler-macos.svg"
CATALOG = ROOT / "mac" / "Stickler" / "Assets.xcassets"
ICONSET = CATALOG / "AppIcon.appiconset"
LAYERS = ("paper", "staff", "notes", "sticks")
BACKGROUND = "#2f5d8c"
POINTS = (16, 32, 128, 256, 512)  # each at 1x and 2x


def master_svg(gtk_icon: str) -> str:
    """The 1024-pixel icon: the design board's rounded square (macOS masks it to its own
    shape) with the GTK icon's drawing on it."""
    inner = re.search(r"<svg\b[^>]*>(.*)</svg>", gtk_icon, re.DOTALL)
    drawing = inner.group(1).strip() if inner else ""
    missing = [layer for layer in LAYERS if f'<g id="{layer}">' not in drawing]
    if missing:
        raise ValueError(f"the GTK icon has no layer {', '.join(missing)}")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 1024 1024">\n'
        f'  <rect x="100" y="100" width="824" height="824" rx="185" fill="{BACKGROUND}"/>\n'
        '  <svg x="98" y="127" width="720" height="720" viewBox="0 0 128 128">\n'
        f"  {drawing}\n"
        "  </svg>\n"
        "</svg>\n"
    )


def contents() -> dict:
    """The icon set's Contents.json: one picture per size in pixels, named by it."""
    images = [
        {
            "filename": f"icon_{points * scale}.png",
            "idiom": "mac",
            "scale": f"{scale}x",
            "size": f"{points}x{points}",
        }
        for points in POINTS
        for scale in (1, 2)
    ]
    return {"images": images, "info": {"author": "xcode", "version": 1}}


def draw(svg: str, pixels: int, dest: Path) -> None:
    import cairo
    import gi

    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg

    handle = Rsvg.Handle.new_from_data(svg.encode("utf-8"))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixels, pixels)
    box = Rsvg.Rectangle()
    box.x, box.y, box.width, box.height = 0, 0, pixels, pixels
    handle.render_document(cairo.Context(surface), box)
    surface.write_to_png(str(dest))


def main() -> int:
    svg = master_svg(GTK_ICON.read_text(encoding="utf-8"))
    MASTER.write_text(svg, encoding="utf-8")
    ICONSET.mkdir(parents=True, exist_ok=True)
    listing = contents()
    for old in ICONSET.glob("*.png"):
        old.unlink()
    for pixels in sorted({int(i["filename"][5:-4]) for i in listing["images"]}):
        draw(svg, pixels, ICONSET / f"icon_{pixels}.png")
    as_json = {"indent": 2, "sort_keys": True}
    (ICONSET / "Contents.json").write_text(json.dumps(listing, **as_json) + "\n", encoding="utf-8")
    catalog = {"info": {"author": "xcode", "version": 1}}
    (CATALOG / "Contents.json").write_text(json.dumps(catalog, **as_json) + "\n", encoding="utf-8")
    print(f"{MASTER.relative_to(ROOT)} and {len(list(ICONSET.glob('*.png')))} pictures written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
