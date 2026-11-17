# Adapter `muscriptor_l`

MuScriptor **large**: multi-instrument transcription (transformer language model over audio
tokens). Stickler only takes the drum track. The same adapter as `muscriptor_m` with
`SIZE = "large"`; see its README for why the raw `transcribe` events are used.

| | |
|---|---|
| Paper | Rouard, Krause, Roebel, Simon-Gabriel, Défossez: *MuScriptor: An Open Model for Multi-Instrument Music Transcription*, ISMIR 2026 (arXiv:2607.08168) |
| Code | https://github.com/muscriptor/muscriptor (Kyutai × Mirelo), PyPI `muscriptor==0.4.0` (2026-10-20), which loads `large` |
| Weights | https://huggingface.co/MuScriptor/muscriptor-large (last change 2026-07-10), `model.safetensors` **5.47 GB**, about 1.4 billion parameters; **gated**: accept the licence for *this* model on Hugging Face, then `uvx hf auth login` |
| License | Code MIT, weights CC BY-NC 4.0 (ADR 0002) |
| Input | Mix or stem; in the benchmark on the Demucs stem only, like medium |

Added for release 8 (SPEC.md): a candidate for Quality only, and only within 20 minutes for a
4-minute song on the laptop. The download (> 2 GB) was approved by the owner on 2026-11-16.

## Usage
```bash
uv run stickler setup --adapter muscriptor_l
```

## Measurements
None yet (Task 84; RunPod for the datasets, the laptop for the time budget).
