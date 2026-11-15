"""The setup assistant's decisions (SPEC.md, module `setup-assistant`; design screens 1–3),
without GTK: what the start shows, the steps of what is missing, a step's progress in bytes,
and which server a failed step names."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from stickler_gtk.i18n import _

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


def disk_bytes(folders: Iterable[Path]) -> int:
    """The size of the files below `folders` (links not followed; missing folders count 0)."""
    total = 0
    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                path = Path(root) / name
                if not path.is_symlink():
                    total += path.stat().st_size
    return total


def uv_cache(env: Mapping[str, str] = os.environ) -> Path:
    """Where uv keeps what it downloads (its own rule: UV_CACHE_DIR, else the XDG cache)."""
    if env.get("UV_CACHE_DIR"):
        return Path(env["UV_CACHE_DIR"])
    base = env.get("XDG_CACHE_HOME") or str(Path(env.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "uv"
