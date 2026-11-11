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
