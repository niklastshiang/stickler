"""Die CLI ist eine dünne Schicht über stickler.api (Success Criterion 9)."""

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
    monkeypatch.setattr(api, "setup_adapters", lambda adapter: calls.append(adapter) or [adapter])
    result = CliRunner().invoke(cli.app, ["setup", "--adapter", "adt_str"])
    assert result.exit_code == 0, result.output
    assert calls == ["adt_str"]
    assert "adt_str" in result.output


def test_run_and_eval_delegate_to_api(monkeypatch, tmp_path):
    from stickler.runner import Record

    rec = Record("mdb", "t", "none", "adt_str", None, None, None, None, "kaputt")
    monkeypatch.setattr(
        api, "run_benchmark", lambda cfg, device=None, progress=None: progress(1, 1, "x") or [rec]
    )
    result = CliRunner().invoke(cli.app, ["run", "--device", "cpu"])
    assert result.exit_code == 0, result.output
    assert "1 Kombinationen, 1 Fehler" in result.output
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
    monkeypatch.setattr(api, "evaluate_benchmark", lambda cfg: summary)
    result = CliRunner().invoke(cli.app, ["eval"])
    assert result.exit_code == 0, result.output
    assert "adt_str" in result.output and "0.700" in result.output
