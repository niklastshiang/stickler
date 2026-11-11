"""Lädt die Gewichte von htdemucs_ft (Hugging Face, über demucs.api) nach weights/."""

import demucs.api
from common import MODEL, WEIGHTS

if __name__ == "__main__":
    demucs.api.Separator(model=MODEL, progress=False)
    print(f"{MODEL} in {WEIGHTS}")
