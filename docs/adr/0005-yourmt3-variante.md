# ADR 0005: YourMT3+ with the variant "YPTF.MoE+Multi (PS)" instead of the Space default

- Status: accepted
- Date: 2026-11-12

## Context
The Hugging Face Space mimbres/YourMT3 (revision `5e66c1e`) offers five checkpoints. The default is "YPTF.MoE+Multi (noPS)". With it, the adapter achieved conspicuously weak drum values on MDB (punk mix: macro-F1 0.48).

Checked and ruled out:
- **Faulty loading:** The checkpoint loads completely; there are no missing or surplus weights.
- **Wrong configuration:** The audio and model configuration stored in the checkpoint matches the arguments from `app.py`.
- **Timing:** The kick median offset is −0.4 ms.
- **Segment boundaries:** The errors are spread evenly across the 2.048 s segments.
- **Post-processing:** `trim_overlapping_notes` only merges notes of the same pitch.

The authors evaluate drums only in the 3-class scheme (kick, snare, hi-hat). There they reach DTM 0.87 on ENST-Drums and 0.90 on Slakh. ENST is part of the training data.

## Comparison (CPU, macro-F1 5-class / 3-class)
| MDB sample | noPS | PS |
|---|---|---|
| Punk, oracle stem | 0.494 / 0.629 | 0.670 / 0.817 |
| Punk, mix | 0.481 / 0.610 | 0.588 / 0.687 |
| 80sRock, mix | 0.664 / 0.697 | 0.911 / 0.966 |
| Reggae, mix | 0.537 / 0.573 | 0.778 / 0.837 |
| Zeppelin, mix | 0.603 / 0.470 | 0.933 / 0.911 |
| Hendrix, mix | 0.889 / 0.889 | 0.992 / 0.992 |
| CoolJazz, mix | 0.182 / 0.182 | 0.442 / 0.464 |
| **Mean** | **0.550 / 0.579** | **0.759 / 0.811** |

## Decision
The adapter `yourmt3` uses `mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b80_ps2/checkpoints/model.ckpt` (759 MB), with the same arguments as the noPS variant in `app.py`.

## Consequences
- **Selection bias:** The variant was selected on 7 MDB samples, i.e. on the benchmark dataset itself. However, the lead is unambiguous on all 7 samples, not just on average. The own songs remain the independent test.
- `setup.py` now loads only this checkpoint. An already downloaded noPS checkpoint can be deleted from `weights/`.
