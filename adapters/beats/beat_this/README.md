# Adapter `beat_this`

Beat This!: beat and downbeat tracking without DBN post-processing (transformer on the spectrogram).
Stickler uses the beats to place the notes of own songs onto audio time (`stickler align`), and
later for quantization into notation.

| | |
|---|---|
| Paper | Foscarin, Schlüter, Widmer: *Beat this! Accurate beat tracking without DBN postprocessing*, ISMIR 2024 (arXiv:2407.21658) |
| Code | https://github.com/CPJKU/beat_this, PyPI `beat-this==1.1.0` (last push 2026-05-28) |
| Weights | Checkpoint `final0` (library default), from cloud.cp.jku.at, 78 MB |
| License | MIT (code and weights) |

## Usage
```bash
uv run stickler setup --adapter beat_this
```

## Output
`beats.json` = `{"beats": [s, …], "downbeats": [s, …]}`. Downbeats are a subset of the beats.

## Measurement (2026-11-12, CPU)
- **RATATATA** (Electric Callboy, 216 s, 140 BPM according to the score): 15 s runtime, 554 MB peak RAM.
- **Result:** 499 beats and 127 downbeats.
- **Tempo:** The mean beat interval gives 142.9 BPM. The deviation from 140 BPM comes from the model's 20 ms grid (50 frames/s); individual beats scatter by ±20 ms. For time alignment, a smooth tempo curve is therefore fitted instead of taking each beat individually.

No GPU variant: 15 s per song on the CPU, and the Radeon 840M has been slower than the CPU for every model so far (ADR 0003).
