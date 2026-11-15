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
