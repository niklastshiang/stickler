# Adapter `yourmt3`

YourMT3+ **YPTF.MoE+Multi (PS)**: multi-instrument transcription (Perceiver-TF encoder with Mixture of Experts, multi-channel T5 decoder). Stickler only takes the drum track.

| | |
|---|---|
| Paper | Chang, Benetos, Kirchhoff, Dixon: *YourMT3+: Multi-instrument Music Transcription with Enhanced Transformer Architectures and Cross-dataset Stem Augmentation*, IEEE MLSP 2024 (arXiv:2407.04822) |
| Code | Inference code from the Hugging Face Space https://huggingface.co/spaces/mimbres/YourMT3, revision `5e66c1e` (2025-01-31). The GitHub repo mimbres/YourMT3 (last commit 2024-11-29) contains only the README. |
| Weights | In the same Space: `amt/logs/2024/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b80_ps2/checkpoints/model.ckpt` (759 MB). The Space default (noPS) is clearly weaker on drums, see ADR 0005. |
| License | Space Apache-2.0, GitHub repo GPL-3.0 |
| Input | Mix or stem (trained on multi-instrument mixes with stem augmentation) |

## Usage
```bash
uv run stickler setup --adapter yourmt3
```

## Implementation
There is no official CLI. `run.py` loads the model via `load_model_checkpoint` from the Space's `model_helper.py`, with the same arguments as `app.py`. It then reimplements `transcribe()`: mono, 16 kHz, segments of `input_frames`, batch size 8, detokenization per decoder channel.

Deviations from the Space:
- **Precision fp32 instead of fp16**, because the adapter runs on the CPU.
- **Audio via soundfile** instead of `torchaudio.load`, which in newer versions needs torchcodec.
- **MIDI output:** The shared helper writes the drum MIDI. The model already delivers the drum pitches in the GM scheme; velocity is fixed at 100.

## Measurements (2026-11-12, CPU, in parallel with the running benchmark)
For the variant comparison on 7 MDB samples, see `docs/adr/0005-yourmt3-variante.md`. On average, PS reaches a macro-F1 of 0.759 (5 classes), noPS 0.550.

Runtime: on the mix about 3.5 times the length of the audio, because all instruments are decoded. On the drum stem about the same as the audio. Peak RAM: ~2.5 GB.

The timing is correct; the kick median offset is −0.4 ms. Remaining weaknesses are model quality:
- Open hi-hats are recognized as cymbals.
- With fast swing jazz (CoolJazz), recognition drops to 0.44.

No GPU variant: for all models so far, the Radeon 840M has been slower than the CPU (ADR 0003).
