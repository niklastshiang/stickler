"""Shared settings for setup.py and run.py: model and location of the weights."""

import os
from pathlib import Path

MODEL = "htdemucs_ft"
WEIGHTS = Path(__file__).parent / "weights"
# Weights live in the adapter folder instead of the global Hugging Face cache
os.environ["HF_HUB_CACHE"] = str(WEIGHTS)
