"""Migration of cache entries from the v1 keys to the v2 keys (runner.cache_dir_for).

v1 keys hashed the raw adapter files and the device/environment (`auto`, `gpu|cuda`, …);
v2 keys only hash the input content and the adapter's code without comments. Keys cannot be
inverted, so the migration recomputes the v1 key for every known input and environment and
moves matching folders. Nothing is deleted:

- two v1 entries for the same v2 key (e.g. CPU and GPU): the first in LEGACY_ENVS wins (CPU
  first), the others go to `cache/_superseded/`;
- folders that match no known input with the current adapter code (e.g. made by an older
  adapter version) go to `cache/_orphaned/`.
The migration is idempotent; it is run again after results come back from a rented GPU.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from stickler import adapters, runner

# CPU first: on duplicates the CPU result is kept (the benchmark's reference device)
LEGACY_ENVS = ("auto", "cpu", "gpu|cuda", "auto|cuda", "gpu|rocm", "auto|rocm")


@dataclass
class Report:
    moved: int = 0  # v1 folders moved to their v2 key
    superseded: int = 0  # duplicates set aside
    orphaned: int = 0  # unknown folders set aside
    current: int = 0  # folders already under a v2 key


def _raw_digest(spec: adapters.AdapterSpec) -> str:
    h = hashlib.sha1()
    for name in ("run.py", "pyproject.toml", "setup.py"):
        p = spec.path / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def legacy_key(spec: adapters.AdapterSpec, audio_sha1: str, env: str) -> str:
    """The v1 key (runner before 2026-11-12) for an input with the given SHA-1."""
    return hashlib.sha1(f"{audio_sha1}|{spec.id}|{_raw_digest(spec)}|{env}".encode()).hexdigest()[
        :16
    ]


def _sha1(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha1").hexdigest()


def migrate(
    cache: Path,
    registry: dict[str, adapters.AdapterSpec],
    inputs: list[Path],
    *,
    dry_run: bool = False,
) -> Report:
    """`inputs`: original audio (mixes, dataset stems, own songs). Separator outputs found in
    the cache are added automatically, because transcribers ran on them. Works on content
    hashes, so moving a separator's folder does not affect the keys of its transcriptions."""
    report = Report()
    stems = [
        p
        for s in registry.values()
        if s.stage == "separators"
        for p in (cache / s.id).glob("*/drums.wav")
    ]
    shas = {_sha1(p) for p in [*inputs, *stems] if p.exists()}
    for spec in registry.values():
        folder = cache / spec.id
        if not folder.is_dir():
            continue
        existing = {e.name for e in folder.iterdir() if e.is_dir()}
        wanted = {runner.cache_key(spec, sha): sha for sha in shas}  # v2 name → input sha1
        claimed = existing & wanted.keys()  # v2 names already in use
        report.current += len(claimed)
        handled: set[str] = set()
        for name, sha in wanted.items():
            for env in LEGACY_ENVS:
                old = legacy_key(spec, sha, env)
                if old not in existing or old in handled or old == name:
                    continue
                handled.add(old)
                if name in claimed:
                    report.superseded += 1
                    if not dry_run:
                        _set_aside(folder / old, cache / "_superseded" / spec.id)
                else:
                    claimed.add(name)
                    report.moved += 1
                    if not dry_run:
                        (folder / old).rename(folder / name)
        for name in sorted(existing - wanted.keys() - handled):
            report.orphaned += 1
            if not dry_run:
                _set_aside(folder / name, cache / "_orphaned" / spec.id)
    return report


def _set_aside(folder: Path, target_parent: Path) -> None:
    target_parent.mkdir(parents=True, exist_ok=True)
    target = target_parent / folder.name
    n = 1
    while target.exists():
        target = target_parent / f"{folder.name}-{n}"
        n += 1
    shutil.move(str(folder), str(target))
