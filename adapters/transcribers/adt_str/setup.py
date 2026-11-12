"""Downloads the official inference bundle (code + weights) from Hugging Face to weights/."""

from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "Pierfrancesco/adt-str"
REVISION = "a33c5c6b191a4ca1e0f6dc22140947485eb36ce8"  # as of 2026-09-17
WEIGHTS = Path(__file__).parent / "weights"

if __name__ == "__main__":
    # Only download the variant in use (saves ~800 MB); the inference code is in the bundle root.
    path = snapshot_download(
        repo_id=REPO_ID,
        revision=REVISION,
        local_dir=WEIGHTS,
        ignore_patterns=["setting-tau-0.4/*", "setting-tau-0.6/*", "model.safetensors"],
    )
    print(f"ADT_STR bundle in {path}")
