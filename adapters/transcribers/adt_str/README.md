# Adapter `adt_str`

Transformer-based drum transcription, trained on realistic synthetic data.

| | |
|---|---|
| Paper | Melucci, Merialdo, Akama: *Towards Realistic Synthetic Data for Automatic Drum Transcription*, arXiv:2601.09520 (Jan. 2026) |
| Code | https://github.com/pier-maker92/ADT_STR, v1.0.0 (commit `77dbef2`, 2026-09-19) |
| Weights | https://huggingface.co/Pierfrancesco/adt-str, revision `a33c5c6` (2026-09-17), variant `setting-tau-0.8` |
| License | CC BY-SA 4.0 (code and weights, according to the repository) |
| Classes | 26 GM classes (47 GM percussion notes grouped) |
| Audio | 24 kHz, segments of 2.56 s |

According to the paper, the model sets new best results on ENST and MDB. Note: MDB is therefore not an independent test for this model.

## Usage
```bash
uv run stickler setup --adapter adt_str      # build environment and load bundle (weights into weights/)
```
Inference uses `ADTTranscriber.from_pretrained(...)` from the HF bundle, as described in the official README. Two adjustments, both taken from the official repository:

1. **Normalization per segment:** The official evaluation (`eval.py` → `utils.audio_utils.normalize`) normalizes each 2.56 s segment to peak level; `ADTTranscriber.transcribe` does not. Without this step, the 10 s excerpt of MDB `MusicDelta_Rock` (drum stem) gave macro-F1 0.48, with it 0.75. The runtime dropped from 215 s to 9 s, because the decoder no longer runs up to `max_length`.
2. **Numbering:** The model outputs its own class numbers (35–60), not GM. The adapter maps them back with `MappingUtils.GM_custom_midi_to_Gm_standard_Mapping` from the bundle and writes the result on channel 10, per the Stickler contract.

**Observation:** On the complete mix the model is clearly weaker (hi-hats are recognized as toms). It is trained on pure drum signals, so a separator must come before this adapter.
