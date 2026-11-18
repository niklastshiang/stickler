"""scripts/swift_coverage.py: only the package's own sources count, and the minimum holds."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "swift_coverage", ROOT / "scripts" / "swift_coverage.py"
)
assert _spec and _spec.loader
swift_coverage = importlib.util.module_from_spec(_spec)
sys.modules["swift_coverage"] = swift_coverage
_spec.loader.exec_module(swift_coverage)


def _report(tmp_path: Path, files: dict[str, tuple[int, int]]) -> Path:
    data = {
        "data": [
            {
                "files": [
                    {"filename": name, "summary": {"lines": {"covered": c, "count": n}}}
                    for name, (c, n) in files.items()
                ]
            }
        ]
    }
    path = tmp_path / "codecov.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_only_the_packages_sources_count(tmp_path, capsys):
    package = tmp_path / "SticklerCore"
    (package / "Sources").mkdir(parents=True)
    src = str((package / "Sources").resolve())
    report = _report(
        tmp_path,
        {
            f"{src}/SticklerCore/Client.swift": (96, 100),
            f"{package.resolve()}/Tests/SticklerCoreTests/ClientTests.swift": (0, 500),
            "/checkouts/swift-argument-parser/Sources/Parser.swift": (0, 900),
        },
    )
    assert swift_coverage.main([str(report), str(package)]) == 0
    out = capsys.readouterr().out
    assert "SticklerCore/Client.swift" in out and "TOTAL 96/100 lines, 96.00 %" in out
    assert "ClientTests" not in out and "Parser" not in out


def test_below_the_minimum_fails(tmp_path):
    package = tmp_path / "P"
    (package / "Sources").mkdir(parents=True)
    src = str((package / "Sources").resolve())
    report = _report(tmp_path, {f"{src}/A.swift": (94, 100), f"{src}/B.swift": (0, 0)})
    assert swift_coverage.main([str(report), str(package)]) == 1
    assert swift_coverage.main([str(report), str(package), "--minimum", "90"]) == 0


def test_an_unreadable_or_empty_report_cannot_run(tmp_path):
    package = tmp_path / "P"
    (package / "Sources").mkdir(parents=True)
    assert swift_coverage.main([str(tmp_path / "missing.json"), str(package)]) == 2
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    assert swift_coverage.main([str(tmp_path / "bad.json"), str(package)]) == 2
    report = _report(tmp_path, {"/elsewhere/A.swift": (1, 1)})
    assert swift_coverage.main([str(report), str(package)]) == 2  # no own source lines
