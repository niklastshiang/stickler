"""Tests for CSV output and summary across tracks."""

import csv

import pytest

from stickler.results import summarize, write_csv


def row(track, cls, tp, fp, fn, f1=0.0, error="", sec=1.0, audio=10.0, ram=100.0, device="cpu"):
    return {
        "dataset": "d",
        "track": track,
        "separator": "none",
        "transcriber": "t",
        "device": device,
        "audio_seconds": audio,
        "peak_rss_mb": ram,
        "sep_seconds": 0.0,
        "trans_seconds": sec,
        "error": error,
        "scheme": "5",
        "class": cls,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": 0.0,
        "recall": 0.0,
        "f1": f1,
    }


ROWS = [
    row("a", "KD", 2, 0, 0),
    row("a", "SD", 0, 1, 1),
    row("a", "micro", 2, 1, 1),
    row("a", "macro", 0, 0, 0, f1=0.5),
    row("b", "KD", 1, 1, 0),
    row("b", "SD", 1, 0, 0),
    row("b", "micro", 2, 1, 0),
    row("b", "macro", 0, 0, 0, f1=0.83),
    row("c", "", 0, 0, 0, error="kaputt"),
]


def test_summary_sums_counts_over_tracks():
    (s,) = summarize(ROWS)
    assert s["tracks"] == 2 and s["errors"] == 1
    assert s["f1_KD"] == pytest.approx(2 * 3 / (2 * 3 + 1))  # TP 3, FP 1, FN 0
    assert s["f1_SD"] == pytest.approx(2 * 1 / (2 * 1 + 1 + 1))  # TP 1, FP 1, FN 1
    assert s["micro_f1"] == pytest.approx(2 * 4 / (2 * 4 + 2 + 1))
    assert s["macro_f1"] == pytest.approx((s["f1_KD"] + s["f1_SD"]) / 2)
    assert s["trans_seconds"] == pytest.approx(2.0)


def test_write_csv_roundtrip(tmp_path):
    path = tmp_path / "x" / "m.csv"
    write_csv(path, ROWS)
    with path.open(encoding="utf-8") as f:
        back = list(csv.DictReader(f))
    assert len(back) == len(ROWS) and back[0]["class"] == "KD"


def test_summary_adds_audio_seconds_peak_ram_and_device():
    rows = [
        row("a", "KD", 1, 0, 0, audio=30.0, ram=500.0),
        row("a", "micro", 1, 0, 0, audio=30.0, ram=500.0),
        row("b", "KD", 1, 0, 0, audio=20.0, ram=800.0, device="gpu"),
        row("b", "micro", 1, 0, 0, audio=20.0, ram=800.0, device="gpu"),
    ]
    (s,) = summarize(rows)
    assert s["audio_seconds"] == pytest.approx(50.0)
    assert s["peak_rss_mb"] == pytest.approx(800.0)
    assert s["device"] == "cpu+gpu"


def test_summary_without_new_columns_still_works():
    old = [{k: v for k, v in r.items() if k not in ("audio_seconds", "peak_rss_mb")} for r in ROWS]
    (s,) = summarize(old)
    assert s["audio_seconds"] == 0.0 and s["peak_rss_mb"] == 0.0


def test_write_csv_empty(tmp_path):
    write_csv(tmp_path / "leer.csv", [])
    assert (tmp_path / "leer.csv").read_text() == ""
