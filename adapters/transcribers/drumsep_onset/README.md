# Adapter `drumsep_onset`

DrumSep splits a drum stem into six drums; an onset detector per drum turns each into hits.

| | |
|---|---|
| Model | DrumSep, MDX23C, 6 stems (kick, snare, toms, hh, ride, crash), by aufr33 and jarredou |
| Code | [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) 0.48.0 (2026-10-29, MIT), the version the `roformer` adapter pins; its `models.json` lists `MDX23C-DrumSep-aufr33-jarredou.ckpt` with `config_drumsep_mdx23c.yaml` |
| Weights | `MDX23C-DrumSep-aufr33-jarredou.ckpt` (438 MB), downloaded by `setup` from audio-separator's own mirror (release `model-configs` of nomadkaraoke/python-audio-separator); the original host (TRvlvr/model_repo) answers 404 since 2026 (checked 2026-11-16) |
| Licence | Code MIT. The weights have **no formal licence** (a community model; Hugging Face mirrors state MIT or CC BY-NC-SA). Downloaded for private use only, never shipped (ADR 0002) |
| Onsets | librosa `onset_strength` per stem at 100 frames/s; peaks picked by `stickler_adapter.onsets` (adapters/_common, shared with the `sad` adapter) on a scale shared by all six stems |
| Classes | kick → 36, snare → 38, toms → 47, hh → 42, ride → 51, crash → 49 (ride and crash score as CY) |

## Usage
```bash
uv run stickler setup --adapter drumsep_onset   # environment and weights (weights/)
```
DrumSep is trained on drums only, so it runs after a separator (`demucs+drumsep_onset`,
`oracle+drumsep_onset`); `[tool.stickler] input = "stem"` keeps it off the mix.

## Why the peaks are not picked by librosa
`librosa.onset.onset_detect` normalises each envelope on its own. A stem that holds only bleed
(a song without toms) would be scaled up until its noise looks like hits. `stickler_adapter.onsets` scales all
six stems of a song by the same value, the largest of any stem, so a quiet stem stays quiet.

Peaks are then picked exactly as the harness picks ADTOF's activations (madmom's method:
moving average subtracted, local maximum, close peaks combined; `pick` is a copy of
`stickler.peaks.pick`, kept identical by a test). The threshold (`THRESHOLD`, on the song's common
scale) is a default until it is chosen on MDB and ENST (SPEC.md, Release 7, method 2). The
envelopes are saved as `activations.npz` (5 columns, ADTOF's order and format, ride and crash
merged by maximum), so `stickler tune --transcriber drumsep_onset` can choose thresholds without
running the model again, and they reproduce this adapter's MIDI.

## Measurements
- 10 s synthetic clip (sine kicks, noise snares; CPU, cloud container): 52 s including model
  loading. Kick and snare are found at the right times, plus many false hits on toms, hi-hat and
  cymbals; the clip is far from real drums, so this only shows the adapter runs.
