"""Lädt BS-Roformer-SW über audio-separator nach weights/ (Download mit SHA-256-Prüfung)."""

import tempfile

from audio_separator.separator import Separator
from common import MODEL, WEIGHTS

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        Separator(model_file_dir=str(WEIGHTS), output_dir=tmp).load_model(model_filename=MODEL)
    print(f"{MODEL} in {WEIGHTS}")
