"""Gemeinsame Einstellungen für setup.py und run.py."""

import os
from pathlib import Path

SIZE = "medium"
WEIGHTS = Path(__file__).parent / "weights"
# Gewichte (gated, Login nötig) im Adapter-Ordner statt im globalen Hugging-Face-Cache
os.environ["HF_HUB_CACHE"] = str(WEIGHTS)
