"""Public API of Stickler. The CLI and the later GTK interface only use these functions."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from stickler import (
    adapters,
    align,
    audio,
    cachemigration,
    combine,
    doctor,
    errors,
    fusion,
    grid,
    musescore,
    notation,
    onsets,
    remote,
    report,
    runner,
    vote,
)
from stickler.classes import load_schemes, onsets_from_notes
from stickler.datasets import enst, mdb, own
from stickler.midi import read_drum_hits
from stickler.results import summarize, write_csv

DATASETS = ("mdb", "enst", "own")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_ROOT = PROJECT_ROOT / "adapters"
CONFIG = PROJECT_ROOT / "config" / "benchmark.yaml"
CLASSES = PROJECT_ROOT / "config" / "classes.yaml"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"
RESULTS_DIR = PROJECT_ROOT / "results"
REFERENCES_DIR = PROJECT_ROOT / "references" / "own"
# Modes of `notate` (docs/report.md): which pipeline provides which class of the 5-class scheme.
# Fast: ADTOF on the mix. Quality: the benchmark's best combination (own songs and MDB).
ALL_CLASSES = ("KD", "SD", "TT", "HH", "CY")
MODES: dict[str, dict[str, tuple[str, ...]]] = {
    "fast": {"none+adtof": ALL_CLASSES},
    "quality": {"demucs+muscriptor_m": ("KD", "SD", "TT"), "none+adtof": ("HH", "CY")},
}
DEFAULT_MODE = "fast"
DRUM_TRACK_SEPARATOR = "demucs"  # for --drums when the mode itself separates nothing


@dataclass(frozen=True)
class BenchmarkConfig:
    datasets: list[str]
    separators: list[str]
    transcribers: list[str]
    device: str
    schemes: list[str]
    timeout: runner.Timeout = None  # seconds per adapter call, overall or per stage
    skip: frozenset[tuple[str, str]] = frozenset()  # (separator, transcriber) pairs not run
    combos: dict = field(default_factory=dict)  # combined pipelines (stickler.combine)
    fusions: dict = field(default_factory=dict)  # fused ADTOF activations (stickler.fusion)
    grid: list = field(default_factory=list)  # pipelines also scored on the beat grid
    consensus: grid.Consensus | None = None  # vote across repeated bars ("@rep")
    simplify: bool = False  # similar bars given their common pattern ("@simple")
    votes: dict = field(default_factory=dict)  # k of n pipelines must agree (stickler.vote)


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
        combos=dict(raw.get("combos") or {}),
        fusions=dict(raw.get("fusions") or {}),
        votes=dict(raw.get("votes") or {}),
        grid=list(raw.get("grid") or []),
        consensus=grid.Consensus(**raw["consensus"]) if raw.get("consensus") else None,
        simplify=bool(raw.get("simplify", False)),
    )


def load_tracks(name: str, data_dir: Path) -> list[runner.Track]:
    if name == "mdb":
        found = mdb.tracks(data_dir / "mdb")
    elif name == "enst":
        found = enst.tracks(data_dir / "enst")
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
    """Downloads a dataset to `data_dir/<name>` (ENST: from Zenodo, then builds the
    evaluation mixes); returns the number of tracks."""
    if name == "mdb":
        return mdb.fetch(data_dir / "mdb")
    if name == "enst":
        return enst.fetch(data_dir / "enst")
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
    only: set[str] | None = None,
) -> list[runner.Record]:
    """Computes the matrix from the configuration; results end up in the cache.
    `only`: track ids to restrict the run to (e.g. what a rented GPU still has to compute)."""
    cfg = load_benchmark_config(config_path)
    tracks = _tracks(cfg, data_dir, only)
    registry = adapters.discover(adapters_root)
    records = runner.run_matrix(
        tracks,
        cfg.separators,
        cfg.transcribers,
        registry,
        cache_dir,
        device=device or cfg.device,
        execute=execute,
        progress=progress,
        cancel=cancel,
        timeout=cfg.timeout,
        skip=cfg.skip,
    )
    if cfg.grid and execute:
        _track_beats(tracks, registry, cache_dir, device or cfg.device, execute=True)
    return records


def _track_beats(
    tracks: dict[str, list], registry: dict, cache_dir: Path, device: str, execute: bool
) -> dict[tuple[str, str], grid.BeatGrid | None]:
    """Beat This! beats of every track's mix (None where they are missing or failed)."""
    out: dict[tuple[str, str], grid.BeatGrid | None] = {}
    for name, ts in tracks.items():
        for t in ts:
            res = runner.cached_or_run(registry["beat_this"], t.mix, cache_dir, device, execute)
            if res.ok:
                raw = json.loads(res.output.read_text(encoding="utf-8"))
                out[(name, t.id)] = grid.BeatGrid(list(raw["beats"]), list(raw["downbeats"]))
            else:
                out[(name, t.id)] = None
    return out


