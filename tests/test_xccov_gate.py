"""scripts/xccov_gate.py: the Mac app's logic outside views must be covered (CONSTRAINTS.md
"Swift coverage", task 117): only functions of the logic types count, closures in them too."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("xccov_gate", ROOT / "scripts" / "xccov_gate.py")
assert _spec and _spec.loader
xccov_gate = importlib.util.module_from_spec(_spec)
sys.modules["xccov_gate"] = xccov_gate
_spec.loader.exec_module(xccov_gate)


def _report(tmp_path: Path, functions: dict[str, tuple[int, int]], target="Stickler.app") -> Path:
    data = {
        "targets": [
            {
                "name": target,
                "files": [
                    {
                        "name": "Exports.swift",
                        "functions": [
                            {"name": name, "coveredLines": c, "executableLines": n}
                            for name, (c, n) in functions.items()
                        ],
                    }
                ],
            },
            {"name": "SticklerTests.xctest", "files": []},
        ]
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_only_the_logic_types_count(tmp_path):
    report = json.loads(
        _report(
            tmp_path,
            {
                "static Exports.pdf(_:)": (9, 10),
                "closure #1 in static Exports.pdf(_:)": (1, 2),
                "PageLoad.webView(_:didFinish:)": (2, 2),
                "ExportMenu.body.getter": (0, 30),  # a view
                "SystemAsking.saveLocation(named:)": (0, 6),  # AppKit only
                "RemovalQuestion.init(sizes:)": (0, 12),
            },
        ).read_text()
    )
    covered, total, rows = xccov_gate.coverage(report, xccov_gate.LOGIC)
    assert (covered, total) == (12, 14)
    assert [name for name, _c, _n in rows] == [
        "PageLoad.webView(_:didFinish:)",
        "closure #1 in static Exports.pdf(_:)",
        "static Exports.pdf(_:)",
    ]


def test_the_minimum_holds_or_fails(tmp_path, capsys):
    good = _report(tmp_path, {"static Panels.openSong(_:)": (19, 20)})
    assert xccov_gate.main([str(good), "--minimum", "95"]) == 0
    bad = _report(tmp_path, {"static Panels.openSong(_:)": (18, 20)})
    assert xccov_gate.main([str(bad), "--minimum", "95"]) == 1
    assert "90.00 %" in capsys.readouterr().out


def test_a_report_without_the_app_or_its_logic_is_an_error(tmp_path):
    assert xccov_gate.main([str(_report(tmp_path, {}, target="Other.app"))]) == 2
    assert xccov_gate.main([str(_report(tmp_path, {"ExportMenu.body.getter": (0, 3)}))]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert xccov_gate.main([str(broken)]) == 2
