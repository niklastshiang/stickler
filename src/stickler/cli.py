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


Device = Annotated[str | None, typer.Option(help="auto | cpu | gpu (überschreibt die Config)")]


@app.command("run")
def run_cmd(device: Device = None) -> None:
    """Benchmark-Matrix rechnen (Ergebnisse werden gecacht)."""

    def progress(done: int, total: int, label: str) -> None:
        typer.echo(f"[{done}/{total}] {label}")

    try:
        records = api.run_benchmark(api.CONFIG, device=device, progress=progress)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(1) from exc
    failed = [r for r in records if not r.ok]
    typer.echo(f"{len(records)} Kombinationen, {len(failed)} Fehler")
    for r in failed:
        typer.echo(f"  {r.dataset}/{r.track} {r.separator} → {r.transcriber}: {r.error}")


@app.command("eval")
def eval_cmd() -> None:
    """Gecachte Ergebnisse bewerten → results/metrics.csv und results/summary.csv."""
    try:
        summary = api.evaluate_benchmark(api.CONFIG)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{'Datensatz':10} {'Separator':10} {'Transkriber':14} Schema  Micro-F1  Macro-F1")
    for s in sorted(summary, key=lambda s: -s["macro_f1"]):
        typer.echo(
            f"{s['dataset']:10} {s['separator']:10} {s['transcriber']:14} {s['scheme']:6} "
            f"{s['micro_f1']:9.3f} {s['macro_f1']:9.3f}  "
            f"({s['tracks']} Tracks, {s['errors']} Fehler)"
        )
