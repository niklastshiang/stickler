# /// script
# requires-python = ">=3.10"
# dependencies = ["pyside6==6.12.0", "verovio==6.4.1"]
# ///
"""A look-only prototype of Stickler's main window in Qt (PySide6), to see Qt's native style on
Windows 11, macOS and Linux (owner, 2026-11-16). Nothing works: no file is opened, nothing plays.

    uv run prototypes/qt/stickler_qt.py            # the system's own style
    uv run prototypes/qt/stickler_qt.py --corrections   # with the corrections sidebar open

The sample sheet (sample.musicxml) is a made-up groove engraved by Stickler; Verovio draws it,
as in the GTK app. Light and dark follow the system.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import verovio
from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QAction, QFontDatabase, QIcon, QPalette
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

HERE = Path(__file__).parent


SVG = "{http://www.w3.org/2000/svg}"


def _leaf_spans(node: ET.Element, inherited: dict) -> list[tuple[dict, str]]:
    """The innermost <tspan>s below `node` with the attributes they inherit (font, size)."""
    leaves = []
    for child in node:
        if child.tag != SVG + "tspan":
            continue
        attrs = {**inherited, **child.attrib}
        if any(c.tag == SVG + "tspan" for c in child):
            leaves += _leaf_spans(child, attrs)
        elif (child.text or "").strip():
            leaves.append((attrs, child.text))
    return leaves


def _tiny(svg: str, colour: str) -> bytes:
    """Verovio's SVG in the SVG Tiny that Qt's SVG module reads: its inner <svg> (the page in
    score units) becomes a group scaled to the outer size, and a <tspan> nested in another
    one moves up, with its parents' attributes (font, size). It draws the same."""
    ET.register_namespace("", SVG[1:-1])
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(svg)
    width, height = (float(root.get(k).removesuffix("px")) for k in ("width", "height"))
    for i, child in enumerate(list(root)):
        if child.tag == SVG + "svg":
            _, _, w, h = (float(v) for v in child.get("viewBox").split())
            group = ET.Element(SVG + "g", transform=f"scale({width / w} {height / h})")
            group.extend(list(child))
            root.remove(child)
            root.insert(i, group)
    for text in root.iter(SVG + "text"):
        leaves = _leaf_spans(text, {})
        if leaves:
            for child in list(text):
                text.remove(child)
            for attrs, content in leaves:
                attrs = {k: v for k, v in attrs.items() if k not in ("id", "class")}
                ET.SubElement(text, SVG + "tspan", attrs).text = content
    root.set("fill", colour)
    root.set("stroke", colour)
    return ET.tostring(root).replace(b'"black"', f'"{colour}"'.encode())


def _sheet_svg(colour: str) -> bytes:
    toolkit = verovio.toolkit()
    toolkit.setOptions(
        {"pageWidth": 1500, "pageHeight": 2970, "scale": 40, "adjustPageHeight": True}
    )
    toolkit.loadData((HERE / "sample.musicxml").read_text(encoding="utf-8"))
    return _tiny(toolkit.renderToSVG(1), colour)


def _segmented(labels: list[str], checked: int) -> QWidget:
    """A row of exclusive buttons, as close to a segmented control as plain Qt widgets get."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    group = QButtonGroup(box)
    for i, text in enumerate(labels):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(i == checked)
        group.addButton(button)
        row.addWidget(button)
    return box


def _corrections() -> QWidget:
    panel = QWidget()
    column = QVBoxLayout(panel)
    beat = QGroupBox("Beat")
    form = QFormLayout(beat)
    form.addRow("Tempo", _segmented(["Half", "As Detected", "Double"], 1))
    per_bar = QSpinBox()
    per_bar.setRange(2, 12)
    per_bar.setValue(4)
    form.addRow("Beats per bar", per_bar)
    first = QComboBox()
    first.addItems([f"Beat {k}" for k in range(1, 5)])
    form.addRow("First “one”", first)
    column.addWidget(beat)
    easier = QGroupBox("Easier to Read")
    easy = QVBoxLayout(easier)
    for text, hint in (
        ("Simplify", "Nearly equal bars get one pattern"),
        ("Repeat signs", "Equal bars are written once"),
    ):
        check = QCheckBox(text)
        check.setChecked(True)
        easy.addWidget(check)
        note = QLabel(hint)
        note.setEnabled(False)
        easy.addWidget(note)
    column.addWidget(easier)
    back = QPushButton("Back to Detected")
    back.setEnabled(False)
    column.addWidget(back)
    column.addStretch()
    panel.setMinimumWidth(300)
    return panel


def _icon(button: QToolButton, name: QIcon.ThemeIcon, fallback: str) -> None:
    """The system's icon (Windows, macOS, a Linux icon theme), else a character."""
    icon = QIcon.fromTheme(name)
    if icon.isNull():
        button.setText(fallback)
    else:
        button.setIcon(icon)


