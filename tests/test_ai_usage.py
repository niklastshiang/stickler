"""The README's token and cost figures come from Claude Code's local session logs."""

import importlib.util
import json
from pathlib import Path

_FILE = Path(__file__).parents[1] / "scripts" / "ai_usage.py"
_spec = importlib.util.spec_from_file_location("ai_usage", _FILE)
usage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usage)


def _line(msg_id, model, output, read=0, write=0, inp=0, ts="2026-11-15T10:00:00Z"):
    return json.dumps(
        {
            "timestamp": ts,
            "requestId": f"r-{msg_id}",
            "message": {
                "id": msg_id,
                "role": "assistant",
                "model": model,
                "usage": {
                    "input_tokens": inp,
                    "output_tokens": output,
                    "cache_creation_input_tokens": write,
                    "cache_read_input_tokens": read,
                },
            },
        }
    )


def test_each_response_counts_once_and_costs_follow_the_price_table(tmp_path):
    log = tmp_path / "session.jsonl"
    lines = [
        _line("a", "claude-opus-5-5", 1_000_000, read=10_000_000, write=1_000_000, inp=1_000_000),
        _line("a", "claude-opus-5-5", 1_000_000, read=10_000_000, write=1_000_000, inp=1_000_000),
        _line("b", "claude-fable-5-2", 500_000, ts="2026-11-14T09:00:00Z"),
        '{"type": "user", "message": {"role": "user", "content": "not counted"}}',
        "not json",
    ]
    log.write_text("\n".join(lines), encoding="utf-8")
    totals, first, last = usage.collect([tmp_path])
    assert totals["claude-opus-5-5"]["output"] == 1_000_000  # the duplicate line counts once
    assert (first, last) == ("2026-11-14T09:00:00Z", "2026-11-15T10:00:00Z")
    # Opus 5.5: 1 M input $4 + 1 M cache writes (1 h) $8 + 10 M reads $2 + 1 M output $20
    assert usage.cost("claude-opus-5-5", totals["claude-opus-5-5"]) == 34.0
    assert usage.cost("claude-fable-5-2", totals["claude-fable-5-2"]) == 20.0
    assert usage.cost("unknown-model", totals["claude-opus-5-5"]) is None


def _entry(ts, kind="user"):
    return json.dumps({"timestamp": ts, "type": kind})


def test_a_day_counts_its_tokens_per_model_and_its_active_minutes(tmp_path):
    """The time is the logs' wall clock: gaps up to 15 minutes count as work, longer ones as a
    break, and parallel sessions count once."""
    (tmp_path / "one.jsonl").write_text(
        "\n".join(
            [
                _entry("2026-11-19T10:00:00Z"),
                _line("a", "claude-opus-5-5", 100, read=1000, ts="2026-11-19T10:10:00Z"),
                _entry("2026-11-19T10:20:00Z"),
                _entry("2026-11-19T12:00:00Z"),  # after a break of 100 minutes
                _entry("2026-11-19T12:05:00Z"),
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "parallel.jsonl").write_text(
        "\n".join(
            [
                _line("b", "claude-fable-5-2", 50, ts="2026-11-19T10:05:00Z"),  # inside the first
                _line("c", "claude-fable-5-2", 70, ts="2026-11-20T09:00:00Z"),
                _entry("2026-11-20T09:30:00Z"),  # more than 15 minutes: not counted
            ]
        ),
        encoding="utf-8",
    )
    days = usage.daily([tmp_path])
    assert days["2026-11-19"]["active_minutes"] == 25  # 10:00-10:20 and 12:00-12:05
    assert days["2026-11-19"]["models"]["claude-opus-5-5"]["output"] == 100
    assert days["2026-11-19"]["models"]["claude-opus-5-5"]["cache_read"] == 1000
    assert days["2026-11-19"]["models"]["claude-fable-5-2"]["responses"] == 1
    assert days["2026-11-20"] == {
        "active_minutes": 0,
        "models": {
            "claude-fable-5-2": {
                "responses": 1,
                "input": 0,
                "output": 70,
                "cache_read": 0,
                "cache_write": 0,
            }
        },
    }


def test_recording_keeps_days_the_device_no_longer_has(tmp_path):
    """A device's file in the repository gets the days of its logs; days whose logs are gone
    from the device stay as they were recorded."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "s.jsonl").write_text(
        _line("a", "claude-opus-5-5", 10, ts="2026-11-20T08:00:00Z"), encoding="utf-8"
    )
    out = tmp_path / "usage" / "mac.json"
    out.parent.mkdir()
    old_day = {"active_minutes": 300, "models": {}}
    out.write_text(
        json.dumps({"device": "mac", "days": {"2026-11-13": old_day, "2026-11-20": old_day}}),
        encoding="utf-8",
    )
    usage.record("mac", [logs], out.parent)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["device"] == "mac"
    assert saved["days"]["2026-11-13"] == old_day
    assert saved["days"]["2026-11-20"]["models"]["claude-opus-5-5"]["output"] == 10
    assert list(saved["days"]) == sorted(saved["days"])


def test_a_device_needs_a_plain_name(tmp_path):
    """The name goes into the repository: a short word of one's own, not the host's name."""
    import pytest

    for name in ("", "My Mac", "../x", "mac.local"):
        with pytest.raises(ValueError):
            usage.record(name, [tmp_path], tmp_path)


def test_the_summary_adds_up_every_device(tmp_path):
    for device, minutes, output in (("mac", 90, 1_000_000), ("linux", 30, 500_000)):
        days = {
            "2026-11-19": {
                "active_minutes": minutes,
                "models": {
                    "claude-opus-5-5": {
                        "responses": 2,
                        "input": 0,
                        "output": output,
                        "cache_read": 0,
                        "cache_write": 0,
                    }
                },
            }
        }
        (tmp_path / f"{device}.json").write_text(
            json.dumps({"device": device, "days": days}), encoding="utf-8"
        )
    rows, total = usage.summary(tmp_path)
    assert [row["device"] for row in rows] == ["linux", "mac"]
    assert rows[1]["hours"] == 1.5 and rows[1]["cost"] == 20.0
    assert total == {"hours": 2.0, "cost": 30.0, "tokens": 1_500_000, "responses": 4}


def test_the_logs_are_read_from_the_checkout_and_all_its_worktrees(tmp_path):
    """Claude Code names a project's folder after its path with every character but letters
    and digits as '-', so `.claude/worktrees/x` becomes `--claude-worktrees-x`. A record made
    in the checkout or in one of its worktrees reads all of them: it replaces whole days, so
    reading one folder would drop the other sessions' share of a day."""
    home = tmp_path / "home"
    projects = home / ".claude" / "projects"
    checkout = Path("/Users/me/Developer/my_app")
    names = [
        "-Users-me-Developer-my-app",
        "-Users-me-Developer-my-app--claude-worktrees-mac-x",
        "-Users-me-Developer-my-app--claude-worktrees-win-y",
        "-Users-me-Developer-my-app-old",  # another project
    ]
    for name in names:
        (projects / name).mkdir(parents=True)
    wanted = [projects / name for name in names[:3]]
    assert usage.log_folders(checkout, home) == wanted
    assert usage.log_folders(checkout / ".claude" / "worktrees" / "mac-x", home) == wanted


def test_a_checkout_without_logs_reads_its_own_folder_only(tmp_path):
    folders = usage.log_folders(Path("/Users/me/new"), tmp_path)
    assert folders == [tmp_path / ".claude" / "projects" / "-Users-me-new"]
