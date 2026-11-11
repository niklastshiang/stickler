"""Gemeinsame Einstellungen für setup.py und run.py: Modell und Ablage der Gewichte."""

import os
from pathlib import Path

MODEL = "htdemucs_ft"
WEIGHTS = Path(__file__).parent / "weights"
# Gewichte liegen im Adapter-Ordner statt im globalen Hugging-Face-Cache
os.environ["HF_HUB_CACHE"] = str(WEIGHTS)
