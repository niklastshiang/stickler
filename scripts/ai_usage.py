"""Tokens and API-equivalent cost of building Stickler with Claude Code, for the README.

Claude Code keeps each session's log under ~/.claude/projects/<the project's path>/, with the
token usage of every response. This sums them per model (a response split over several log lines
counts once) and prices them with Anthropic's API prices. On a subscription the real cost
differs; the logs on this machine are the only source, so earlier sessions that are gone are
missing.

    uv run python scripts/ai_usage.py           # this machine's logs, as a table
    uv run python scripts/ai_usage.py --record mac  # this machine's days into docs/usage/mac.json
    uv run python scripts/ai_usage.py --summary  # every device recorded in docs/usage/

Every computer that works on Stickler records its days into the repository (owner, 2026-11-20;
CLAUDE.md), so the figures of all of them can be added up: the tokens per model and day, and
the active time, the logs' wall clock with gaps of up to 15 minutes counted as work.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import re
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


RECORDS = ROOT / "docs" / "usage"
BREAK = datetime.timedelta(minutes=15)  # a longer gap between log entries is a break
DEVICE = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")
FIELDS = ("responses", "input", "output", "cache_read", "cache_write")


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


def _entries(folders: list[Path]):
    for folder in folders:
        for log in sorted(folder.rglob("*.jsonl")):
            for line in log.open(encoding="utf-8", errors="replace"):
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    yield entry


def _moment(stamp: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _active_minutes(stamps: list[datetime.datetime]) -> int:
    moments = sorted(stamps)
    worked = sum(
        (
            later - earlier
            for earlier, later in zip(moments, moments[1:], strict=False)
            if later - earlier <= BREAK
        ),
        datetime.timedelta(),
    )
    return round(worked.total_seconds() / 60)


def daily(folders: list[Path]) -> dict[str, dict]:
    """Per day (UTC): the active minutes over all sessions at once, and each model's tokens
    (a response split over several log lines counts once)."""
    stamps: dict[str, list[datetime.datetime]] = collections.defaultdict(list)
    models: dict[str, dict[str, collections.Counter]] = collections.defaultdict(
        lambda: collections.defaultdict(collections.Counter)
    )
    seen: set[tuple] = set()
    for entry in _entries(folders):
        stamp = entry.get("timestamp")
        if not isinstance(stamp, str):
            continue
        day = stamp[:10]
        stamps[day].append(_moment(stamp))
        message = entry.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if "usage" not in message:
            continue
        key = (message.get("id"), entry.get("requestId"))
        if key in seen:
            continue
        seen.add(key)
        counts = models[day][message.get("model", "?")]
        for kind, field in KINDS.items():
            counts[kind] += message["usage"].get(field) or 0
        counts["responses"] += 1
    return {
        day: {
            "active_minutes": _active_minutes(stamps[day]),
            "models": {
                model: {field: counts[field] for field in FIELDS}
                for model, counts in sorted(models[day].items())
            },
        }
        for day in sorted(stamps)
    }


def record(device: str, folders: list[Path], records: Path = RECORDS) -> Path:
    """Writes this device's days into `records/<device>.json`: the days its logs have now
    replace the recorded ones, days whose logs are gone stay."""
    if not DEVICE.fullmatch(device):
        raise ValueError(f"{device!r}: a short name of lowercase letters, digits and '-'")
    out = records / f"{device}.json"
    days = {}
    if out.exists():
        days = json.loads(out.read_text(encoding="utf-8")).get("days", {})
    days.update(daily(folders))
    data = {"device": device, "days": dict(sorted(days.items()))}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out


def summary(records: Path = RECORDS) -> tuple[list[dict], dict]:
    """Every recorded device's hours, tokens, responses and API cost, and their sum."""
    rows = []
    for path in sorted(records.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        minutes = tokens = responses = 0
        dollars = 0.0
        for day in data["days"].values():
            minutes += day["active_minutes"]
            for model, counts in day["models"].items():
                counter = collections.Counter(counts)
                tokens += sum(counter[kind] for kind in KINDS)
                responses += counter["responses"]
                dollars += cost(model, counter) or 0.0
        days = sorted(data["days"])
        rows.append(
            {
                "device": data["device"],
                "from": days[0] if days else None,
                "to": days[-1] if days else None,
                "hours": round(minutes / 60, 1),
                "tokens": tokens,
                "responses": responses,
                "cost": round(dollars, 2),
            }
        )
    rows.sort(key=lambda row: row["device"])
    total = {
        "hours": round(sum(row["hours"] for row in rows), 1),
        "cost": round(sum(row["cost"] for row in rows), 2),
        "tokens": sum(row["tokens"] for row in rows),
        "responses": sum(row["responses"] for row in rows),
    }
    return rows, total


def cost(model: str, counts: collections.Counter) -> float | None:
    prices = PRICES.get(model)
    if prices is None:
        return None
    return round(sum(counts[kind] * prices[kind] for kind in KINDS) / 1_000_000, 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", metavar="DEVICE", help="write this machine's days")
    parser.add_argument("--summary", action="store_true", help="add up every recorded device")
    args = parser.parse_args()
    if args.record:
        out = record(args.record, [log_folder()])
        days = len(json.loads(out.read_text(encoding="utf-8"))["days"])
        print(f"{out.relative_to(ROOT)}: {days} days")
        return 0
    if args.summary:
        rows, total = summary()
        print("| Device | Days | Active time | Responses | Tokens | Cost (API, USD) |")
        print("|---|---|---:|---:|---:|---:|")
        for row in rows:
            print(
                f"| {row['device']} | {row['from']} to {row['to']} | {row['hours']:,} h | "
                f"{row['responses']:,} | {row['tokens'] / 1e6:,.0f} M | {row['cost']:,.2f} |"
            )
        print(
            f"| **Total** | | {total['hours']:,} h | {total['responses']:,} | "
            f"{total['tokens'] / 1e6:,.0f} M | {total['cost']:,.2f} |"
        )
        return 0
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
