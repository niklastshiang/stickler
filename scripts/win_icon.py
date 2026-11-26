#!/usr/bin/env python3
"""The Windows app's icon from the GTK icon (SPEC.md, `win-design`: the free-standing GNOME
icon on a transparent background, not the Mac's orange square; module `win-package`, scope 7).

It writes `win/Stickler/Stickler.ico` with one PNG frame per size Windows asks for (16, 20, 24,
32, 40, 48, 64 and 256 pixels: the title bar, the taskbar, Explorer and Settings › Apps at
100 % to 200 % scale). The `.exe`, the window, the installer, the Start menu and Settings › Apps
take it. Run it after changing the GTK icon, with a Python that has PyGObject, librsvg and
pycairo (the GTK app's system Python, e.g. in WSL):

    /usr/bin/python3 scripts/win_icon.py

Packing and reading the `.ico` need the standard library only (the tests use them).
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "packaging/icons/ng.tshia.Stickler.svg"
TARGET = ROOT / "win/Stickler/Stickler.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
PNG = b"\x89PNG\r\n\x1a\n"


def pack(frames: list[tuple[int, bytes]]) -> bytes:
    """An `.ico` of square PNG frames (size, PNG bytes), smallest first: the ICONDIR header, one
    ICONDIRENTRY per frame (256 is written as 0), then the PNGs as they are."""
    frames = sorted(frames)
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries, images = b"", b""
    for size, png in frames:
        if not png.startswith(PNG) or not 1 <= size <= 256:
            raise ValueError(f"frame {size}: not a PNG of 1 to 256 pixels")
        side = 0 if size == 256 else size
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        images += png
    return header + entries + images


def read(data: bytes) -> list[tuple[int, int, bytes]]:
    """The frames of an `.ico`: (width, height, image bytes) as its directory names them."""
    reserved, kind, count = struct.unpack_from("<HHH", data)
    if reserved != 0 or kind != 1:
        raise ValueError("not an icon file")
    frames = []
    for i in range(count):
        w, h, _colours, _zero, _planes, _bits, length, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * i
        )
        frames.append((w or 256, h or 256, data[offset : offset + length]))
    return frames


def png_size(png: bytes) -> tuple[int, int]:
    """Width and height from a PNG's IHDR chunk."""
    if not png.startswith(PNG) or png[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", png[16:24])


def render(svg: Path, size: int) -> bytes:  # the GTK app's libraries: not in the test run
    """The SVG drawn into a transparent square of `size` pixels, as PNG."""
    import gi

    gi.require_version("Rsvg", "2.0")
    import cairo
    from gi.repository import Rsvg

    handle = Rsvg.Handle.new_from_file(str(svg))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    context = cairo.Context(surface)
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, size, size
    handle.render_document(context, viewport)
    out = io.BytesIO()
    surface.write_to_png(out)
    return out.getvalue()


def main() -> int:  # runs with the GTK app's libraries, as `render`
    TARGET.write_bytes(pack([(size, render(SOURCE, size)) for size in SIZES]))
    print(f"{TARGET.relative_to(ROOT)}: {', '.join(map(str, SIZES))} px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
