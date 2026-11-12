"""Downloads MuScriptor (gated: accept the licence on Hugging Face, `uvx hf auth login`)."""

from common import SIZE, WEIGHTS
from muscriptor.transcription_model import TranscriptionModel

if __name__ == "__main__":
    TranscriptionModel.load_model(SIZE, device="cpu")
    print(f"MuScriptor {SIZE} in {WEIGHTS}")
