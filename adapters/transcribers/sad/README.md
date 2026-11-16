# Adapter `sad` (Separate-and-Detect)

A latent diffusion model generates five drum stems from a drum stem; an onset detector per stem
turns them into hits.

| | |
|---|---|
| Paper | Hsu, Chang, Chen, Su, Yang: *Separate-and-Detect: Unified Drum Transcription and Stem Generation via Latent Diffusion*, arXiv:2608.01093 (Aug. 2026) |
| Code | https://github.com/ddman1101/Separate-and-detect, commit `0ac2fe6` (2026-08-13, the latest; research code without releases), MIT. Downloaded by `setup` (it is not a package) |
| Weights | https://huggingface.co/ddman1101/Separate-and-Detect, revision `5384a5d`, `msgld_obtb.ckpt` (OB+TB, 5.4 GB, SHA-256 checked), MIT. It holds the VAE and the HiFi-GAN vocoder too, so MusicLDM's own checkpoints (Zenodo 10643148) are not needed |
| Also downloaded | OpenAI CLIP's `bpe_simple_vocab_16e6.txt.gz` (MIT, commit `d05afc4`): the code imports the CLIP tokenizer, but its repository lacks the file |
| Stems | kick → 36, snare → 38, toms → 47, hi_hats → 42, cymbals → 49 |
| Audio | 44.1 kHz in, 10.24 s windows, 16 kHz stems |

Tested as an exception (owner, 2026-11-16): the project is research code without visible
maintenance (CLAUDE.md asks for maintained projects). Measured on RunPod for the datasets and
the owner's songs (SPEC.md, Release 7).

## Usage
```bash
uv run stickler setup --adapter sad   # environment, code, checkpoint and vocabulary (weights/)
```
Trained on drum-only multitracks (StemGMD, IDMT), so a separator comes first
(`demucs+sad`, `oracle+sad`).

## Deviations from the paper's code, and why
- **Current stack instead of Python 3.9 and torch 1.13** (owner's question, 2026-11-16): the
  pinned environment (torch 1.13.1, pytorch-lightning 1.9.4, transformers 4.26, 2023) has known
  vulnerabilities, among them `torch.load` running code from a checkpoint. On Python 3.12 with
  torch 2.15 and pytorch-lightning 2.6 the code runs through `compat.py`, which restores six
  removed APIs (torchaudio `info`/`load`, librosa's positional `mel`, two pytorch-lightning
  imports) and skips the LPIPS download of the unused training loss; no file of the code is
  changed. The checkpoint is loaded with `weights_only=True`, so no code in it runs.
- **Every 10.24 s window is a track of its own**: the data module drops a song's last partial
  window and songs under 10 s or over 640 s; the adapter pads the last window with silence and
  joins the windows' stems in order.
- **The onset detector is Stickler's**, not the paper's madmom detector: the step shared with
  `drumsep_onset` (`stickler_adapter.onsets`), so both separations are compared with the same
  detector, and `stickler tune --transcriber sad` can choose thresholds on MDB and ENST.
- Diffusion settings are the inference config's (200 DDIM steps, one candidate).

## Measurements
See the run on 10 s of an MDB drum stem below (CPU, cloud container), and Task 84 for the
full runs.
