"""Kommandozeile: nur Argumente parsen, stickler.api aufrufen, Ergebnis ausgeben."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from stickler import api

app = typer.Typer(help="Stickler: Benchmark für Schlagzeug-Transkription", no_args_is_help=True)

DataDir = Annotated[Path, typer.Option("--data-dir", help="Ablage für Datensätze")]


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")


@app.command()
def fetch(name: str, data_dir: DataDir = Path("data")) -> None:
    """Datensatz herunterladen (z. B. mdb)."""
    try:
        count = api.fetch_dataset(name, data_dir)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{name}: {count} Tracks in {data_dir / name}")


@app.command()
def setup(
    adapter: Annotated[str | None, typer.Option(help="Adapter-ID; ohne Angabe alle")] = None,
) -> None:
    """Adapter-Umgebung bauen und Gewichte laden."""
    try:
        done = api.setup_adapters(adapter)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Eingerichtet: {', '.join(done)}")
