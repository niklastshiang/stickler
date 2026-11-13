"""Command line: only parse arguments, call stickler.api, print the result."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from stickler import api

app = typer.Typer(help="Stickler: benchmark for drum transcription", no_args_is_help=True)

DataDir = Annotated[Path, typer.Option("--data-dir", help="Storage location for datasets")]


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")


@app.command()
def fetch(name: str, data_dir: DataDir = Path("data")) -> None:
    """Download a dataset (mdb) or prepare a local one (enst: unpack the archive first)."""
    try:
        count = api.fetch_dataset(name, data_dir)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{name}: {count} tracks in {data_dir / name}")


@app.command()
def setup(
    adapter: Annotated[str | None, typer.Option(help="Adapter ID; all if omitted")] = None,
    device: Annotated[str, typer.Option(help="cpu | rocm (AMD GPU) | cuda (NVIDIA GPU)")] = "cpu",
) -> None:
    """Build the adapter environment and download weights."""
    try:
        done = api.setup_adapters(adapter, device=device)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Set up: {', '.join(done)}")


Device = Annotated[str | None, typer.Option(help="auto | cpu | gpu (overrides the config)")]


ConfigOpt = Annotated[Path | None, typer.Option("--config", help="default: config/benchmark.yaml")]


@app.command("run")
def run_cmd(device: Device = None, config: ConfigOpt = None) -> None:
    """Compute the benchmark matrix (results are cached)."""

    def progress(done: int, total: int, label: str) -> None:
        typer.echo(f"[{done}/{total}] {label}")

    try:
        records = api.run_benchmark(config or api.CONFIG, device=device, progress=progress)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    failed = [r for r in records if not r.ok]
    typer.echo(f"{len(records)} combinations, {len(failed)} errors")
    for r in failed:
        typer.echo(f"  {r.dataset}/{r.track} {r.separator} → {r.transcriber}: {r.error}")


@app.command("eval")
def eval_cmd(config: ConfigOpt = None) -> None:
    """Score cached results → metrics.csv and summary.csv in results/ (or results/<config>/)."""
    cfg = config or api.CONFIG
    try:
        summary = api.evaluate_benchmark(cfg, results_dir=api.results_dir_for(cfg))
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{'Dataset':10} {'Separator':10} {'Transcriber':14} Scheme  Micro-F1  Macro-F1")
    for s in sorted(summary, key=lambda s: -s["macro_f1"]):
        typer.echo(
            f"{s['dataset']:10} {s['separator']:10} {s['transcriber']:14} {s['scheme']:6} "
            f"{s['micro_f1']:9.3f} {s['macro_f1']:9.3f}  "
            f"({s['tracks']} tracks, {s['errors']} errors)"
        )


@app.command("report")
def report_cmd() -> None:
    """Write results/report.html from all available summary.csv files."""
    path = api.write_report()
    typer.echo(f"Report: {path}")


@app.command("align")
def align_cmd(song: Annotated[str | None, typer.Argument()] = None) -> None:
    """Lay own songs' notes onto the recordings and check them → data/own/<song>/click.wav."""
    try:
        reports = api.align_songs(song)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for r in reports:
        if r.error:
            typer.echo(f"✗ {r.song:24} {r.error}")
            continue
        q = r.quality
        typer.echo(
            f"{'✓' if r.passed else '✗'} {r.song:24} Beats {q['beat_fit']:.3f}  "
            f"coverage {q['coverage']:.3f}  explained {q['explained']:.3f}  "
            f"evaluated {q['evaluated_seconds']:.0f} s"
        )
        typer.echo(
            f"    excluded: {q['excluded_strong']:.1%} of clear onsets, "
            f"{r.excluded_seconds:.0f} s (info)"
        )
        if q.get("score_unmatched", 0) > 0:
            typer.echo(
                f"    score passages not in the recording: {q['score_unmatched']:.1%} (info)"
            )
        for reason in r.reasons:
            typer.echo(f"    {reason}")
        if r.approved_by_ear:
            typer.echo(f"    approved by ear: {r.approved_by_ear}")
        typer.echo(f"    Check: {r.click}")