def _tracks(cfg: BenchmarkConfig, data_dir: Path, only: set[str] | None) -> dict:
    return {
        name: [t for t in load_tracks(name, data_dir) if only is None or t.id in only]
        for name in cfg.datasets
    }


def missing_tracks(
    config_path: Path,
    *,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
) -> list[str]:
    """Ids of the tracks with at least one job of the config that is not in the cache."""
    records = run_benchmark(
        config_path,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        execute=False,
    )
    return sorted({r.track for r in records if not r.ok})


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
    only: set[str] | None = None,
) -> list[dict]:
    """Scores the cached results (computes nothing); writes metrics.csv and summary.csv."""
    cfg, tracks, records = _all_records(
        config_path,
        device=device,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        only=only,
    )
    all_schemes = load_schemes(CLASSES)
    schemes = {name: all_schemes[name] for name in cfg.schemes}
    rows = runner.score_records(records, tracks, schemes)
    summary = summarize(rows)
    write_csv(results_dir / "metrics.csv", rows)
    write_csv(results_dir / "summary.csv", summary)
    return summary


def _all_records(
    config_path: Path,
    *,
    device: str | None,
    data_dir: Path,
    cache_dir: Path,
    adapters_root: Path,
    only: set[str] | None,
) -> tuple[BenchmarkConfig, dict, list[runner.Record]]:
    """The cached records of a config plus its fusions, votes, combos and grid variants."""
    cfg = load_benchmark_config(config_path)
    tracks = _tracks(cfg, data_dir, only)
    records = run_benchmark(
        config_path,
        device=device,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        execute=False,
        only=only,
    )
    all_schemes = load_schemes(CLASSES)
    # Fusions and combos name classes of the 5-class scheme; scored in every configured scheme.
    # Fusions first, so that combos can use them ("fusion+<name>").
    five = all_schemes["5"]
    fusions = fusion.parse_fusions(cfg.fusions, list(five.classes))
    records += fusion.fused_records(records, fusions, _class_of(five))
    votes = vote.parse_votes(cfg.votes)
    records += vote.vote_records(records, votes, five, runner.read_drum_notes)
    combos = combine.parse_combos(cfg.combos, all_schemes["5"])
    records += combine.combine_records(records, combos, all_schemes["5"], runner.read_drum_notes)
    if cfg.grid:
        beats = _track_beats(
            tracks, adapters.discover(adapters_root), cache_dir, cfg.device, execute=False
        )
        pipelines = grid.parse_pipelines(cfg.grid)
        records += grid.grid_records(
            records, pipelines, beats, runner.read_drum_notes, cfg.consensus, cfg.simplify
        )
    return cfg, tracks, records


ERROR_PIPELINES = ("none+adtof", "combo+quality")  # Fast and Quality


