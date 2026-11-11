"""Öffentliche API von Stickler. CLI und spätere GTK-Oberfläche nutzen nur diese Funktionen."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

from stickler import adapters, runner
from stickler.classes import load_schemes
from stickler.datasets import mdb
from stickler.results import summarize, write_csv

DATASETS = ("mdb",)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_ROOT = PROJECT_ROOT / "adapters"
CONFIG = PROJECT_ROOT / "config" / "benchmark.yaml"
CLASSES = PROJECT_ROOT / "config" / "classes.yaml"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"
RESULTS_DIR = PROJECT_ROOT / "results"


@dataclass(frozen=True)
class BenchmarkConfig:
    datasets: list[str]
    separators: list[str]
    transcribers: list[str]
    device: str
    schemes: list[str]


def load_benchmark_config(path: Path = CONFIG) -> BenchmarkConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [k for k in ("datasets", "separators", "transcribers") if not raw.get(k)]
    if missing:
        raise ValueError(f"{path.name}: fehlende Einträge: {', '.join(missing)}")
    return BenchmarkConfig(
        datasets=list(raw["datasets"]),
        separators=list(raw["separators"]),
        transcribers=list(raw["transcribers"]),
        device=raw.get("device", "auto"),
        schemes=[str(s) for s in raw.get("schemes", ["5", "3"])],
    )


def load_tracks(name: str, data_dir: Path) -> list[runner.Track]:
    if name == "mdb":
        found = mdb.tracks(data_dir / "mdb")
    else:
        raise ValueError(f"Datensatz {name!r} unbekannt (verfügbar: {', '.join(DATASETS)})")
    if not found:
        raise ValueError(f"Datensatz {name} fehlt: zuerst `stickler fetch {name}`")
    return found


def fetch_dataset(name: str, data_dir: Path) -> int:
    """Lädt einen Datensatz nach `data_dir/<name>`; gibt die Anzahl der Tracks zurück."""
    if name == "mdb":
        return mdb.fetch(data_dir / "mdb")
    raise ValueError(f"Datensatz {name!r} unbekannt (verfügbar: {', '.join(DATASETS)})")


def setup_adapters(adapter: str | None, adapters_root: Path = ADAPTERS_ROOT) -> list[str]:
    """Richtet einen Adapter (oder mit None alle) ein; gibt die eingerichteten IDs zurück."""
    registry = adapters.discover(adapters_root)
    if adapter is not None and adapter not in registry:
        raise ValueError(f"Adapter {adapter!r} unbekannt (verfügbar: {', '.join(registry)})")
    ids = [adapter] if adapter else sorted(registry)
    for adapter_id in ids:
        adapters.setup_adapter(registry[adapter_id])
    return ids


def run_benchmark(
    config_path: Path = CONFIG,
    *,
    device: str | None = None,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    execute: bool = True,
    progress: runner.Progress | None = None,
    cancel: threading.Event | None = None,
) -> list[runner.Record]:
    """Rechnet die Matrix aus der Konfiguration; Ergebnisse landen im Cache."""
    cfg = load_benchmark_config(config_path)
    tracks = {name: load_tracks(name, data_dir) for name in cfg.datasets}
    return runner.run_matrix(
        tracks,
        cfg.separators,
        cfg.transcribers,
        adapters.discover(adapters_root),
        cache_dir,
        device=device or cfg.device,
        execute=execute,
        progress=progress,
        cancel=cancel,
    )


def evaluate_benchmark(
    config_path: Path = CONFIG,
    *,
    device: str | None = None,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    results_dir: Path = RESULTS_DIR,
) -> list[dict]:
    """Bewertet die gecachten Ergebnisse (rechnet nichts); schreibt metrics.csv und summary.csv."""
    cfg = load_benchmark_config(config_path)
    tracks = {name: load_tracks(name, data_dir) for name in cfg.datasets}
    records = run_benchmark(
        config_path,
        device=device,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        execute=False,
    )
    all_schemes = load_schemes(CLASSES)
    schemes = {name: all_schemes[name] for name in cfg.schemes}
    rows = runner.score_records(records, tracks, schemes)
    summary = summarize(rows)
    write_csv(results_dir / "metrics.csv", rows)
    write_csv(results_dir / "summary.csv", summary)
    return summary
