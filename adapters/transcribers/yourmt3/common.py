"""Gemeinsame Einstellungen für setup.py und run.py."""

from pathlib import Path

REPO_ID = "mimbres/YourMT3"  # Hugging-Face-Space mit Inferenz-Code und Checkpoints
REVISION = "5e66c1ea173a8186e0d20432b841d3180cc015b5"  # Stand 2025-01-31
WEIGHTS = Path(__file__).parent / "weights"
SRC = WEIGHTS / "amt" / "src"

# YPTF.MoE+Multi (PS): mit Pitch-Shift-Augmentierung trainiert. Auf 7 MDB-Proben beim
# Schlagzeug klar besser als die Space-Voreinstellung (noPS), siehe ADR 0005
EXP = "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b80_ps2"
CHECKPOINT = f"{EXP}@model.ckpt"
# Argumente wie in app.py des Space, Präzision 32 statt 16 (CPU)
ARGS = [
    CHECKPOINT,
    "-p",
    "2024",
    "-tk",
    "mc13_full_plus_256",
    "-dec",
    "multi-t5",
    "-nl",
    "26",
    "-enc",
    "perceiver-tf",
    "-sqr",
    "1",
    "-ff",
    "moe",
    "-wf",
    "4",
    "-nmoe",
    "8",
    "-kmoe",
    "2",
    "-act",
    "silu",
    "-epe",
    "rope",
    "-rp",
    "1",
    "-ac",
    "spec",
    "-hop",
    "300",
    "-atc",
    "1",
    "-pr",
    "32",
]
