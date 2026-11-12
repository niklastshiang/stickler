"""Gemeinsame Einstellungen für setup.py und run.py."""

import os
from pathlib import Path

CHECKPOINT = "final0"  # Standard der Bibliothek: trainiert auf allen Daten außer GTZAN, Seed 0
WEIGHTS = Path(__file__).parent / "weights"
# torch.hub legt den Checkpoint unter $TORCH_HOME/hub/checkpoints ab → im Adapter-Ordner
os.environ["TORCH_HOME"] = str(WEIGHTS)
