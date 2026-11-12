"""Public API of Stickler. The CLI and the later GTK interface only use these functions."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from stickler import adapters, align, audio, doctor, onsets, runner
from stickler.classes import load_schemes
from stickler.datasets import mdb, own
from stickler.results import summarize, write_csv

DATASETS = ("mdb", "own")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_ROOT = PROJECT_ROOT / "adapters"
CONFIG = PROJECT_ROOT / "config" / "benchmark.yaml"
CLASSES = PROJECT_ROOT / "config" / "classes.yaml"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"
RESULTS_DIR = PROJECT_ROOT / "results"
REFERENCES_DIR = PROJECT_ROOT / "references" / "own"


@dataclass(frozen=True)
class BenchmarkConfig:
    datasets: list[str]
    separators: list[str]
    transcribers: list[str]
    device: str
    schemes: list[str]
    timeout: runner.Timeout = None  # seconds per adapter call, overall or per stage


def _parse_limit(stage: str, raw: object) -> float | runner.RelativeLimit:
    """`300` = fixed seconds, `{factor: 10, min: 120}` = 10 × audio duration, at least 120 s."""
    if not isinstance(raw, dict):
        return float(raw)
    if "factor" not in raw:
        raise ValueError(f"timeout.{stage}: relative time limit needs 'factor'")
    return runner.RelativeLimit(factor=float(raw["factor"]), minimum=float(raw.get("min", 0)))


def _parse_timeout(raw: object) -> runner.Timeout:
    if not raw:
        return None
    if isinstance(raw, dict):
        return {str(stage): _parse_limit(str(stage), limit) for stage, limit in raw.items()}
    return float(raw)


def load_benchmark_config(path: Path = CONFIG) -> BenchmarkConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [k for k in ("datasets", "separators", "transcribers") if not raw.get(k)]
    if missing:
        raise ValueError(f"{path.name}: missing entries: {', '.join(missing)}")
    return BenchmarkConfig(
        datasets=list(raw["datasets"]),
        separators=list(raw["separators"]),
        transcribers=list(raw["transcribers"]),
        device=raw.get("device", "auto"),
        schemes=[str(s) for s in raw.get("schemes", ["5", "3"])],
        timeout=_parse_timeout(raw.get("timeout")),
    )


def load_tracks(name: str, data_dir: Path) -> list[runner.Track]:
    if name == "mdb":
        found = mdb.tracks(data_dir / "mdb")
    elif name == "own":
        found = own.tracks(REFERENCES_DIR, data_dir)
        if not found:
            raise ValueError("no own songs with a passed alignment: run `stickler align` first")
        return found
    else:
        raise ValueError(f"Dataset {name!r} unknown (available: {', '.join(DATASETS)})")
    if not found:
        raise ValueError(f"Dataset {name} missing: run `stickler fetch {name}` first")
    return found


def fetch_dataset(name: str, data_dir: Path) -> int:
    """Downloads a dataset to `data_dir/<name>`; returns the number of tracks."""
    if name == "mdb":
        return mdb.fetch(data_dir / "mdb")
    raise ValueError(f"Dataset {name!r} unknown (available: {', '.join(DATASETS)})")


def setup_adapters(
    adapter: str | None, device: str = "cpu", adapters_root: Path = ADAPTERS_ROOT
) -> list[str]:
    """Sets up one adapter (or all with None) for cpu or rocm; returns the IDs.
    For rocm without an adapter given, only adapters with a ROCm declaration are set up."""
    registry = adapters.discover(adapters_root)
    if adapter is not None and adapter not in registry:
        raise ValueError(f"Adapter {adapter!r} unknown (available: {', '.join(registry)})")
    if adapter:
        ids = [adapter]
    elif device == "rocm":
        ids = sorted(i for i, spec in registry.items() if adapters.rocm_config(spec))
    else:
        ids = sorted(registry)
    for adapter_id in ids:
        adapters.setup_adapter(registry[adapter_id], device=device)
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
    """Computes the matrix from the configuration; results end up in the cache."""
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
        timeout=cfg.timeout,
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
    """Scores the cached results (computes nothing); writes metrics.csv and summary.csv."""
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


def run_doctor(
    adapters_root: Path = ADAPTERS_ROOT, data_dir: Path = DATA_DIR
) -> list[doctor.Check]:
    """Checks GPU, adapters, weights, Hugging Face login, MuseScore and datasets."""
    return doctor.run_all(adapters_root, data_dir)


@dataclass(frozen=True)
class AlignReport:
    song: str
    title: str
    passed: bool
    quality: dict
    reasons: list[str]
    excluded_seconds: float  # excluded duration within the song
    click: (
        Path | None
    )  # check WAV: recording on the left, clicks on the reference notes on the right
    error: str | None = None


CLICK_SR = 22050
CLICK_FREQ = {0: 700.0, 1: 1400.0, 2: 2800.0}  # kick, snare/toms, cymbals


def _click_track(song: own.Song, notes: list[tuple[float, int]]) -> Path:
    mix = audio.load_mono(song.audio, sr=CLICK_SR)
    clicks = np.zeros_like(mix)
    t = np.arange(int(0.02 * CLICK_SR)) / CLICK_SR
    for time, pitch in notes:
        burst = 0.6 * np.exp(-t * 200) * np.sin(2 * np.pi * CLICK_FREQ[align._group(pitch)] * t)
        start = int(time * CLICK_SR)
        end = min(len(clicks), start + len(burst))
        if 0 <= start < end:
            clicks[start:end] += burst[: end - start]
    stereo = np.stack([0.7 * mix, clicks], axis=1)
    return audio.write_wav(song.dir / "click.wav", stereo, CLICK_SR)


def _align_song(song: own.Song, registry: dict, cache_dir: Path, device: str) -> AlignReport:
    if not song.score.exists():
        return AlignReport(
            song.id, song.title, False, {}, [], 0.0, None, f"Score missing: {song.score}"
        )
    stem = runner.cached_or_run(registry["demucs"], song.audio, cache_dir, device, True)
    beats = runner.cached_or_run(registry["beat_this"], song.audio, cache_dir, device, True)
    for step in (stem, beats):
        if not step.ok:
            return AlignReport(song.id, song.title, False, {}, [], 0.0, None, step.error)
    times, flux = onsets.band_flux(audio.load_mono(stem.output), 22050)
    beat_times = np.array(json.loads(beats.output.read_text(encoding="utf-8"))["beats"])
    result = align.align(align.read_score(song.score), beat_times, times, flux, song.exclude)
    notes = [
        (float(t), p)
        for t, (_, p) in zip(result.mapped_times, align.read_score(song.score).notes, strict=True)
        if not np.isnan(t) and not any(a <= t < b for a, b in result.excluded)
    ]
    q = result.quality
    quality = {k: round(getattr(q, k), 4) for k in align.THRESHOLDS}
    own.save_alignment(
        song,
        notes=notes,
        excluded=result.excluded,
        quality=quality,
        reasons=q.reasons,
        shift=result.shift,
    )
    end = audio.duration(song.audio)
    excluded_seconds = sum(min(b, end) - a for a, b in result.excluded if a < end)
    return AlignReport(
        song.id,
        song.title,
        q.passed,
        quality,
        q.reasons,
        excluded_seconds,
        _click_track(song, notes),
    )


def align_songs(
    song: str | None = None,
    *,
    references_dir: Path | None = None,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    device: str = "auto",
) -> list[AlignReport]:
    """Lays the notes of own songs onto the recordings and checks the quality (Demucs stem and
    Beat This! beats come from the cache). Only passed songs go into the benchmark."""
    found = own.songs(references_dir or REFERENCES_DIR, data_dir)
    if song is not None:
        found = [s for s in found if s.id == song]
        if not found:
            raise ValueError(f"Song {song!r} unknown (references/own/{song}.yaml missing)")
    registry = adapters.discover(adapters_root)
    return [_align_song(s, registry, cache_dir, device) for s in found]
