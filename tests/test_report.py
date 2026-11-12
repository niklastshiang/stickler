"""Tests for the HTML report: content from small synthetic summary rows."""

import re

from stickler import report

CLASSES_5 = ("KD", "SD", "TT", "HH", "CY")


def srow(dataset="mdb", sep="none", trans="adtof", scheme="5", macro=0.5, **kw):
    row = {
        "dataset": dataset,
        "separator": sep,
        "transcriber": trans,
        "scheme": scheme,
        "tracks": 20,
        "errors": 1,
        "micro_f1": 0.6,
        "macro_f1": macro,
        "sep_seconds": 100.0,
        "trans_seconds": 50.0,
        "audio_seconds": 1500.0,
        "peak_rss_mb": 2048.0,
        "device": "cpu",
    }
    classes = CLASSES_5 if scheme == "5" else ("KD", "SD", "HH")
    row.update({f"f1_{c}": 0.4 for c in classes})
    row.update(kw)
    return row


def page(rows, name="default"):
    return report.render({name: rows})


def test_ranking_is_ordered_by_macro_f1_descending():
    html = page(
        [
            srow(trans="p_low", macro=0.30),
            srow(trans="p_high", macro=0.80),
            srow(trans="p_mid", macro=0.55),
        ]
    )
    assert html.index("p_high") < html.index("p_mid") < html.index("p_low")


def test_pipeline_name_micro_tracks_and_errors_are_shown():
    html = page([srow(sep="demucs", trans="adtof", micro_f1=0.6123, tracks=23, errors=2)])
    assert "demucs + adtof" in html
    assert "0.612" in html
    assert ">23<" in html and ">2<" in html


def test_datasets_and_schemes_get_their_own_tables():
    html = page([srow(dataset="mdb"), srow(dataset="own"), srow(dataset="mdb", scheme="3")])
    assert "own" in html
    assert "5-class" in html and "3-class" in html


def test_class_columns_follow_the_scheme():
    html = page([srow(scheme="3")])
    assert ">HH<" in html and ">KD<" in html
    assert ">CY<" not in html and ">TT<" not in html
    html5 = page([srow(scheme="5")])
    assert ">CY<" in html5 and ">TT<" in html5


def test_best_value_per_column_is_highlighted():
    html = page([srow(trans="a", macro=0.3), srow(trans="b", macro=0.9)])
    assert re.search(r'class="best">0\.900', html)
    assert not re.search(r'class="best">0\.300', html)


def test_runtime_rtf_and_ram_formatting():
    # (100 + 50) s of processing for 1500 s of audio -> RTF 0.10, 2048 MB -> 2.0 GB
    html = page([srow()])
    assert ">0.10<" in html or 'class="best">0.10<' in html
    assert "2.0 GB" in html
    assert "100" in html and "50" in html


def test_missing_audio_duration_shows_dash_instead_of_rtf():
    html = page([srow(audio_seconds=0.0, peak_rss_mb=0.0)])
    assert "RTF" in html
    assert "&ndash;" in html


def test_device_is_shown_and_cpu_only_is_stated():
    html = page([srow(device="cpu")])
    assert ">cpu<" in html
    assert "only CPU" in html


def test_gpu_results_drop_the_cpu_only_note():
    html = page([srow(device="cpu"), srow(trans="x", device="gpu")])
    assert ">gpu<" in html
    assert "only CPU" not in html


def test_mdb_training_overlap_note_is_present():
    html = page([srow()])
    assert "MDB Drums" in html
    assert "optimistic" in html
    assert "own" in html and "honest" in html


def test_empty_input_produces_a_valid_page_with_note():
    html = report.render({})
    assert html.startswith("<!doctype html>")
    assert "No results" in html
    assert "MDB Drums" in html


def test_page_is_self_contained_and_supports_dark_mode():
    html = page([srow()])
    assert "prefers-color-scheme: dark" in html
    assert "<style>" in html
    assert not re.search(r"(src|href)=[\"']https?:", html)
    assert "<script" not in html


def test_values_are_html_escaped():
    html = page([srow(trans="<b>x</b>")])
    assert "<b>x</b>" not in html and "&lt;b&gt;" in html


def test_multiple_configs_are_separate_sections():
    html = report.render({"default": [srow()], "own_songs": [srow(dataset="own")]})
    assert "Config: default" in html and "Config: own_songs" in html


def test_read_summary_parses_numbers_and_blank_classes(tmp_path):
    path = tmp_path / "summary.csv"
    path.write_text(
        "dataset,separator,transcriber,scheme,tracks,errors,micro_f1,macro_f1,f1_KD,f1_CY,"
        "sep_seconds,trans_seconds\n"
        "mdb,none,adtof,3,5,0,0.5,0.4,0.7,,1.5,2.5\n",
        encoding="utf-8",
    )
    (row,) = report.read_summary(path)
    assert row["tracks"] == 5 and row["macro_f1"] == 0.4
    assert row["f1_KD"] == 0.7 and row["f1_CY"] is None
    assert row["audio_seconds"] == 0.0 and row["device"] == ""  # old CSV without new columns
