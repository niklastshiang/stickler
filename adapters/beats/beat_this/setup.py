"""Lädt den Beat-This!-Checkpoint (von cloud.cp.jku.at, ~80 MB) nach weights/."""

from beat_this.inference import load_checkpoint
from common import CHECKPOINT, WEIGHTS

if __name__ == "__main__":
    load_checkpoint(CHECKPOINT, device="cpu")
    print(f"Beat-This!-Checkpoint {CHECKPOINT} in {WEIGHTS}")
