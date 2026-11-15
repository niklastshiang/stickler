"""Tokens and API-equivalent cost of building Stickler with Claude Code, for the README.

Claude Code keeps each session's log under ~/.claude/projects/<the project's path>/, with the
token usage of every response. This sums them per model (a response split over several log lines
counts once) and prices them with Anthropic's API prices. On a subscription the real cost
differs; the logs on this machine are the only source, so earlier sessions that are gone are
missing.

    uv run python scripts/ai_usage.py           # before a release; the README takes the table
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# USD per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing
# (checked 2026-11-15). Claude Code caches for an hour, so cache writes use the 1 h price.
PRICES = {
    "claude-opus-5-5": {"input": 4.0, "cache_write": 8.0, "cache_read": 0.20, "output": 20.0},
    "claude-fable-5-2": {"input": 8.0, "cache_write": 16.0, "cache_read": 0.20, "output": 40.0},
}
KINDS = {
    "input": "input_tokens",
    "cache_write": "cache_creation_input_tokens",
    "cache_read": "cache_read_input_tokens",
    "output": "output_tokens",
}


def log_folder(project: Path = ROOT) -> Path:
    """Claude Code names a project's folder after its path, with '/' and '_' as '-'."""
    name = str(project).replace("/", "-").replace("_", "-")
    return Path.home() / ".claude" / "projects" / name


def collect(folders: list[Path]) -> tuple[dict[str, collections.Counter], str | None, str | None]:
    totals: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    seen: set[tuple] = set()
    first = last = None
    for folder in folders:
        for log in sorted(folder.rglob("*.jsonl")):
            for line in log.open(encoding="utf-8", errors="replace"):
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                message = entry.get("message") if isinstance(entry, dict) else None
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                if "usage" not in message:
                    continue
                key = (message.get("id"), entry.get("requestId"))
                if key in seen:
                    continue
                seen.add(key)
                counts = totals[message.get("model", "?")]
                for kind, field in KINDS.items():
                    counts[kind] += message["usage"].get(field) or 0
                counts["responses"] += 1
                stamp = entry.get("timestamp")
                if stamp:
                    first = min(first or stamp, stamp)
                    last = max(last or stamp, stamp)
    return totals, first, last


def cost(model: str, counts: collections.Counter) -> float | None:
    prices = PRICES.get(model)
    if prices is None:
        return None
    return round(sum(counts[kind] * prices[kind] for kind in KINDS) / 1_000_000, 2)


def main() -> int:
    totals, first, last = collect([log_folder()])
    print(f"Sessions logged from {first} to {last}\n")
    print("| Model | Responses | Output tokens | Cache read | Cache written | Cost (API, USD) |")
    print("|---|---:|---:|---:|---:|---:|")
    total = 0.0
    for model, counts in sorted(totals.items(), key=lambda kv: -kv[1]["output"]):
        price = cost(model, counts)
        total += price or 0.0
        shown = f"{price:,.2f}" if price is not None else "no price"
        print(
            f"| {model} | {counts['responses']:,} | {counts['output']:,} | "
            f"{counts['cache_read']:,} | {counts['cache_write']:,} | {shown} |"
        )
    print(f"\nTotal: about {total:,.0f} USD at API prices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
