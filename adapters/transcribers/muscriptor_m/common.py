"""Shared settings for setup.py and run.py."""

import os
from pathlib import Path

SIZE = "medium"
WEIGHTS = Path(__file__).parent / "weights"
# Weights (gated, login required) in the adapter folder instead of the global Hugging Face cache
os.environ["HF_HUB_CACHE"] = str(WEIGHTS)
