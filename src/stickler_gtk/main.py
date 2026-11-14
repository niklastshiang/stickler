"""Entry point `stickler-gtk`."""

from __future__ import annotations

import sys

from stickler_gtk.ui.application import Application


def main() -> int:
    return Application().run(sys.argv)
