"""Öffentliche API von Stickler. CLI und spätere GTK-Oberfläche nutzen nur diese Funktionen."""

from __future__ import annotations

from pathlib import Path

from stickler.datasets import mdb

DATASETS = ("mdb",)


def fetch_dataset(name: str, data_dir: Path) -> int:
    """Lädt einen Datensatz nach `data_dir/<name>`; gibt die Anzahl der Tracks zurück."""
    if name == "mdb":
        return mdb.fetch(data_dir / "mdb")
    raise ValueError(f"Datensatz {name!r} unbekannt (verfügbar: {', '.join(DATASETS)})")
