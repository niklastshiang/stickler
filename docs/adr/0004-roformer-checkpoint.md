# ADR 0004: RoFormer separator with checkpoint "BS-Roformer-SW" via python-audio-separator

- Status: accepted (origin of the weights only partially clarified, see below)
- Date: 2026-11-11

## Context
In the community, Band-Split and Mel-Band RoFormer are considered the current state of the art in music source separation. The architecture is implemented openly ([lucidrains/BS-RoFormer](https://github.com/lucidrains/BS-RoFormer), MIT). Trained weights, however, almost always come from the community (ZFTurbo/MSST, MVSEP, UVR) and are documented to varying degrees. Stickler needs a checkpoint with its **own drum stem**. Pure vocal/instrumental models do not help.

`python-audio-separator` 0.48.0 (MIT, 2026-10-29) lists exactly one RoFormer with its own drum stem among 172 models: **BS-Roformer-SW** by jarredou (6 stems: bass, drums, guitar, other, piano, vocals). The other hits are Demucs (own adapter), MDX-Net 2021 (kuielab) and BS-Roformer-Viperx-1053, which separates only "drum-bass" jointly.

## Decision
Adapter `roformer` = `audio-separator[cpu]==0.48.0` + `BS-Roformer-SW.ckpt`, the library's default parameters, only the stem "Drums".

## Origin and License (open)
- Author according to audio-separator and MVSEP: jarredou. According to [openmirlab/bs-roformer-infer](https://github.com/openmirlab/bs-roformer-infer), the original Hugging Face account was deleted (2026-06). Mirror: `enerjazzer/BS-ROFO-SW-Fixed`.
- License: only one secondary source names CC BY-NC-SA 4.0 ([Ryan5453/unblend](https://huggingface.co/Ryan5453/unblend)). No original text was found. Under ADR 0002, NC is permitted for private use.
- Training data: unknown. An overlap with MDB/MedleyDB cannot be ruled out. The report flags this.
- Reproducibility: audio-separator verifies the download via SHA-256 (`24e7d35e…916e`).

## Consequences
- For a later publication (e.g. a GTK app), this checkpoint is **unsuitable** as long as the license is unclear.
- `audio-separator` 0.48.0 does not declare the dependency `audioread`, but imports it. The adapter adds it.
- Training our own model with lucidrains/BS-RoFormer or ZFTurbo/MSST would be the license-clean alternative. On the Radeon 840M, that is not realistic (see ADR 0003).
