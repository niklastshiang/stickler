"""Self-contained HTML report over the benchmark summaries (standard library only).

One page: ranking by macro-F1, F1 per class, runtime / RTF / peak RAM and the device, per
config, dataset and class scheme. Inline CSS, no scripts, no external requests.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from html import escape
from pathlib import Path

CLASS_ORDER = ("KD", "SD", "TT", "HH", "CY")
NUMERIC = (
    "tracks",
    "errors",
    "micro_f1",
    "macro_f1",
    "sep_seconds",
    "trans_seconds",
    "audio_seconds",
    "peak_rss_mb",
)
DASH = "&ndash;"

MDB_NOTE = (
    "Some models may have seen MDB Drums during training or evaluation, so the MDB numbers "
    "may be optimistic. The owner's own songs (dataset <code>own</code>) are the honest test."
)

CSS = """
:root { --bg:#fff; --fg:#1b1f24; --muted:#59636e; --line:#d0d7de; --head:#f6f8fa;
  --best:#dafbe1; --warn-bg:#fff8c5; --warn-line:#d4a72c; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0d1117; --fg:#e6edf3; --muted:#8d96a0; --line:#30363d; --head:#161b22;
    --best:#12361f; --warn-bg:#2d2a12; --warn-line:#9e7e1a; }
}
body { background:var(--bg); color:var(--fg); margin:0 auto; padding:1.5rem 1rem 3rem;
  max-width:68rem; font:15px/1.5 system-ui, sans-serif; }
h1 { margin-top:0; } h2 { margin-top:2.5rem; border-bottom:1px solid var(--line); }
h3 { margin-bottom:.2rem; } h4 { margin:1rem 0 .3rem; color:var(--muted); }
.note { background:var(--warn-bg); border-left:4px solid var(--warn-line); padding:.7rem 1rem;
  margin:1rem 0; }
.muted { color:var(--muted); }
.wrap { overflow-x:auto; }
table { border-collapse:collapse; margin:.3rem 0 1rem; font-variant-numeric:tabular-nums; }
th, td { border:1px solid var(--line); padding:.3rem .6rem; text-align:right; }
th { background:var(--head); } td.l, th.l { text-align:left; }
td.best { background:var(--best); font-weight:600; }
"""


def _num(value: str | None) -> float:
    return float(value) if value else 0.0


def read_summary(path: Path) -> list[dict]:
    """Reads one summary.csv; numbers become floats/ints, empty class cells None, columns
    missing in older files get neutral defaults (0.0 / empty device)."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    parsed = []
    for raw in rows:
        row: dict = dict(raw)
        for key in NUMERIC:
            row[key] = _num(raw.get(key, ""))
        for key in ("tracks", "errors"):
            row[key] = int(row[key])
        row["device"] = raw.get("device") or ""
        for key in raw:
            if key.startswith("f1_"):
                row[key] = None if raw[key] == "" else float(raw[key])
        parsed.append(row)
    return parsed


def _rtf(row: dict) -> float | None:
    if row["audio_seconds"] <= 0:
        return None
    return (row["sep_seconds"] + row["trans_seconds"]) / row["audio_seconds"]


def _ram(row: dict) -> float | None:
    return row["peak_rss_mb"] if row["peak_rss_mb"] > 0 else None


def _fmt(value: float | None, spec: str) -> str:
    return DASH if value is None else format(value, spec)


def _gb(value: float | None) -> str:
    return DASH if value is None else f"{value / 1024:.1f} GB"


def _class_columns(rows: list[dict]) -> list[str]:
    found = {k[3:] for r in rows for k, v in r.items() if k.startswith("f1_") and v is not None}
    return sorted(found, key=lambda c: (CLASS_ORDER.index(c) if c in CLASS_ORDER else 99, c))


