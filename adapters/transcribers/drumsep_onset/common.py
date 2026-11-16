"""Shared settings for setup.py and run.py."""

from pathlib import Path

# 6 stems: kick, snare, toms, hh, ride, crash (aufr33 and jarredou, via audio-separator)
MODEL = "MDX23C-DrumSep-aufr33-jarredou.ckpt"
WEIGHTS = Path(__file__).parent / "weights"
