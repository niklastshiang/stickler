"""Öffentliche API von Stickler. CLI und spätere GTK-Oberfläche nutzen nur diese Funktionen."""

from __future__ import annotations

from pathlib import Path

from stickler import adapters
from stickler.datasets import mdb

DATASETS = ("mdb",)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_ROOT = PROJECT_ROOT / "adapters"


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
