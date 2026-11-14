"""Entry point `stickler-gtk`."""

from __future__ import annotations

import sys

from stickler_gtk import i18n
from stickler_gtk.ui.application import Application


def main() -> int:
    i18n.setup()
    return Application().run(sys.argv)