def error_breakdowns(
    config_path: Path = CONFIG,
    pipelines: tuple[str, ...] | list[str] = ERROR_PIPELINES,
    *,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    only: set[str] | None = None,
) -> dict[tuple[str, str, str], errors.Breakdown]:
    """(dataset, track, pipeline) → the categorised errors in the 5-class scheme, from the same
    records `evaluate_benchmark` scores (computes nothing)."""
    _, tracks, records = _all_records(
        config_path,
        device=None,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        only=only,
    )
    five = load_schemes(CLASSES)["5"]
    by_id = {(ds, t.id): t for ds, ts in tracks.items() for t in ts}
    found, out = set(), {}
    for r in records:
        label = f"{r.separator}+{r.transcriber}"
        if label not in pipelines:
            continue
        found.add(label)
        if not r.ok:
            where = f"{r.dataset}/{r.track}"
            raise RuntimeError(f"{label} on {where}: not computed, run `stickler run`")
        ref, est = runner.record_notes(r, by_id[(r.dataset, r.track)])
        out[(r.dataset, r.track, label)] = errors.categorise(
            onsets_from_notes(ref, five), onsets_from_notes(est, five)
        )
    if unknown := [p for p in pipelines if p not in found]:
        raise ValueError(f"not in {config_path.name}: {', '.join(unknown)}")
    return out


def error_breakdown(
    config_path: Path = CONFIG,
    pipelines: tuple[str, ...] | list[str] = ERROR_PIPELINES,
    *,
    results_dir: Path = RESULTS_DIR,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    only: set[str] | None = None,
) -> list[dict]:
    """Writes errors.csv (per track, pipeline and class) and returns the counts summed over the
    tracks, per pipeline and class."""
    found = error_breakdowns(
        config_path,
        pipelines,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        only=only,
    )
    classes = list(load_schemes(CLASSES)["5"].classes)
    rows = [
        {"dataset": ds, "track": track, "pipeline": label, **row}
        for (ds, track, label), b in found.items()
        for row in errors.count_rows(b, classes)
    ]
    write_csv(results_dir / "errors.csv", rows)
    return errors.pool(rows)


def _class_of(scheme) -> dict[int, str]:
    """ADTOF's output pitches (LABELS_5) → classes of the scheme."""
    return {p: scheme.class_of(p) for p in (35, 38, 47, 42, 49)}


@dataclass
class TuneReport:
    inputs: list[str]
    tracks: int
    default: dict  # class → fusion.Tuned for ADTOF's defaults on inputs[0]
    tuned: dict  # class → fusion.Tuned

    def yaml(self, name: str) -> str:
        lines = [
            "fusions:",
            f"  {name}:",
            f"    inputs: [{', '.join(self.inputs)}]",
            "    classes:",
        ]
        for cls, t in self.tuned.items():
            weights = ", ".join(f"{w:g}" if w != int(w) else f"{w:.1f}" for w in t.weights)
            lines.append(f"      {cls}: {{weights: [{weights}], threshold: {t.threshold:g}}}")
        return "\n".join(lines) + "\n"


