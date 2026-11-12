"""Public API of Stickler. The CLI and the later GTK interface only use these functions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from stickler import (
    adapters,
    align,
    audio,
    cachemigration,
    doctor,
    musescore,
    notation,
    onsets,
    remote,
    report,
    runner,
)
from stickler.classes import load_schemes
from stickler.datasets import mdb, own
from stickler.midi import read_drum_hits
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
# Best pipeline in the first sample (MDB Punk); revisit once the benchmark has finished.
DEFAULT_PIPELINE = "demucs+adtof"


@dataclass(frozen=True)
class BenchmarkConfig:
    datasets: list[str]
    separators: list[str]
    transcribers: list[str]
    device: str
    schemes: list[str]
    timeout: runner.Timeout = None  # seconds per adapter call, overall or per stage
    skip: frozenset[tuple[str, str]] = frozenset()  # (separator, transcriber) pairs not run


def _parse_skip(raw: list) -> frozenset[tuple[str, str]]:
    """`["none+muscriptor_m", …]` → {("none", "muscriptor_m"), …}."""
    pairs = []
    for item in raw:
        parts = str(item).split("+")
        if len(parts) != 2:
            raise ValueError(f"skip: expected 'separator+transcriber', got {item!r}")
        pairs.append((parts[0], parts[1]))
    return frozenset(pairs)


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
        skip=_parse_skip(raw.get("skip") or []),
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
        skip=cfg.skip,
    )


def results_dir_for(config_path: Path) -> Path:
    """results/ for the default config, results/<config name>/ for any other."""
    if config_path.resolve() == CONFIG.resolve():
        return RESULTS_DIR
    return RESULTS_DIR / config_path.stem


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


def write_report(config_paths: list[Path] | None = None, results_dir: Path = RESULTS_DIR) -> Path:
    """Writes `report.html` into `results_dir` from the available summary.csv files and
    returns its path. Without `config_paths`: the default config plus every subfolder of
    `results_dir` that has a summary.csv; otherwise the given configs' result folders."""
    if config_paths is None:
        folders = {"default": results_dir}
        folders.update({p.name: p for p in sorted(results_dir.glob("*/")) if p.is_dir()})
    else:
        folders = {}
        for p in config_paths:
            is_default = p.resolve() == CONFIG.resolve()
            folders["default" if is_default else p.stem] = (
                results_dir if is_default else results_dir / p.stem
            )
    configs = {
        name: report.read_summary(folder / "summary.csv")
        for name, folder in folders.items()
        if (folder / "summary.csv").is_file()
    }
    path = results_dir / "report.html"
    results_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(report.render(configs), encoding="utf-8")
    return path


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
    approved_by_ear: str | None = None  # owner overrode failed checks after listening


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
    info = ["excluded_strong", "score_unmatched"]
    quality = {k: round(getattr(q, k), 4) for k in [*align.THRESHOLDS, *info]}
    own.save_alignment(
        song,
        notes=notes,
        excluded=result.excluded,
        quality=quality,
        reasons=q.reasons,
        shift=result.shift,
        approved_by_ear=song.approved_by_ear,
    )
    end = audio.duration(song.audio)
    excluded_seconds = sum(min(b, end) - a for a, b in result.excluded if a < end)
    return AlignReport(
        song.id,
        song.title,
        q.passed or bool(song.approved_by_ear),
        quality,
        q.reasons,
        excluded_seconds,
        _click_track(song, notes),
        approved_by_ear=song.approved_by_ear if not q.passed else None,
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


@dataclass(frozen=True)
class SongTranscription:
    audio: Path
    separator: str
    transcriber: str
    stem: Path  # separated drum track (the mix itself for separator "none")
    midi: Path
    beats: list[float]
    downbeats: list[float]
    hits: list[tuple[float, int, int]]  # (seconds, GM pitch, velocity)


@dataclass(frozen=True)
class Notation:
    musicxml: Path
    pdf: Path | None
    pdf_error: str | None  # why there is no PDF (MuseScore missing or failed)
    transcription: SongTranscription


def _parse_pipeline(pipeline: str, registry: dict) -> tuple[str, str]:
    parts = pipeline.split("+")
    if len(parts) != 2:
        raise ValueError(f"pipeline must look like 'separator+transcriber', got {pipeline!r}")
    sep, tr = parts
    if sep != "none" and (sep not in registry or registry[sep].stage != "separators"):
        raise ValueError(f"pipeline: unknown separator {sep!r}")
    if tr not in registry or registry[tr].stage != "transcribers":
        raise ValueError(f"pipeline: unknown transcriber {tr!r}")
    if sep == "none" and registry[tr].needs_stem:
        raise ValueError(f"pipeline: {tr} needs a separated drum stem, not the mix")
    return sep, tr


def _result(step: adapters.AdapterResult) -> Path:
    if not step.ok:
        raise RuntimeError(step.error or "adapter failed")
    return step.output


def transcribe_song(
    audio_path: Path,
    pipeline: str = DEFAULT_PIPELINE,
    *,
    device: str = "auto",
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
) -> SongTranscription:
    """Separation, transcription and beat tracking for one song (cached like the benchmark)."""
    registry = adapters.discover(adapters_root)
    sep, tr = _parse_pipeline(pipeline, registry)
    stem = audio_path
    if sep != "none":
        stem = _result(runner.cached_or_run(registry[sep], audio_path, cache_dir, device, True))
    midi = _result(runner.cached_or_run(registry[tr], stem, cache_dir, device, True))
    beats_file = _result(
        runner.cached_or_run(registry["beat_this"], audio_path, cache_dir, device, True)
    )
    beats = json.loads(beats_file.read_text(encoding="utf-8"))
    return SongTranscription(
        audio=audio_path,
        separator=sep,
        transcriber=tr,
        stem=stem,
        midi=midi,
        beats=list(beats["beats"]),
        downbeats=list(beats["downbeats"]),
        hits=read_drum_hits(midi),
    )


def notate(
    audio_path: Path,
    out: Path | None = None,
    *,
    pipeline: str = DEFAULT_PIPELINE,
    title: str | None = None,
    artist: str | None = None,
    pdf: bool = True,
    device: str = "auto",
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    results_dir: Path = RESULTS_DIR,
) -> Notation:
    """Song → drum sheet music as MusicXML (default: results/notation/<song>.musicxml), plus a
    PDF next to it if MuseScore is installed. Title and artist default to the file's tags."""
    t = transcribe_song(
        audio_path, pipeline, device=device, cache_dir=cache_dir, adapters_root=adapters_root
    )
    target = out or results_dir / "notation" / f"{audio_path.stem}.musicxml"
    target.parent.mkdir(parents=True, exist_ok=True)
    found = audio.tags(audio_path) if title is None or artist is None else {}
    xml = notation.to_musicxml(
        t.hits,
        t.beats,
        t.downbeats,
        title=title or found.get("title") or audio_path.stem,
        artist=artist if artist is not None else found.get("artist", ""),
    )
    target.write_text(xml, encoding="utf-8")
    pdf_path, pdf_error = None, None
    if pdf:
        command = musescore.find()
        if command is None:
            pdf_error = "MuseScore not installed (Flathub: org.musescore.MuseScore)"
        else:
            try:
                pdf_path = musescore.export_pdf(target, target.with_suffix(".pdf"), command)
            except RuntimeError as exc:
                pdf_error = str(exc)
    return Notation(target, pdf_path, pdf_error, t)


DRUM_TRACK_FORMATS = (".wav", ".flac", ".ogg", ".mp3")


def export_drum_track(stem: Path, dest: Path) -> Path:
    """Saves the separated drum track: WAV is copied, other formats are encoded with ffmpeg."""
    if dest.suffix.lower() not in DRUM_TRACK_FORMATS:
        raise ValueError(
            f"unsupported format {dest.suffix!r} (use {', '.join(DRUM_TRACK_FORMATS)})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() == ".wav":
        shutil.copyfile(stem, dest)
        return dest
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(stem), str(dest)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg: {dest.name}: {proc.stderr.strip()}")
    return dest


RUNPOD_KEY_FILE = Path.home() / ".config" / "stickler" / "runpod.env"


def runpod_api_key() -> str:
    """RUNPOD_API_KEY from the environment, else from RUNPOD_KEY_FILE. The file is read as
    text, never executed: either the bare key or `[export ]RUNPOD_API_KEY=<key>`."""
    if key := os.environ.get("RUNPOD_API_KEY", ""):
        return key
    if not RUNPOD_KEY_FILE.exists():
        return ""
    for line in RUNPOD_KEY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        value = line.split("=", 1)[1] if "=" in line else line
        return value.strip().strip("'\"")
    return ""


def run_remote(host: str, port: int, config_path: Path, *, pod_id: str | None = None) -> None:
    """Runs a benchmark config on a rented GPU over SSH and brings the new cache entries
    back (development only). Secrets come from the environment: HF_TOKEN (or the file from
    `hf auth login`) and, to stop the pod afterwards, the RunPod key (`runpod_api_key`)."""
    api_key = runpod_api_key()
    if pod_id and not api_key:
        raise ValueError(f"--pod-id needs the RunPod API key (RUNPOD_API_KEY or {RUNPOD_KEY_FILE})")
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token and doctor.HF_TOKEN_FILE.exists():
        hf_token = doctor.HF_TOKEN_FILE.read_text(encoding="utf-8").strip()
    config = config_path.resolve()
    plan = remote.sync_plan(
        config,
        project_root=PROJECT_ROOT,
        references_dir=REFERENCES_DIR,
        data_dir=DATA_DIR,
        home=Path.home(),
    )
    remote.run_remote(
        remote.Host(host, port),
        str(config.relative_to(PROJECT_ROOT)),
        remote.adapters_for(config),
        plan,
        project_root=PROJECT_ROOT,
        home=Path.home(),
        hf_token=hf_token,
        stop=(lambda: remote.stop_pod(pod_id, api_key)) if pod_id else None,
    )


def migrate_cache(
    *,
    dry_run: bool = False,
    cache_dir: Path = CACHE_DIR,
    data_dir: Path = DATA_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    rekey_from: Path | None = None,
) -> cachemigration.Report:
    """Moves cache entries from the old device-dependent keys to the current keys (see
    stickler.cachemigration). Inputs: MDB mixes and stems, the own songs' recordings.
    `rekey_from`: digest snapshot (save_digests) taken before a behaviour-neutral edit."""
    inputs: list[Path] = []
    for track in mdb.tracks(data_dir / "mdb"):
        inputs += [track.mix, track.drums]
    inputs += [song.audio for song in own.songs(REFERENCES_DIR, data_dir)]
    previous = cachemigration.load_digests(rekey_from) if rekey_from else None
    return cachemigration.migrate(
        cache_dir,
        adapters.discover(adapters_root),
        inputs,
        dry_run=dry_run,
        previous_digests=previous,
    )


def save_digests(path: Path, adapters_root: Path = ADAPTERS_ROOT) -> None:
    """Snapshot of every adapter's code digest, for `migrate_cache(rekey_from=...)`."""
    cachemigration.save_digests(path, adapters.discover(adapters_root))
