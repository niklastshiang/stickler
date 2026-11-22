#!/usr/bin/env python3
"""The Mac app's icon from the GTK icon's layers (SPEC.md, `mac-design`: paper, staff, notes
and sticks on the macOS shape, background #e8894a since 2026-11-20; `docs/design/mac/Icon.dc.html`).

It writes two things:

- `mac/Stickler/AppIcon.icon`, the icon the app is built with: an Icon Composer bundle
  (macOS 26) with the orange as its fill and the drawing as one layer, in a light and a dark
  version (owner, 2026-11-20: in dark the paper is dark and the notes white; the staff, the
  sticks and the orange stay). macOS draws its own shape around it, and Xcode makes the
  pictures for the Dock, Finder and older systems from it.
- `packaging/icons/ng.tshia.Stickler-macos.svg`, a flat picture of the light icon on the
  design board's rounded square, for documents and the design board.

Icon Composer itself is not needed (it runs on macOS 26.4 only); the bundle's format follows
the files Icon Composer saves (`icon.json` and SVG layers in `Assets/`). Run it after changing
the GTK icon:

    uv run python scripts/mac_icon.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GTK_ICON = ROOT / "packaging" / "icons" / "ng.tshia.Stickler.svg"
MASTER = ROOT / "packaging" / "icons" / "ng.tshia.Stickler-macos.svg"
BUNDLE = ROOT / "mac" / "Stickler" / "AppIcon.icon"  # the name is the build setting's
OLD_CATALOG = ROOT / "mac" / "Stickler" / "Assets.xcassets"  # the icon set before 2026-11-22
LAYERS = ("paper", "staff", "notes", "sticks")
BACKGROUND = "#e8894a"  # the website's orange, a little deeper (owner, 2026-11-20); before #2f5d8c
LIGHT, DARK = "drawing.svg", "drawing-dark.svg"

# the design board's rounded square (824 of 1024) and where the drawing sits on it
BOARD_EDGE, BOARD_SIZE = 100, 824
DRAWING_X, DRAWING_Y, DRAWING_SIZE = 98, 127, 720

# dark appearance (owner, 2026-11-20, draft 2 of three): the paper's three sheets and the notes
DARK_PAPER = {"#ffffff": "#241f31", "#deddda": "#3d3846", "#c0bfbc": "#5e5c64"}
DARK_NOTES = {"#241f31": "#ffffff"}


def drawing(gtk_icon: str) -> str:
    """The GTK icon's drawing (its four layers, in its 128-unit coordinates)."""
    inner = re.search(r"<svg\b[^>]*>(.*)</svg>", gtk_icon, re.DOTALL)
    content = inner.group(1).strip() if inner else ""
    content = re.sub(r"<!--.*?-->\s*", "", content, flags=re.DOTALL)
    missing = [layer for layer in LAYERS if f'<g id="{layer}">' not in content]
    if missing:
        raise ValueError(f"the GTK icon has no layer {', '.join(missing)}")
    return content


def master_svg(gtk_icon: str) -> str:
    """The flat 1024-pixel picture: the design board's rounded square with the drawing on it."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 1024 1024">\n'
        f'  <rect x="{BOARD_EDGE}" y="{BOARD_EDGE}" width="{BOARD_SIZE}" height="{BOARD_SIZE}" '
        f'rx="185" fill="{BACKGROUND}"/>\n'
        f'  <svg x="{DRAWING_X}" y="{DRAWING_Y}" width="{DRAWING_SIZE}" height="{DRAWING_SIZE}" '
        'viewBox="0 0 128 128">\n'
        f"  {drawing(gtk_icon)}\n"
        "  </svg>\n"
        "</svg>\n"
    )


def _recolour(part: str, colours: dict[str, str], name: str) -> str:
    for old, new in colours.items():
        if f'"{old}"' not in part:
            raise ValueError(f"the GTK icon's {name} has no colour {old}")
        part = part.replace(f'"{old}"', f'"{new}"')
    return part


def dark_drawing(light: str) -> str:
    """The drawing for the dark appearance: the paper dark, the notes white."""
    starts = [light.index(f'<g id="{layer}">') for layer in LAYERS]
    if starts != sorted(starts):
        raise ValueError(f"the GTK icon's layers are not in the order {', '.join(LAYERS)}")
    paper, staff, notes, sticks = (
        light[start:end] for start, end in zip(starts, [*starts[1:], len(light)], strict=True)
    )
    return (
        light[: starts[0]]
        + _recolour(paper, DARK_PAPER, "paper")
        + staff
        + _recolour(notes, DARK_NOTES, "notes")
        + sticks
    )


def layer_svg(content: str) -> str:
    """A layer of the bundle: the drawing on Icon Composer's 1024-point canvas, which is the
    whole icon shape (macOS adds its own margin). The drawing keeps its place and size on the
    design board's square, scaled from 824 to 1024."""
    grow = 1024 / BOARD_SIZE
    x, y = (DRAWING_X - BOARD_EDGE) * grow, (DRAWING_Y - BOARD_EDGE) * grow
    scale = DRAWING_SIZE / 128 * grow
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 1024 1024">\n'
        f'  <g transform="translate({x:.3f} {y:.3f}) scale({scale:.5f})">\n'
        f"  {content}\n"
        "  </g>\n"
        "</svg>\n"
    )


def colour(hex_colour: str) -> str:
    """Icon Composer's way of writing a colour: "srgb:r,g,b,a" with five decimals."""
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return "srgb:" + ",".join(f"{value:.5f}" for value in [*channels, 1.0])


def descriptor() -> dict:
    """The bundle's icon.json: the orange in both appearances, one flat layer (no glass,
    shadow or translucency: the design is the flat icon) whose picture follows the appearance;
    the tinted appearance is made by macOS from the light one."""
    return {
        "fill": {"solid": colour(BACKGROUND)},
        "groups": [
            {
                "layers": [
                    {
                        "glass": False,
                        "image-name-specializations": [
                            {"value": LIGHT},
                            {"appearance": "dark", "value": DARK},
                        ],
                        "name": "Drawing",
                    }
                ],
                "name": "Drawing",
                "shadow": {"kind": "none", "opacity": 0.5},
                "specular": False,
                "translucency": {"enabled": False, "value": 0.5},
            }
        ],
        "supported-platforms": {"squares": ["macOS"]},
    }


def descriptor_text() -> str:
    """icon.json as Icon Composer writes it (two spaces, " : ", keys in order)."""
    text = json.dumps(descriptor(), indent=2, sort_keys=True, separators=(",", " : "))
    return text + "\n"


def bundle_files(gtk_icon: str) -> dict[str, str]:
    """Every file of the bundle by its path inside it."""
    light = drawing(gtk_icon)
    return {
        "icon.json": descriptor_text(),
        f"Assets/{LIGHT}": layer_svg(light),
        f"Assets/{DARK}": layer_svg(dark_drawing(light)),
    }


def main() -> int:
    gtk_icon = GTK_ICON.read_text(encoding="utf-8")
    MASTER.write_text(master_svg(gtk_icon), encoding="utf-8")
    shutil.rmtree(BUNDLE, ignore_errors=True)
    shutil.rmtree(OLD_CATALOG, ignore_errors=True)
    for name, text in bundle_files(gtk_icon).items():
        path = BUNDLE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"{MASTER.relative_to(ROOT)} and {BUNDLE.relative_to(ROOT)} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