def _playbar() -> QWidget:
    bar = QFrame()
    bar.setFrameShape(QFrame.Shape.StyledPanel)
    row = QHBoxLayout(bar)
    play = QToolButton()
    _icon(play, QIcon.ThemeIcon.MediaPlaybackStart, "▶")
    play.setIconSize(QSize(20, 20))
    row.addWidget(play)
    row.addWidget(QLabel("0:17"))
    position = QSlider(Qt.Orientation.Horizontal)
    position.setRange(0, 67)
    position.setValue(17)
    row.addWidget(position, 1)
    total = QLabel("1:07")
    total.setEnabled(False)
    row.addWidget(total)
    where = QLabel("Bar 9 of 31")
    where.setEnabled(False)
    row.addWidget(where)
    volume = QToolButton()
    _icon(volume, QIcon.ThemeIcon.AudioVolumeHigh, "🔊")
    row.addWidget(volume)
    row.addWidget(_segmented(["Song", "Hits", "Both"], 2))
    return bar


class Window(QMainWindow):
    def __init__(self, corrections: bool) -> None:
        super().__init__()
        self.setWindowTitle("Sample Groove — Stickler prototype  ·  ♩ = 120  ·  4/4")
        self.resize(1000, 700)
        self.setUnifiedTitleAndToolBarOnMac(True)

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen), "Open…")
        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy()
        )
        toolbar.addWidget(spacer)
        export = QToolButton()
        export.setText("Export")
        export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(export)
        for text in ("PDF…", "MusicXML…", "Drum Track…"):
            menu.addAction(text)
        export.setMenu(menu)
        toolbar.addWidget(export)
        self.toggle = QAction("Corrections", self)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(corrections)
        toolbar.addAction(self.toggle)
        self.addToolBar(toolbar)

        menubar = self.menuBar()  # on macOS this is the screen's menu bar
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Open…")
        file_menu.addMenu(menu)
        menubar.addMenu("View").addAction(self.toggle)
        menubar.addMenu("Help").addAction("About Stickler")

        text = self.palette().color(QPalette.ColorRole.Text).name()
        sheet = QSvgWidget()
        sheet.load(QByteArray(_sheet_svg(text)))
        size = sheet.renderer().defaultSize()
        sheet.setFixedSize(size)
        page = QWidget()
        centre = QHBoxLayout(page)
        centre.addWidget(sheet, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)

        left = QWidget()
        stack = QVBoxLayout(left)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(scroll, 1)
        stack.addWidget(_playbar())

        split = QSplitter()
        split.addWidget(left)
        side = _corrections()
        split.addWidget(side)
        side.setVisible(corrections)
        self.toggle.toggled.connect(side.setVisible)
        split.setStretchFactor(0, 1)
        self.setCentralWidget(split)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corrections", action="store_true", help="open the sidebar")
    parser.add_argument("--style", help="force a Qt style (windows11, macOS, fusion)")
    parser.add_argument("--dark", action="store_true", help="force dark (for screenshots)")
    parser.add_argument("--screenshot", type=Path, help="save a PNG of the window and quit")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    # the music font Verovio names for symbols in text (the tempo's note), as the GTK app loads it
    QFontDatabase.addApplicationFont(str(HERE.parents[1] / "packaging" / "fonts" / "Leipzig.ttf"))
    if args.style:
        app.setStyle(args.style)
    if args.dark:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    window = Window(args.corrections)
    window.show()
    if args.screenshot:
        app.processEvents()
        window.grab().save(str(args.screenshot))
        return
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
