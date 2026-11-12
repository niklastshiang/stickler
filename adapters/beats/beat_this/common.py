"""Shared settings for setup.py and run.py."""

import os
from pathlib import Path

CHECKPOINT = "final0"  # library default: trained on all data except GTZAN, seed 0
WEIGHTS = Path(__file__).parent / "weights"
# torch.hub stores the checkpoint under $TORCH_HOME/hub/checkpoints → in the adapter folder
os.environ["TORCH_HOME"] = str(WEIGHTS)
