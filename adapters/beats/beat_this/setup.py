"""Downloads the Beat This! checkpoint (~80 MB) to weights/: from JKU Linz, else from
Stickler's copy of the same file (download.py checks its SHA-256)."""

from beat_this.inference import load_checkpoint
from common import CHECKPOINT, WEIGHTS
from download import fetch

if __name__ == "__main__":
    source = fetch(WEIGHTS / "hub" / "checkpoints" / f"beat_this-{CHECKPOINT}.ckpt")
    load_checkpoint(CHECKPOINT, device="cpu")  # loads it the way run.py will
    print(f"Beat This! checkpoint {CHECKPOINT} in {WEIGHTS} (from {source})")
