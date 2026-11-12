"""Shared settings for setup.py and run.py."""

from pathlib import Path

MODEL = "BS-Roformer-SW.ckpt"  # 6 Stems: bass, drums, guitar, other, piano, vocals (ADR 0004)
WEIGHTS = Path(__file__).parent / "weights"