def tune_fusion(
    config_paths: list[Path],
    inputs: list[str],
    *,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    step: float = 0.25,
    thresholds: list[float] | None = None,
) -> TuneReport:
    """Tunes fusion weights and thresholds per class on the cached ADTOF runs of the given
    configs (use tuning data only, e.g. MDB and ENST; keep the own songs for the final check)."""
    five = load_schemes(CLASSES)["5"]
    samples = []
    for path in config_paths:
        cfg = load_benchmark_config(path)
        tracks = {name: load_tracks(name, data_dir) for name in cfg.datasets}
        records = run_benchmark(
            path, data_dir=data_dir, cache_dir=cache_dir, adapters_root=adapters_root, execute=False
        )
        samples += fusion.samples_from_records(records, tracks, inputs, five)
    if not samples:
        raise ValueError("no tracks with ADTOF activations for all inputs: run ADTOF first")
    labels, class_of = [35, 38, 47, 42, 49], _class_of(five)
    first = tuple(1.0 if i == 0 else 0.0 for i in range(len(inputs)))
    default = fusion.score_params(
        samples,
        labels,
        class_of,
        {c: fusion.ClassParams(first, t) for c, t in fusion.ADTOF_THRESHOLDS.items()},
    )
    grid = thresholds or [round(0.02 + 0.02 * i, 2) for i in range(30)]  # 0.02 … 0.60
    tuned = fusion.tune(
        samples, labels, class_of, weights=fusion.weight_grid(len(inputs), step), thresholds=grid
    )
    return TuneReport(list(inputs), len(samples), default, tuned)


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
    pipeline: str  # the mode ("fast", "quality") or "separator+transcriber"
    stem: Path | None  # separated drum track; None if nothing was separated
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
    pipeline: str | None = None,
    *,
    mode: str = DEFAULT_MODE,
    drums: bool = False,
    device: str = "auto",
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
) -> SongTranscription:
    """Separation, transcription and beat tracking for one song (cached like the benchmark).
    `pipeline` ("separator+transcriber") overrides `mode`. In a mode with several parts, each
    part provides its classes; hits outside the five classes come from the first part.
    `drums`: also separate the drums if the mode itself does not (for the drum track export)."""
    registry = adapters.discover(adapters_root)
    if pipeline is not None:
        parts = {pipeline: ALL_CLASSES}
    elif mode in MODES:
        parts = MODES[mode]
    else:
        raise ValueError(f"unknown mode {mode!r} (available: {', '.join(MODES)})")
    pairs = {label: _parse_pipeline(label, registry) for label in parts}

    def run(adapter: str, source: Path) -> Path:
        return _result(runner.cached_or_run(registry[adapter], source, cache_dir, device, True))

    stems: dict[str, Path] = {}
    for sep, _ in pairs.values():
        if sep != "none" and sep not in stems:
            stems[sep] = run(sep, audio_path)
    five = load_schemes(CLASSES)["5"]
    hits: list[tuple[float, int, int]] = []
    for i, (label, (sep, tr)) in enumerate(pairs.items()):
        wanted = set(parts[label])
        for hit in read_drum_hits(run(tr, stems.get(sep, audio_path))):
            cls = five.class_of(hit[1])
            if cls in wanted or (cls is None and i == 0):
                hits.append(hit)
    if drums and not stems:
        stems[DRUM_TRACK_SEPARATOR] = run(DRUM_TRACK_SEPARATOR, audio_path)
    beats = json.loads(run("beat_this", audio_path).read_text(encoding="utf-8"))
    return SongTranscription(
        audio=audio_path,
        pipeline=pipeline or mode,
        stem=next(iter(stems.values()), None),
        beats=list(beats["beats"]),
        downbeats=list(beats["downbeats"]),
        hits=sorted(hits),
    )