@app.command("notate")
def notate_cmd(
    audio: Annotated[Path, typer.Argument(help="song (MP3, FLAC, WAV, …)")],
    out: Annotated[Path | None, typer.Option("--out", help="MusicXML file")] = None,
    pipeline: Annotated[str, typer.Option(help="separator+transcriber")] = api.DEFAULT_PIPELINE,
    title: Annotated[str | None, typer.Option(help="default: from the file's tags")] = None,
    artist: Annotated[str | None, typer.Option(help="default: from the file's tags")] = None,
    drums: Annotated[
        Path | None, typer.Option("--drums", help="also save the drum track (.wav/.flac/…)")
    ] = None,
    pdf: Annotated[bool, typer.Option("--pdf/--no-pdf", help="PDF via MuseScore")] = True,
    device: Device = None,
) -> None:
    """Song → drum sheet music (MusicXML, PDF if MuseScore is installed)."""
    try:
        result = api.notate(
            audio,
            out,
            pipeline=pipeline,
            title=title,
            artist=artist,
            pdf=pdf,
            device=device or "auto",
        )
        exported = api.export_drum_track(result.transcription.stem, drums) if drums else None
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    t = result.transcription
    typer.echo(f"Pipeline: {t.separator} + {t.transcriber}, {len(t.hits)} hits")
    typer.echo(f"MusicXML: {result.musicxml}")
    typer.echo(f"PDF: {result.pdf}" if result.pdf else f"PDF: – ({result.pdf_error or 'off'})")
    if exported:
        typer.echo(f"Drum track: {exported}")


@app.command("remote")
def remote_cmd(
    host: Annotated[str, typer.Argument(help="user@address of the GPU machine, e.g. a pod")],
    port: Annotated[int, typer.Option(help="SSH port")] = 22,
    config: ConfigOpt = None,
    pod_id: Annotated[
        str | None, typer.Option("--pod-id", help="RunPod pod to stop afterwards")
    ] = None,
    wipe: Annotated[
        bool,
        typer.Option(
            "--wipe",
            help="delete everything uploaded from the host afterwards, also on failure "
            "(licensed data such as ENST, own songs)",
        ),
    ] = False,
) -> None:
    """Run a benchmark config on a rented GPU and fetch the results (development only)."""
    try:
        api.run_remote(host, port, config or api.CONFIG, pod_id=pod_id, wipe=wipe)
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo("Done: new results are in cache/; run `stickler eval` and `stickler report`.")


@app.command("tune")
def tune_cmd(
    configs: Annotated[
        list[Path], typer.Option("--config", help="tuning data, e.g. config/benchmark.yaml")
    ],
    inputs: Annotated[str, typer.Option(help="separators to fuse, the first is the baseline")] = (
        "none,demucs"
    ),
    name: Annotated[str, typer.Option(help="name of the fusion in the printed YAML")] = "fused",
    step: Annotated[float, typer.Option(help="weight grid step")] = 0.25,
) -> None:
    """Tune ADTOF fusion weights and thresholds per class on cached runs; prints a `fusions`
    entry for a benchmark config."""
    try:
        r = api.tune_fusion(configs, inputs.split(","), step=step)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{r.tracks} tracks, inputs {', '.join(r.inputs)}")
    typer.echo(f"{'class':6} {'ADTOF default':>14} {'tuned':>7}  weights / threshold")
    for cls, t in r.tuned.items():
        d = r.default[cls]
        w = "/".join(f"{x:g}" for x in t.weights)
        typer.echo(f"{cls:6} {d.f1:14.3f} {t.f1:7.3f}  {w} / {t.threshold:g}")
    typer.echo("")
    typer.echo(r.yaml(name))


@app.command("cache-migrate")
def cache_migrate_cmd(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="only report")] = False,
    rekey_from: Annotated[
        Path | None,
        typer.Option(
            "--rekey-from",
            help="digest snapshot (stickler cache-digests) taken before an edit that does not "
            "change behaviour, e.g. a translation; never use it after a real code change",
        ),
    ] = None,
) -> None:
    """Move cache entries to the current (device-independent) keys; nothing is deleted."""
    r = api.migrate_cache(dry_run=dry_run, rekey_from=rekey_from)
    prefix = "would move" if dry_run else "moved"
    typer.echo(
        f"{prefix} {r.moved}, set aside {r.superseded} duplicates and {r.orphaned} unknown "
        f"entries, {r.current} already current"
    )


@app.command("cache-digests")
def cache_digests_cmd(out: Path) -> None:
    """Save every adapter's code digest, before a behaviour-neutral edit (see cache-migrate)."""
    api.save_digests(out)
    typer.echo(f"Digests: {out}")


@app.command("doctor")
def doctor_cmd() -> None:
    """System check: GPU, adapter environments, weights, HF login, MuseScore, datasets."""
    for check in api.run_doctor():
        typer.echo(f"{'✓' if check.ok else '✗'} {check.name:22} {check.detail}")
