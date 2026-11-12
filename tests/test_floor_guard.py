"""Tests für scripts/floor_guard.py: jeder Floor-Verstoß wird erkannt, saubere Diffs nicht."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

import stickler

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("floor_guard", ROOT / "scripts" / "floor_guard.py")
assert _spec and _spec.loader
floor_guard = importlib.util.module_from_spec(_spec)
sys.modules["floor_guard"] = floor_guard  # nötig für @dataclass
_spec.loader.exec_module(floor_guard)


def diff_for(
    path: str, added: list[str] = (), removed: list[str] = (), *, new: bool = False
) -> str:
    old = "/dev/null" if new else f"a/{path}"
    lines = [f"diff --git a/{path} b/{path}", f"--- {old}", f"+++ b/{path}", "@@ -1 +1 @@"]
    lines += [f"-{t}" for t in removed] + [f"+{t}" for t in added]
    return "\n".join(lines)


def rules(diff: str) -> set[str]:
    return {rule for rule, _, _ in floor_guard.check(diff)}


def test_package_version():
    assert stickler.__version__ == "0.1.0"


def test_clean_diff_passes():
    assert (
        floor_guard.check(diff_for("src/stickler/x.py", ["def f() -> int:", "    return 1"])) == []
    )


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        ("x = 1  # noqa: E501", "silenced-checker"),
        ("y = f()  # type: ignore", "silenced-checker"),
        ("if debug:  # pragma: no cover", "silenced-checker"),
        ("    raise NotImplementedError", "unfinished-work"),
        ("except Exception: pass", "unfinished-work"),
        ("# TODO später", "unfinished-work"),
        ("@pytest.mark.skip(reason='rot')", "test-made-easier"),
        ("    pytest.skip('später')", "test-made-easier"),
    ],
)
def test_added_violations_are_flagged(line, rule):
    assert rule in rules(diff_for("src/stickler/x.py", [line]))


def test_secret_is_flagged_but_redacted():
    token = "hf_" + "A" * 34
    findings = floor_guard.check(diff_for("src/stickler/x.py", [f'TOKEN = "{token}"']))
    assert [(r, t) for r, _, t in findings] == [("secret", "<redacted>")]
    assert token not in str(findings)


def test_binary_file_added_is_flagged():
    assert "binary-in-git" in rules(diff_for("data/song.mp3", ["x"], new=True))


def test_deleted_test_file_is_flagged():
    diff = "\n".join(
        ["diff --git a/tests/test_a.py b/tests/test_a.py", "--- a/tests/test_a.py", "+++ /dev/null"]
    )
    assert "test-deleted" in rules(diff)


def test_removed_assertion_is_flagged():
    assert "assertion-removed" in rules(diff_for("tests/test_a.py", [], ["    assert f() == 1"]))


def test_constraints_threshold_loosened_is_flagged():
    old = "| Coverage | line coverage >= 80% | pytest | task end |"
    new = "| Coverage | line coverage >= 70% | pytest | task end |"
    assert "threshold-loosened" in rules(diff_for("CONSTRAINTS.md", [new], [old]))


def test_constraints_threshold_tightened_is_silent():
    old = "| Coverage | line coverage >= 80% | pytest | task end |"
    new = "| Coverage | line coverage >= 90% | pytest | task end |"
    assert rules(diff_for("CONSTRAINTS.md", [new], [old])) == set()


@pytest.mark.parametrize(
    ("before", "after", "found"), [("80", "95", set()), ("80", "70", {"threshold-loosened"})]
)
def test_fail_under_is_a_minimum(before, after, found):
    row = "| Coverage | >= {0}% | `pytest --cov --cov-fail-under={0}` | task end |"
    diff = diff_for("CONSTRAINTS.md", [row.format(after)], [row.format(before)])
    assert rules(diff) == found


def test_constraints_rule_removed_is_flagged():
    assert "rule-removed" in rules(
        diff_for("CONSTRAINTS.md", [], ["| Lint | Zero errors | ruff | edit |"])
    )


def test_new_exception_is_flagged():
    row = "| W1 | coverage | src/x.py | Grund | owner | 2027-01-01 |"
    assert "new-exception" in rules(diff_for("CONSTRAINTS.md", [row]))


def test_cli_exit_code_two_outside_git(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "floor_guard.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_docs_may_name_patterns():
    assert (
        rules(
            diff_for("CONSTRAINTS.md", ["- No new suppression comments: `# noqa`, `pytest.skip(`"])
        )
        == set()
    )


def test_changed_assertion_is_not_a_removal():
    diff = diff_for("tests/test_a.py", ["    assert f() == {1, 2}"], ["    assert f() == {1}"])
    assert rules(diff) == set()


def test_net_loss_of_assertions_is_flagged():
    diff = diff_for(
        "tests/test_a.py", ["    assert f() == 1"], ["    assert f() == 1", "    assert g() == 2"]
    )
    assert "assertion-removed" in rules(diff)