def notate(
    audio_path: Path,
    out: Path | None = None,
    *,
    pipeline: str | None = None,
    mode: str = DEFAULT_MODE,
    drums: bool = False,
    title: str | None = None,
    artist: str | None = None,
    pdf: bool = True,
    simplify: bool = True,
    repeats: bool = True,
    device: str = "auto",
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
) -> Notation:
    """Song → drum sheet music as MusicXML (default: next to the song, <song>.musicxml), plus a
    PDF next to it if MuseScore is installed. Title and artist default to the file's tags.
    For readability, `simplify` gives similar bars their common pattern and `repeats` writes
    runs of equal bars once between repeat signs (notation.to_musicxml)."""
    t = transcribe_song(
        audio_path,
        pipeline,
        mode=mode,
        drums=drums,
        device=device,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
    )
    target = out or audio_path.with_suffix(".musicxml")
    target.parent.mkdir(parents=True, exist_ok=True)
    found = audio.tags(audio_path) if title is None or artist is None else {}
    xml = notation.to_musicxml(
        t.hits,
        t.beats,
        t.downbeats,
        title=title or found.get("title") or audio_path.stem,
        artist=artist if artist is not None else found.get("artist", ""),
        simplify_bars=simplify,
        repeats=repeats,
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


def cache_entries(
    config_path: Path,
    *,
    data_dir: Path = DATA_DIR,
    cache_dir: Path = CACHE_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    only: set[str] | None = None,
) -> list[str]:
    """Cache folders ("<adapter>/<key>") holding results the config uses: stems,
    transcriptions and the tracks' beats (of the `only` tracks). Only these go to a rented GPU."""
    records = run_benchmark(
        config_path,
        data_dir=data_dir,
        cache_dir=cache_dir,
        adapters_root=adapters_root,
        execute=False,
        only=only,
    )
    folders: set[Path] = set()
    for r in records:
        folders.update(p.parent for p in (r.stem, r.midi) if p is not None)
    registry = adapters.discover(adapters_root)
    if "beat_this" in registry:
        for name in load_benchmark_config(config_path).datasets:
            for t in load_tracks(name, data_dir):
                if only is None or t.id in only:
                    folders.add(runner.cache_dir_for(cache_dir, registry["beat_this"], t.mix))
    root = cache_dir.resolve()
    return sorted(
        str(f.resolve().relative_to(root))
        for f in folders
        if f.is_dir() and f.resolve().is_relative_to(root)
    )


def restrict_plan(plan: remote.SyncPlan, only: list[str]) -> remote.SyncPlan:
    """Keeps only the own songs' files of the given tracks (song folder data/own/<id>)."""
    keep = set(only)
    return dataclasses.replace(
        plan,
        data_files=[f for f in plan.data_files if Path(f).parent.name in keep],
        audio=[(local, d) for local, d in plan.audio if Path(d).name in keep],
        only=list(only),
    )


def run_remote(
    host: str, port: int, config_path: Path, *, pod_id: str | None = None, wipe: bool = False
) -> list[str]:
    """Runs a benchmark config on a rented GPU over SSH and brings the new cache entries
    back (development only); returns the tracks it computed. Only tracks with missing jobs
    are uploaded and computed; with none, nothing is uploaded and the pod is only stopped.
    Secrets come from the environment: HF_TOKEN (or the file from `hf auth login`) and, to
    stop the pod afterwards, the RunPod key (`runpod_api_key`)."""
    api_key = runpod_api_key()
    if pod_id and not api_key:
        raise ValueError(f"--pod-id needs the RunPod API key (RUNPOD_API_KEY or {RUNPOD_KEY_FILE})")
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token and doctor.HF_TOKEN_FILE.exists():
        hf_token = doctor.HF_TOKEN_FILE.read_text(encoding="utf-8").strip()
    config = config_path.resolve()
    stop = (lambda: remote.stop_pod(pod_id, api_key)) if pod_id else None
    missing = missing_tracks(config)
    if not missing:
        if stop:
            stop()
        return []
    plan = remote.sync_plan(
        config,
        project_root=PROJECT_ROOT,
        references_dir=REFERENCES_DIR,
        data_dir=DATA_DIR,
    )
    plan = restrict_plan(plan, missing)
    plan = dataclasses.replace(plan, cache=cache_entries(config, only=set(missing)))
    remote.run_remote(
        remote.Host(host, port),
        str(config.relative_to(PROJECT_ROOT)),
        remote.adapters_for(config),
        plan,
        project_root=PROJECT_ROOT,
        hf_token=hf_token,
        stop=stop,
        wipe=wipe,
    )
    return missing


def migrate_cache(
    *,
    dry_run: bool = False,
    cache_dir: Path = CACHE_DIR,
    data_dir: Path = DATA_DIR,
    adapters_root: Path = ADAPTERS_ROOT,
    rekey_from: Path | None = None,
) -> cachemigration.Report:
    """Moves cache entries from the old device-dependent keys to the current keys (see
    stickler.cachemigration). Inputs: MDB and ENST mixes and stems, the own songs' recordings;
    a dataset missing here would have all its entries set aside as unknown.
    `rekey_from`: digest snapshot (save_digests) taken before a behaviour-neutral edit."""
    inputs: list[Path] = []
    for track in mdb.tracks(data_dir / "mdb"):
        inputs += [track.mix, track.drums]
    for track in enst.tracks(data_dir / "enst"):
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
