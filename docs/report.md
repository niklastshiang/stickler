# Stickler benchmark report

Which open-source models turn a song into the most accurate drum notes? This report collects
every result and every decision of the Stickler benchmark in one place, readable without the
code. Raw numbers are in `results/` after `stickler eval`, the decisions in detail in
[`docs/adr/`](adr/).

> **Status (2026-11-13).** Complete: MDB Drums (23 tracks) and the first 10 own songs.
> Still running: ENST-Drums (64 tracks) and all pipelines on 15 further own songs (25 in
> total). Sections marked *pending* are filled in when those runs are done.

---

## 1. In short

| Mode | Pipeline | Own songs (macro-F1) | MDB (macro-F1) | Laptop time for a 4-min song |
|---|---|---|---|---|
| **Fast** | ADTOF on the original mix | 0.788 | 0.718 | ~15 s |
| **Quality** | MuScriptor medium on the Demucs stem for kick, snare and toms, ADTOF on the mix for hi-hat and cymbals | **0.815** | **0.785** | ~14 min |

*Own songs: the first 10, 5 classes. Laptop: AMD Ryzen AI 5 340, CPU only.*

- **ADTOF is the strongest single transcriber**, and on real recordings it works best on the
  original mix. Separating the drums first helps on MDB but not on the owner's rock and metal
  recordings.
- **MuScriptor medium is best at kick, snare and especially toms**, but weak at cymbals. ADTOF
  is the opposite. The *Quality* combination takes each instrument from the model that is
  best at it, and it wins on both datasets.
- **Snapping the notes to the beat grid**, as the sheet music needs, costs almost nothing on the
  own songs.
- Several ways to squeeze out more (fusing inputs, voting between models, tuning thresholds,
  consensus across repeated bars) **did not help on the target music** (section 6). ADTOF's own
  settings are already close to optimal there; the only stable gain is a higher cymbal
  threshold.

---

## 2. What is measured

**The task.** A song goes in, drum notes come out: for every hit, its time and which drum it is.

