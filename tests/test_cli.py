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
