"""Lädt Inferenz-Code und den genutzten Checkpoint aus dem YourMT3-Space nach weights/."""

from common import EXP, REPO_ID, REVISION, WEIGHTS
from huggingface_hub import snapshot_download

if __name__ == "__main__":
    path = snapshot_download(
        repo_id=REPO_ID,
        repo_type="space",
        revision=REVISION,
        local_dir=WEIGHTS,
        allow_patterns=["model_helper.py", "amt/src/**", f"amt/logs/2024/{EXP}/checkpoints/*"],
        ignore_patterns=["amt/src/extras/**", "amt/src/tests/**", "*.DS_Store", "*.coverage"],
    )
    print(f"YourMT3-Bundle in {path}")