**The score.** Each estimated hit is matched to at most one reference hit of the same class
within **±50 ms**, the standard tolerance in the drum transcription literature
([`mir_eval`](https://github.com/mir-evaluation/mir_eval)). From the matches:

- **Precision**: share of the estimated hits that are real.
- **Recall**: share of the real hits that were found.
- **F1**: the harmonic mean of both; 1.0 is perfect.

**Instrument classes.** GM drum notes are grouped into classes:

| Scheme | Classes |
|---|---|
| **5 classes** (main scheme) | Kick (KD), Snare incl. side stick (SD), Toms (TT), Hi-hat open/closed/pedal (HH), Cymbals incl. ride (CY) |
| 3 classes (for comparison with the literature) | Kick, Snare, Hi-hat |

**Micro vs. macro.** *Micro-F1* counts all hits together, so frequent instruments (hi-hat, kick)
dominate. *Macro-F1* averages the F1 of the classes, so toms and cymbals count as much as the
kick. Rankings use **macro-F1 over 5 classes**, because readable sheet music needs every drum.

Counts are summed over all tracks of a dataset before F1 is computed.

---

## 3. Datasets

| Dataset | Tracks | What it is | Licence |
|---|---|---|---|
| **MDB Drums** (Southall et al., ISMIR 2017) | 23 | Multitrack productions from MedleyDB, many genres incl. a lot of jazz, with an isolated drum stem | CC BY-NC-SA 4.0 |
| **Own songs** | 10 (25 *pending*) | Commercial rock, metal and pop recordings from the owner's collection, references from musescore.com transcriptions | not published |
| **ENST-Drums** (Gillet & Richard, ISMIR 2006) | 64 *pending* | Three drummers, "minus-one" pieces in many styles, mixed 2/3 drums + 1/3 accompaniment | on request, personal scientific use only |

**Caution with MDB:** some models may have seen MDB during training or evaluation, so MDB numbers
can be optimistic. The own songs are the honest test, because they are the music Stickler is
meant for.

### How the own songs become references

Sheet music and a recording never line up by themselves: intros differ, tempos drift,
transcriptions leave passages out or add repeats. `stickler align` lays the notes onto the
recording:

1. **Beats.** Beat This! finds the beats of the recording; they are matched to the quarter notes
   of the score.
2. **Rhythm patterns.** For every beat, the rhythm of the notes is compared with the attacks in
   the Demucs drum stem; dynamic time warping (DTW) finds the best path through both.
3. **Exclusion.** Passages without a counterpart are excluded from scoring.

**Only good references are used** (owner's rule: "if the quality is not at least good, don't use
it"). The checks use no transcription model, so the candidates are not their own examiners; the
thresholds are calibrated on MDB, whose references are known to be correct:

| Check | Threshold |
|---|---|
| Paired score beats that sit on a recording beat (±70 ms) | ≥ 95 % |
| Score hits with an audible attack in the drum stem (±50 ms) | ≥ 85 % |
| Clear attacks in the stem that appear in the notes | ≥ 90 % |
| Evaluated music after exclusions | ≥ 2 min |

Passages that exist only in the sheet music are dropped from the reference but are no reason to
reject a song. If the automatic checks are fooled (for example by bass bleeding into the drum
stem), the owner can approve a song after listening to its `click.wav` (the recording on one
channel, clicks on the reference hits on the other).

Of the 28 songs with a reference file, 25 passed (one of them approved by ear). Not used: a score that covers only
98 s of a song; a 12/8 song whose score and recording could not be matched; one song narrowly
below the third threshold (to be checked by ear).

---

## 4. Candidates

Only open-source projects that are actively maintained; each adapter's README names its source and
version.

| Stage | Adapter | Project | Licence |
|---|---|---|---|
| Separation | `demucs` | Demucs v4 `htdemucs_ft`, maintained fork adefossez/demucs | MIT |
| Separation | `roformer` | BS-RoFormer "SW" (6 stems) via python-audio-separator | MIT / weights unclear (CC BY-NC-SA named by one source) |
| Separation | `none`, `oracle` | the original mix; the dataset's isolated drum stem (upper bound, MDB/ENST only) | – |
| Transcription | `adtof` | ADTOF Frame_RNN (Zehren et al. 2023), PyTorch port | CC BY-NC-SA |
| Transcription | `adt_str` | ADT_STR (2026), stems only | CC BY-SA |
| Transcription | `muscriptor_m` (`_s`) | MuScriptor medium (small) (Kyutai/IRCAM, 2026) | code MIT, weights CC BY-NC |
| Transcription | `yourmt3` | YourMT3+ YPTF.MoE+Multi (PS) | Apache-2.0 / GPL-3.0 |
| Beats | `beat_this` | Beat This! (CPJKU, ISMIR 2024) | MIT |

---

## 5. Results

### 5.1 Own songs (10 songs, 5 classes)

*Update with 25 songs pending.*

| Pipeline | Macro-F1 | Kick | Snare | Toms | Hi-hat | Cymbals |
|---|---|---|---|---|---|---|
| **Quality** (combination) | **0.815** | 0.91 | 0.89 | 0.83 | 0.74 | 0.71 |
| ADTOF, mix | 0.788 | 0.89 | 0.88 | 0.72 | 0.74 | 0.71 |
| ADTOF, Demucs | 0.760 | 0.90 | 0.85 | 0.65 | 0.71 | 0.70 |
| ADTOF, RoFormer | 0.745 | 0.88 | 0.82 | 0.65 | 0.70 | 0.67 |
| MuScriptor medium, RoFormer | 0.734 | 0.91 | 0.87 | 0.80 | 0.67 | 0.43 |
| MuScriptor medium, Demucs | 0.727 | 0.91 | 0.89 | 0.83 | 0.66 | 0.35 |
| ADT_STR, Demucs | 0.637 | 0.86 | 0.75 | 0.63 | 0.55 | 0.40 |
| ADT_STR, RoFormer | 0.618 | 0.84 | 0.74 | 0.59 | 0.55 | 0.37 |
| YourMT3+, RoFormer | 0.604 | 0.84 | 0.72 | 0.58 | 0.53 | 0.35 |
| YourMT3+, Demucs | 0.597 | 0.84 | 0.69 | 0.57 | 0.51 | 0.36 |
| YourMT3+, mix | 0.542 | 0.79 | 0.73 | 0.32 | 0.47 | 0.40 |

### 5.2 MDB Drums (23 tracks, 5 classes)

| Pipeline | Macro-F1 | Kick | Snare | Toms | Hi-hat | Cymbals |
|---|---|---|---|---|---|---|
| **Quality** (combination) | **0.785** | 0.92 | 0.76 | 0.56 | 0.85 | 0.83 |
| ADTOF, RoFormer | 0.778 | 0.95 | 0.80 | 0.43 | 0.86 | 0.85 |
| MuScriptor medium, RoFormer | 0.773 | 0.95 | 0.79 | 0.59 | 0.76 | 0.78 |
| MuScriptor medium, oracle stem | 0.766 | 0.91 | 0.81 | 0.60 | 0.75 | 0.75 |
| ADTOF, oracle stem | 0.764 | 0.96 | 0.81 | 0.32 | 0.86 | 0.87 |
| ADTOF, Demucs | 0.762 | 0.93 | 0.78 | 0.39 | 0.85 | 0.86 |
| MuScriptor medium, Demucs | 0.747 | 0.92 | 0.76 | 0.56 | 0.75 | 0.75 |
| ADT_STR, oracle stem | 0.742 | 0.93 | 0.84 | 0.63 | 0.73 | 0.57 |
| ADTOF, mix | 0.718 | 0.85 | 0.71 | 0.35 | 0.85 | 0.83 |
| ADT_STR, RoFormer | 0.679 | 0.94 | 0.78 | 0.56 | 0.68 | 0.45 |
| ADT_STR, Demucs | 0.638 | 0.91 | 0.75 | 0.50 | 0.68 | 0.34 |

With 3 classes (kick, snare, hi-hat), ADTOF leads: 0.869 on the RoFormer stem, 0.876 on the
oracle stem.

### 5.3 ENST-Drums (64 tracks)

*Pending.*

### 5.4 Runtime and memory

Real-time factor (RTF) = processing time ÷ song length; 0.5 means a 4-minute song takes 2 minutes.

| Adapter | Laptop CPU¹ RTF | Peak RAM (CPU) | GPU RTF² |
|---|---|---|---|
| ADTOF | 0.03 | ~0.7 GB | 0.02 |
| Beat This! | ~0.03 | ~0.5 GB | – |
| ADT_STR | 0.59 | ~0.7–3.7 GB | 0.07 |
| MuScriptor medium | 1.65 | ~2.6 GB | 0.14 |
| YourMT3+ | 1.76 | ~2.6 GB | ~0.2 |
| Demucs | 1.84 | ~2.7–4.0 GB | ~0.2 |
| BS-RoFormer | 4.17 | ~2.4–2.7 GB | 0.13 |

¹ AMD Ryzen AI 5 340 (12 threads), median over the songs. ² RTX 4090 on a 5-min song, RTX 3090 on
ENST (incl. model loading). On the laptop's Radeon 840M (ROCm), every model was slower than
on the CPU, so Stickler computes on the CPU there ([ADR 0003](adr/0003-rocm-kanal.md)).

---

## 6. What was tried and did not help

The tuning rule: **choose settings on some data, check them on other data.** Choices made on
MDB were checked on the own songs; choices made on the own songs were cross-validated (tuned on
20 songs, tested on the other 5, five times).

| Idea | On the tuning data | On unseen own songs | Why |
|---|---|---|---|
| Fuse ADTOF's frame probabilities of mix and stem, tune thresholds per class (chosen on MDB) | big gains (toms 0.35 → 0.54) | **0.788 → 0.729** | MDB's jazz ghost notes call for a very low snare threshold that adds false snares in rock and metal |
| Same, but only the fusion weights | gains | 0.788 → 0.771 | separated stems help ADTOF on MDB, not on the own recordings |
| Vote: a hit counts if 2 of 3 (or 3 of 5) pipelines detect it (chosen on MDB) | big gains | 0.788 → 0.773 | toms and hi-hat better, kick, snare and cymbals worse |
| Consensus across repeated bars: fill in hits that most similar bars have | +0.002 | ±0.000 | only 31 % of the added hits were right: what one bar lacks is usually a real variation (hi-hat left out before a fill), while model errors repeat in every bar |
| Tune ADTOF's thresholds on the own songs (cross-validated) | – | 0.770 → 0.774 | ADTOF's defaults are already close to optimal; the only stable change is the cymbal threshold (0.30 → 0.44, chosen in all five folds, cymbals 0.680 → 0.710) |
| Snap notes to the beat grid like the sheet music | – | 0.815 → 0.812 (Quality) | not an optimisation but a check: the notes on paper are as good as the detection |

**Lesson:** what is optimal on MDB favours separated stems and jazz subtleties and does not
transfer to rock and metal. Real gains need tuning data from the target music, which is why the
own song set was grown from 10 to 25.

---

## 7. Decisions

| Decision | Why | Record |
|---|---|---|
| Only open-source models from maintained projects; non-commercial weights allowed | free models, reproducible; NC weights are downloaded by each user, never shipped | [ADR 0002](adr/0002-nc-lizenzen.md) |
| Demucs from the maintained fork | the original repository is archived | [ADR 0001](adr/0001-demucs-fork.md) |
| GPU optional per adapter; CPU by default on the laptop | on the Radeon 840M every model was slower on the GPU | [ADR 0003](adr/0003-rocm-kanal.md) |
| BS-RoFormer "SW" checkpoint | delivers a separate drum stem; origin and licence partly unclear, documented | [ADR 0004](adr/0004-roformer-checkpoint.md) |
| YourMT3+ "PS" variant | as in the official demo | [ADR 0005](adr/0005-yourmt3-variante.md) |
| Release numbers 1, 2, 3 … instead of SemVer | a tool, not a library; owner's preference | [ADR 0006](adr/0006-versionierung.md) |
| Each model in its own environment, called as a subprocess | the models' dependencies conflict; a new candidate is one folder | SPEC.md |
| Cache keyed by input content and adapter code, not by device | results from a rented GPU count on the laptop; comments and translations do not invalidate results | tasks/todo.md (Task 20) |
| Dropped MuScriptor small and MuScriptor medium on the mix | last in every measurement; most expensive job and below ADTOF | config files |
| ADT_STR only on separated stems | trained on isolated drums; hallucinates on the mix | adapter README |
| Rented GPU (RunPod, EU) for development runs, data wiped afterwards | sustained 95 °C on the laptop; licensed data must not stay on third-party machines | tasks/todo.md (Phase 5b) |
| Own songs: quality thresholds, ≥ 2 min, missing passages no reason to reject, approval by ear | references must be good, but real transcriptions are never perfect | section 3 |
| ENST: minus-one tracks, 2/3 drums + 1/3 accompaniment | the common evaluation set with accompaniment | `stickler.datasets.enst` |
| Tune on the target music, with cross-validation | MDB choices did not transfer | section 6 |

---

## 8. Limits

- **Small target set.** 25 own songs are enough for cross-validated tuning of a few parameters,
  not for training.
- **References are transcriptions by third parties**, aligned automatically; errors in them count
  against every model alike.
- **MDB may overlap with training data** of some models; RoFormer's training data is unknown.
- **Compound meters** (6/8, 12/8) are not handled by the alignment yet.
- **Five classes only.** Open vs. closed hi-hat and ride vs. crash matter on paper; ADTOF does not
  distinguish them (planned).

---

## 9. Reproduce

See the [CLI guide](cli.md) and the [requirements](requirements.md). In short:

```console
uv sync
uv run stickler fetch mdb
uv run stickler setup
uv run stickler run && uv run stickler eval && uv run stickler report
```

Own songs need your own recordings and transcriptions (section 3); they are never part of the
repository.
