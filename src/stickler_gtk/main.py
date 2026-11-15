"""Entry point `stickler-gtk`."""

from __future__ import annotations

import os
import sys

from stickler_gtk import i18n
from stickler_gtk.logic import paths
from stickler_gtk.ui.application import Application


def main() -> int:
    os.environ.update(paths.packaged_env())  # an AppImage's own settings, before anything runs
    i18n.setup()
    return Application().run(sys.argv)
