"""Results: write CSV and summarise across tracks."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

GROUP = ("dataset", "separator", "transcriber", "scheme")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _f1(tp: int, fp: int, fn: int) -> float:
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def _new_group() -> dict:
    return {
        "counts": defaultdict(lambda: [0, 0, 0]),
        "tracks": set(),
        "errors": set(),
        "sep": 0.0,
        "trans": 0.0,
    }


def summarize(rows: list[dict]) -> list[dict]:
    """Per combination (dataset, separator, transcriber, scheme): sum the counts over all tracks,
    from them F1 per class, micro F1 and macro F1 (classes with reference events)."""
    groups: dict[tuple, dict] = defaultdict(_new_group)
    for r in rows:
        g = groups[tuple(r[k] for k in GROUP)]
        if r["error"]:
            g["errors"].add(r["track"])
            continue
        if r["class"] == "macro":
            continue
        if r["class"] == "micro":
            g["tracks"].add(r["track"])
            g["sep"] += float(r["sep_seconds"])
            g["trans"] += float(r["trans_seconds"])
            continue
        c = g["counts"][r["class"]]
        c[0] += int(r["tp"])
        c[1] += int(r["fp"])
        c[2] += int(r["fn"])
    summary = []
    for key, g in groups.items():
        per_class = {cls: _f1(*c) for cls, c in g["counts"].items()}
        with_ref = [per_class[cls] for cls, c in g["counts"].items() if c[0] + c[2] > 0]
        tp, fp, fn = (sum(c[i] for c in g["counts"].values()) for i in range(3))
        summary.append(
            {
                **dict(zip(GROUP, key, strict=True)),
                "tracks": len(g["tracks"]),
                "errors": len(g["errors"]),
                "micro_f1": _f1(tp, fp, fn),
                "macro_f1": sum(with_ref) / len(with_ref) if with_ref else 0.0,
                **{f"f1_{cls}": f1 for cls, f1 in per_class.items()},
                "sep_seconds": g["sep"],
                "trans_seconds": g["trans"],
            }
        )
    return summary
