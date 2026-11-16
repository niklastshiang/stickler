"""Shared settings for setup.py and run.py: pinned sources and where they live."""

from pathlib import Path

WEIGHTS = Path(__file__).parent / "weights"

# The paper's code (MIT), pinned; downloaded by setup.py (it is not a package).
REPO = "https://github.com/ddman1101/Separate-and-detect.git"
COMMIT = "0ac2fe6a35a7968d70ecfb8866cad025c350f5bd"  # 2026-08-13, the latest
SOURCE = WEIGHTS / "separate-and-detect"
CONFIG = SOURCE / "config" / "MSG-LD" / "integrated_musicldm_test_inference.yaml"

# The OB+TB checkpoint (MIT). It holds the VAE and the HiFi-GAN vocoder too, so MusicLDM's
# separate checkpoints are not needed.
CHECKPOINT_URL = (
    "https://huggingface.co/ddman1101/Separate-and-Detect/resolve/"
    "5384a5dcf7456ea5876de2b350438f0cfbe34726/msgld_obtb.ckpt"
)
CHECKPOINT_SHA256 = "ffead7341064caf0d6cb87fa0da1abc7d2259648ddfb3b6bd1848ce37d3dbcd1"
CHECKPOINT = WEIGHTS / "msgld_obtb.ckpt"

# The CLIP tokenizer's vocabulary is imported by the code but missing from its repository;
# OpenAI's original (MIT), pinned.
VOCAB_URL = (
    "https://raw.githubusercontent.com/openai/CLIP/"
    "d05afc436d78f1c48dc0dbf8e5980a9d471f35f6/clip/bpe_simple_vocab_16e6.txt.gz"
)
VOCAB_SHA256 = "924691ac288e54409236115652ad4aa250f48203de50a9e4722a6ecd48d6804a"
VOCAB = SOURCE / "src" / "clap" / "clap_module" / "bpe_simple_vocab_16e6.txt.gz"

SAMPLE_RATE = 44100  # the dataset reads 44.1 kHz audio (dataset.py, read_wav)
SEGMENT = 10.24  # seconds per diffusion window
STEMS = ["kick", "snare", "toms", "hi_hats", "cymbals"]  # the config's stem order
