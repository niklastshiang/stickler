# Qt look prototype

Stickler's main window rebuilt in Qt (PySide6 6.12), only to see how Qt's own style looks on
Windows 11, macOS and Linux (owner, 2026-11-16). Nothing works: it opens no file and plays
nothing. The sheet is a made-up groove engraved by Stickler (`sample.musicxml`) and drawn by
Verovio, as in the GTK app; light and dark follow the system.

```bash
git clone --branch claude/gifted-curie-4n4pz4 https://github.com/niklastshiang/stickler.git
cd stickler
uv run prototypes/qt/stickler_qt.py --corrections
```

`uv` fetches Python, PySide6 and Verovio by itself (install it from https://docs.astral.sh/uv/).
`--corrections` opens the sidebar; the toolbar button toggles it.

Qt's SVG module only reads SVG Tiny, so the script turns Verovio's nested `<svg>` and `<tspan>`
elements into plain ones before drawing; the notes are the same.
