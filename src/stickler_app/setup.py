"""The setup assistant's decisions (SPEC.md, module `setup-assistant`; design screens 1–3),
without GTK: what the start shows, the steps of what is missing, a step's progress in bytes,
and which server a failed step names."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from stickler_app.i18n import N_, _

# what a step adds on disk, from docs/requirements.md (uv's cache and the adapter's folder)
SIZES = {
    "environment:adtof": 1_300_000_000,  # its programs, the model included
    "environment:beat_this": 800_000_000,
    "weights:beat_this": 78_000_000,
}
MOST = 0.99  # a step is full only when it reports done
DETAIL_LINES = 8


def start_page(missing: list[str], *, agreed: bool) -> str:
    """ "none" when Fast is set up; else "consent", or "download" once agreed (an interrupted
    setup goes on by itself)."""
    if not missing:
        return "none"
    return "download" if agreed else "consent"


def step_ids(missing: list[str], has_weights: Callable[[str], bool]) -> tuple[str, ...]:
    """The order api.setup_adapters reports them in: each adapter's programs, then its model."""
    ids = []
    for adapter in missing:
        ids.append(f"environment:{adapter}")
        if has_weights(adapter):
            ids.append(f"weights:{adapter}")
    return tuple(ids)


def fraction(step_id: str, grown: int) -> float | None:
    size = SIZES.get(step_id)
    if size is None:
        return None
    return min(max(grown / size, 0.0), MOST)


def _size(n: float) -> str:
    if n >= 1_000_000_000:
        return _("{size:n} GB").format(size=round(n / 1e9, 1))
    return _("{size:n} MB").format(size=round(n / 1e6))


def amount(step_id: str, grown: int) -> str:
    """ "650 MB of 1.3 GB" for a running step."""
    size = SIZES.get(step_id)
    if size is None:
        return ""
    done = min(max(grown, 0), size)
    return _("{done} of {total}").format(done=_size(done), total=_size(size))


def server(step_id: str) -> str:
    """Who a failed step needed (design screen 3)."""
    kind, _sep, adapter = step_id.partition(":")
    if kind == "environment":
        return _("the Python package servers (pypi.org, download.pytorch.org, github.com)")
    if adapter == "beat_this":
        return _("JKU Linz (cloud.cp.jku.at) and Stickler’s copy (github.com)")
    return _("the model’s server")


def details(error: str) -> str:
    lines = error.strip().splitlines()
    return "\n".join(lines[-DETAIL_LINES:])


def free_space(path: Path) -> int:
    """Free bytes on the disk that holds `path` (or its nearest existing parent). What a step
    used is the free space it took: cheap enough for twice a second, unlike walking uv's cache;
    other programs writing at the same time make it a little off, hence MOST."""
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path).free


def meter(step_id: str, root: Path, adapter_dir: Path) -> Callable[[], int]:
    """What a step has added so far, measured from when it starts. The programs: the free space
    they took. The model: the files under the adapter's weights/, since the free space also
    counted Python's first bytecode and showed "78 of 78 MB" half-way (owner, 2026-11-15)."""
    if step_id.startswith("weights:"):
        weights = adapter_dir / "weights"
        return lambda: sum(f.stat().st_size for f in weights.rglob("*") if f.is_file())
    before = free_space(root)
    return lambda: before - free_space(root)


# design screen 1: what each model does and its licence
MODELS = {
    "adtof": (
        N_("detects the hits"),
        N_("Its trained model is free for non-commercial use only (CC BY-NC-SA 4.0)."),
    ),
    "beat_this": (
        N_("finds the beat and the bars"),
        N_("MIT licence. Its model comes from the JKU Linz server."),
    ),
}


def model_text(adapter: str) -> tuple[str, str]:
    does, licence = MODELS.get(adapter, ("", ""))
    return (_(does) if does else "", _(licence) if licence else "")


def _model_bytes(adapter: str) -> int:
    return sum(size for step, size in SIZES.items() if step.endswith(f":{adapter}"))


def _gb(n: float) -> str:
    """Sizes on the consent page are in GB, as design screen 1 has them."""
    return _("{size:n} GB").format(size=round(n / 1e9, 1))


def model_size(adapter: str) -> str:
    return _gb(_model_bytes(adapter))


def total_size(missing: Iterable[str]) -> str:
    return _gb(sum(_model_bytes(a) for a in missing))


def uv_cache(env: Mapping[str, str] = os.environ) -> Path:
    """Where uv keeps what it downloads (its own rule: UV_CACHE_DIR, else the XDG cache)."""
    if env.get("UV_CACHE_DIR"):
        return Path(env["UV_CACHE_DIR"])
    base = env.get("XDG_CACHE_HOME") or str(Path(env.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "uv"


SKIPPED = {"__pycache__", ".venv", "weights", ".pytest_cache"}  # never shipped, never replaced
WEIGHT_FILES = {"setup.py", "download.py", "common.py"}  # what decides an adapter's weights


def sync_adapters(shipped: Path, models: Path) -> int:
    """Copies the adapters' sources a packaged app ships into its writable models folder, file
    by file where they differ; the environments and weights there stay (uv sync and setup
    bring them up to date). Returns how many files were copied."""
    copied = 0
    for source in sorted(shipped.rglob("*")):
        relative = source.relative_to(shipped)
        if any(part in SKIPPED or part.startswith(".venv") for part in relative.parts):
            continue
        target = models / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists() or target.read_bytes() != source.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")  # never a half-copied file
            shutil.copyfile(source, part)
            part.replace(target)
            copied += 1
            if source.name in WEIGHT_FILES and len(relative.parts) >= 3:
                # where the weights come from changed: setup must download them again
                adapter = models / relative.parts[0] / relative.parts[1]
                (adapter / "weights" / ".setup-complete").unlink(missing_ok=True)
    return copied