def _table(rows: list[dict], columns: list[tuple[str, Callable[[dict], object], str, str | None]]):
    """columns: (header, getter, format spec or '' for text, best mode)."""
    best: dict[int, float] = {}
    for i, (_, getter, _, mode) in enumerate(columns):
        values = [v for v in (getter(r) for r in rows) if isinstance(v, float)]
        if mode and values:
            best[i] = max(values) if mode == "max" else min(values)
    head = "".join(
        f'<th class="l">{escape(h)}</th>' if not s else f"<th>{escape(h)}</th>"
        for h, _, s, _ in columns
    )
    body = []
    for r in rows:
        cells = []
        for i, (_, getter, spec, _) in enumerate(columns):
            value = getter(r)
            if not spec:
                cells.append(f'<td class="l">{escape(str(value))}</td>')
                continue
            text = _gb(value) if spec == "gb" else _fmt(value, spec)
            is_best = i in best and isinstance(value, float) and value == best[i]
            cells.append(f'<td class="best">{text}</td>' if is_best else f"<td>{text}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (
        f'<div class="wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _pipeline(row: dict) -> str:
    return f"{row['separator']} + {row['transcriber']}"


def _scheme_section(rows: list[dict]) -> str:
    ranked = sorted(rows, key=lambda r: -r["macro_f1"])
    ranking = _table(
        ranked,
        [
            ("Pipeline", _pipeline, "", None),
            ("Macro-F1", lambda r: r["macro_f1"], ".3f", "max"),
            ("Micro-F1", lambda r: r["micro_f1"], ".3f", "max"),
            ("Tracks", lambda r: r["tracks"], ".0f", None),
            ("Errors", lambda r: r["errors"], ".0f", "min"),
        ],
    )
    classes = _class_columns(ranked)
    per_class = _table(
        ranked,
        [("Pipeline", _pipeline, "", None)]
        + [(c, (lambda r, c=c: r.get(f"f1_{c}")), ".3f", "max") for c in classes],
    )
    runtime = _table(
        ranked,
        [
            ("Pipeline", _pipeline, "", None),
            ("Device", lambda r: r["device"] or "?", "", None),
            ("Separator s", lambda r: r["sep_seconds"], ".0f", None),
            ("Transcriber s", lambda r: r["trans_seconds"], ".0f", None),
            ("RTF", _rtf, ".2f", "min"),
            ("Peak RAM", _ram, "gb", "min"),
        ],
    )
    return (
        f"<h4>Ranking by macro-F1</h4>{ranking}"
        f"<h4>F1 per class</h4>{per_class}"
        f"<h4>Runtime (RTF = processing seconds / audio seconds)</h4>{runtime}"
    )


def _config_section(name: str, rows: list[dict]) -> str:
    parts = [f"<h2>Config: {escape(name)}</h2>"]
    for dataset in sorted({r["dataset"] for r in rows}):
        parts.append(f"<h3>Dataset: {escape(dataset)}</h3>")
        for scheme in sorted({r["scheme"] for r in rows if r["dataset"] == dataset}):
            subset = [r for r in rows if r["dataset"] == dataset and r["scheme"] == scheme]
            parts.append(f"<h3>{escape(scheme)}-class scheme</h3>{_scheme_section(subset)}")
    return "".join(parts)


def _device_note(all_rows: list[dict]) -> str:
    devices = {d for r in all_rows for d in r["device"].split("+") if d}
    if devices and devices <= {"cpu"}:
        return '<p class="muted">Devices: only CPU results exist so far; no GPU comparison.</p>'
    return ""


def render(configs: dict[str, list[dict]]) -> str:
    """The complete HTML page for {config name: summary rows}."""
    all_rows = [r for rows in configs.values() for r in rows]
    if all_rows:
        body = _device_note(all_rows) + "".join(
            _config_section(name, rows) for name, rows in configs.items() if rows
        )
    else:
        body = "<p>No results found. Run <code>stickler eval</code> first.</p>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>Stickler report</title><style>{CSS}</style></head><body>"
        "<h1>Stickler benchmark report</h1>"
        f'<div class="note"><strong>Note:</strong> {MDB_NOTE}</div>'
        f"{body}</body></html>"
    )
