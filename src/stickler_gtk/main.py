"""Entry point `stickler-gtk`."""

from __future__ import annotations

import os
import sys

from stickler_app import i18n, paths
from stickler_gtk.ui.application import Application


def main() -> int:
    os.environ.update(paths.packaged_env())  # an AppImage's own settings, before anything runs
    i18n.setup()
    return Application().run(sys.argv)
