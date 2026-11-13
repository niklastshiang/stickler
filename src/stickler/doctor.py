"""System check: GPU, adapter environments, weights, Hugging Face login, MuseScore, datasets."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stickler import adapters, musescore
from stickler.datasets import enst, mdb

HF_TOKEN_FILE = Path.home() / ".cache" / "huggingface" / "token"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _nvidia_name() -> str | None:
    """First line of `nvidia-smi -L`, e.g. "GPU 0: NVIDIA GeForce RTX 4090 (UUID: …)"."""
    try:
        proc = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = proc.stdout.strip().splitlines() if proc.returncode == 0 else []
    return lines[0] if lines else None


def check_gpu(
    kfd: Path = Path("/dev/kfd"),
    drm: Path = Path("/sys/class/drm"),
    nvidia: Callable[[], str | None] = _nvidia_name,
) -> Check:
    """NVIDIA GPU for CUDA (nvidia-smi), or AMD GPU for ROCm: /dev/kfd present and a DRM card
    with vendor 0x1002."""
    if name := nvidia():
        return Check("gpu", True, f"{name} (CUDA)")
    amd = [v for v in drm.glob("card*/device/vendor") if v.read_text().strip() == "0x1002"]
    if kfd.exists() and amd:
        return Check("gpu", True, f"AMD GPU ({amd[0].parent.parent.name}), /dev/kfd present")
    return Check("gpu", False, "no NVIDIA GPU (nvidia-smi) and no AMD GPU with /dev/kfd found")


def _rocm_device_name(spec: adapters.AdapterSpec) -> str | None:
    python = spec.path / adapters.ROCM_ENV / "bin" / "python"
    code = "import torch; print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
    try:
        proc = subprocess.run([str(python), "-c", code], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    name = proc.stdout.strip().splitlines()[-1:] if proc.returncode == 0 else []
    return name[0] if name and name[0] else None


def check_adapters(root: Path, probe_gpu: bool = False) -> list[Check]:
    checks = []
    for adapter_id, spec in sorted(adapters.discover(root).items()):
        problems = []
        if not (spec.path / ".venv").is_dir():
            problems.append("CPU environment missing")
        if (spec.path / "setup.py").exists():
            weights = spec.path / "weights"
            if not weights.is_dir() or not any(weights.iterdir()):
                problems.append("weights missing")
        cfg = adapters.rocm_config(spec) if (spec.path / "pyproject.toml").exists() else None
        if cfg is None:
            rocm = "ROCm: –"
        elif not (spec.path / adapters.ROCM_ENV).is_dir():
            rocm = "ROCm: not built"
        else:
            name = _rocm_device_name(spec) if probe_gpu else None
            rocm = f"ROCm: {name}" if name else "ROCm: built"
            if not cfg.prefer_gpu:
                rocm += " (auto uses CPU)"
        if (spec.path / adapters.CUDA_ENV).is_dir():
            rocm += "; CUDA: built"
        detail = "; ".join(problems) if problems else "ready"
        if problems:
            detail += f" → stickler setup --adapter {adapter_id}"
        checks.append(Check(f"adapter {adapter_id}", not problems, f"{detail}; {rocm}"))
    return checks


def check_hf_login(token_file: Path = HF_TOKEN_FILE) -> Check:
    if os.environ.get("HF_TOKEN") or token_file.exists():
        return Check("hugging face", True, "logged in")
    return Check("hugging face", False, "not logged in → uvx hf auth login (for MuScriptor)")


def check_musescore(flatpak_ids: Callable[[], set[str]] = musescore.flatpak_ids) -> Check:
    cmd = musescore.find(flatpak_ids=flatpak_ids)
    if cmd:
        label = f"Flatpak {musescore.FLATPAK_ID}" if cmd[0] == "flatpak" else cmd[0]
        return Check("musescore", True, label)
    return Check(
        "musescore", False, "not found (optional, for PDF): flathub org.musescore.MuseScore"
    )


def check_datasets(data_dir: Path) -> list[Check]:
    n = len(mdb.tracks(data_dir / "mdb"))
    detail = f"{n} tracks" if n else "missing → stickler fetch mdb"
    checks = [Check("dataset mdb", n > 0, detail)]
    n_enst = len(enst.tracks(data_dir / "enst"))
    if n_enst:  # optional dataset (`stickler fetch enst`), only shown once it is there
        checks.append(Check("dataset enst", True, f"{n_enst} tracks"))
    return checks


def run_all(adapters_root: Path, data_dir: Path) -> list[Check]:
    return [
        check_gpu(),
        *check_adapters(adapters_root, probe_gpu=True),
        check_hf_login(),
        check_musescore(),
        *check_datasets(data_dir),
    ]
