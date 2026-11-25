"""Tests for scripts/cobertura_gate.py: the C# coverage gate (CONSTRAINTS.md, "C# coverage")."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "cobertura_gate", ROOT / "scripts" / "cobertura_gate.py"
)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["cobertura_gate"] = gate
_spec.loader.exec_module(gate)

COBERTURA = """<?xml version="1.0"?>
<coverage line-rate="0.5"><sources><source>C:\\work\\</source></sources>
<packages><package name="SticklerCore"><classes>
<class name="A" filename="win\\SticklerCore\\A.cs"><lines>
  <line number="1" hits="1"/><line number="2" hits="0"/><line number="3" hits="2"/>
</lines></class>
<class name="A.Inner" filename="win\\SticklerCore\\A.cs">
  <lines><line number="2" hits="1"/></lines></class>
<class name="B" filename="win\\SticklerCore\\obj\\Gen.g.cs">
  <lines><line number="1" hits="0"/></lines></class>
<class name="V" filename="win\\Stickler\\MainWindow.xaml.cs">
  <lines><line number="1" hits="0"/></lines></class>
</classes></package></packages></coverage>
"""


def test_a_line_that_any_class_ran_counts_as_run_and_paths_use_slashes():
    files = gate.lines_by_file(COBERTURA)
    assert files["C:/work/win/SticklerCore/A.cs"] == {1: True, 2: True, 3: True}


def test_only_the_included_files_count(tmp_path, capsys):
    report = tmp_path / "coverage.cobertura.xml"
    report.write_text(COBERTURA, encoding="utf-8")
    args = [str(report), "--include", "win/SticklerCore/*.cs"]
    assert gate.main([*args, "--exclude", "/obj/*"]) == 0
    assert gate.main(args) == 1  # the generated file's missed line drags it under 95 %
    assert gate.main([*args, "--show", "--minimum", "50"]) == 0
    assert "missed: 1" in capsys.readouterr().out
    assert gate.main([str(report), "--include", "nothing/*.cs"]) == 2
