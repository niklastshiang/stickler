"""Downloads BS-Roformer-SW via audio-separator to weights/ (download with SHA-256 check)."""

import tempfile

from audio_separator.separator import Separator
from common import MODEL, WEIGHTS

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        Separator(model_file_dir=str(WEIGHTS), output_dir=tmp).load_model(model_filename=MODEL)
    print(f"{MODEL} in {WEIGHTS}")
