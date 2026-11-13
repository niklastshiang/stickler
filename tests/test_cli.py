"""The CLI is a thin layer over stickler.api (success criterion 9)."""

import ast
from pathlib import Path

from typer.testing import CliRunner

from stickler import api, cli

CLI_SOURCE = Path(cli.__file__).read_text(encoding="utf-8")


def test_cli_imports_only_the_api_from_stickler():
    imported = set()
    for node in ast.walk(ast.parse(CLI_SOURCE)):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("stickler"):
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names if a.name.startswith("stickler"))
    assert imported == {"stickler.api"}


def test_fetch_delegates_to_api(monkeypatch, tmp_path):
    calls = []

    def fake_fetch(name, data_dir):
        calls.append((name, data_dir))
        return 23

    monkeypatch.setattr(api, "fetch_dataset", fake_fetch)
    result = CliRunner().invoke(cli.app, ["fetch", "mdb", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [("mdb", tmp_path)]
    assert "23" in result.output


def test_unknown_dataset_gives_error(tmp_path):
    result = CliRunner().invoke(cli.app, ["fetch", "gibtsnicht", "--data-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "gibtsnicht" in result.output


def test_setup_delegates_to_api(monkeypatch):
    calls = []
    monkeypatch.setattr(
        api, "setup_adapters", lambda adapter, device: calls.append((adapter, device)) or [adapter]
    )
    result = CliRunner().invoke(cli.app, ["setup", "--adapter", "adt_str", "--device", "rocm"])
    assert result.exit_code == 0, result.output
    assert calls == [("adt_str", "rocm")]
    assert "adt_str" in result.output


def test_run_and_eval_delegate_to_api(monkeypatch, tmp_path):
    from stickler.runner import Record

    rec = Record("mdb", "t", "none", "adt_str", None, None, None, None, "kaputt")
    monkeypatch.setattr(
        api, "run_benchmark", lambda cfg, device=None, progress=None: progress(1, 1, "x") or [rec]
    )
    result = CliRunner().invoke(cli.app, ["run", "--device", "cpu"])
    assert result.exit_code == 0, result.output
    assert "1 combinations, 1 errors" in result.output
    assert "kaputt" in result.output

    summary = [
        {
            "dataset": "mdb",
            "separator": "none",
            "transcriber": "adt_str",
            "scheme": "5",
            "tracks": 23,
            "errors": 0,
            "micro_f1": 0.7,
            "macro_f1": 0.6,
        }
    ]
    monkeypatch.setattr(api, "evaluate_benchmark", lambda cfg, results_dir=None: summary)
    result = CliRunner().invoke(cli.app, ["eval"])
    assert result.exit_code == 0, result.output
    assert "adt_str" in result.output and "0.700" in result.output


def test_doctor_prints_checks(monkeypatch):
    from stickler.doctor import Check

    monkeypatch.setattr(
        api, "run_doctor", lambda: [Check("gpu", True, "AMD"), Check("x", False, "fehlt")]
    )
    result = CliRunner().invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "✓ gpu" in result.output and "✗ x" in result.output


def test_align_prints_quality_and_reasons(monkeypatch, tmp_path):
    q = {
        "beat_fit": 1.0,
        "coverage": 0.6,
        "explained": 0.95,
        "evaluated_seconds": 140.0,
        "excluded_strong": 0.05,
        "score_unmatched": 0.08,
    }
    reports = [
        api.AlignReport("gut", "Gut", True, {**q, "coverage": 0.99}, [], 3.0, tmp_path / "c.wav"),
        api.AlignReport("schlecht", "S", False, q, ["coverage = 0.600 (limit ≥ 0.85)"], 0, None),
        api.AlignReport("ohne", "O", False, {}, [], 0.0, None, "Score missing"),
        api.AlignReport(
            "ohr",
            "E",
            True,
            q,
            ["explained = 0.700 (limit ≥ 0.9)"],
            0,
            None,
            approved_by_ear="checked click.wav",
        ),
    ]
    monkeypatch.setattr(api, "align_songs", lambda song=None: reports)
    result = CliRunner().invoke(cli.app, ["align"])
    assert result.exit_code == 0
    assert "✓ gut" in result.output and "✗ schlecht" in result.output
    assert "limit ≥ 0.85" in result.output and "Score missing" in result.output
    assert "score passages not in the recording: 8.0% (info)" in result.output
    assert "✓ ohr" in result.output and "approved by ear: checked click.wav" in result.output


def test_run_and_eval_accept_another_config(monkeypatch, tmp_path):
    cfg = tmp_path / "own.yaml"
    seen = {}
    monkeypatch.setattr(
        api, "run_benchmark", lambda c, device=None, progress=None: seen.setdefault("run", c) and []
    )
    monkeypatch.setattr(
        api,
        "evaluate_benchmark",
        lambda c, results_dir=None: seen.update(eval=c, out=results_dir) or [],
    )
    assert CliRunner().invoke(cli.app, ["run", "--config", str(cfg)]).exit_code == 0
    assert CliRunner().invoke(cli.app, ["eval", "--config", str(cfg)]).exit_code == 0
    assert seen == {"run": cfg, "eval": cfg, "out": api.RESULTS_DIR / "own"}


def test_report_delegates_to_api(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "write_report", lambda: tmp_path / "report.html")
    result = CliRunner().invoke(cli.app, ["report"])
    assert result.exit_code == 0, result.output
    assert "report.html" in result.output


def test_notate_prints_outputs_and_exports_drums(monkeypatch, tmp_path):
    from stickler.api import Notation, SongTranscription

    t = SongTranscription(
        tmp_path / "s.mp3",
        "demucs",
        "adtof",
        tmp_path / "drums.wav",
        tmp_path / "d.mid",
        [0.0, 0.5],
        [0.0],
        [(0.0, 36, 100)],
    )
    seen = {}

    def fake_notate(audio, out=None, *, pipeline, title=None, artist=None, pdf=True, device="auto"):
        seen.update(audio=audio, out=out, pipeline=pipeline, pdf=pdf)
        return Notation(tmp_path / "s.musicxml", None, "MuseScore not installed", t)

    monkeypatch.setattr(api, "notate", fake_notate)
    monkeypatch.setattr(
        api, "export_drum_track", lambda stem, dest: seen.setdefault("drums", (stem, dest))[1]
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "notate",
            str(tmp_path / "s.mp3"),
            "--pipeline",
            "none+adtof",
            "--drums",
            str(tmp_path / "d.flac"),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["pipeline"] == "none+adtof" and seen["pdf"] is False
    assert seen["drums"] == (tmp_path / "drums.wav", tmp_path / "d.flac")
    assert "s.musicxml" in result.output and "MuseScore not installed" in result.output


def test_notate_error_exits_nonzero(monkeypatch, tmp_path):
    def boom(audio, out=None, **kw):
        raise ValueError("pipeline: unknown transcriber 'nix'")

    monkeypatch.setattr(api, "notate", boom)
    result = CliRunner().invoke(cli.app, ["notate", str(tmp_path / "s.mp3")])
    assert result.exit_code == 1 and "unknown transcriber" in result.output


def test_remote_delegates_to_api(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        api,
        "run_remote",
        lambda host, port, config, pod_id=None, wipe=False: seen.update(
            host=host, port=port, config=config, pod=pod_id, wipe=wipe
        ),
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "remote",
            "root@h",
            "--port",
            "2222",
            "--config",
            "config/own.yaml",
            "--pod-id",
            "p1",
            "--wipe",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == {
        "host": "root@h",
        "port": 2222,
        "config": Path("config/own.yaml"),
        "pod": "p1",
        "wipe": True,
    }


def test_cache_migrate_reports(monkeypatch):
    from stickler.cachemigration import Report

    seen = {}

    def fake(dry_run, rekey_from):
        seen.update(dry_run=dry_run, rekey_from=rekey_from)
        return Report(3, 1, 2, 4)

    monkeypatch.setattr(api, "migrate_cache", fake)
    result = CliRunner().invoke(cli.app, ["cache-migrate", "--dry-run", "--rekey-from", "d.json"])
    assert result.exit_code == 0
    assert "would move 3" in result.output and "1 duplicates" in result.output
    assert seen == {"dry_run": True, "rekey_from": Path("d.json")}


def test_cache_digests_writes_snapshot(monkeypatch):
    seen = []
    monkeypatch.setattr(api, "save_digests", seen.append)
    result = CliRunner().invoke(cli.app, ["cache-digests", "d.json"])
    assert result.exit_code == 0 and seen == [Path("d.json")]
