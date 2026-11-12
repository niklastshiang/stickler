"""Downloads the htdemucs_ft weights (Hugging Face, via demucs.api) to weights/."""

import demucs.api
from common import MODEL, WEIGHTS

if __name__ == "__main__":
    demucs.api.Separator(model=MODEL, progress=False)
    print(f"{MODEL} in {WEIGHTS}")
