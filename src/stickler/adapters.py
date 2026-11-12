"""Adapter contract: models run as a subprocess in their own uv environment.

Aufruf:  uv run --project <adapter> python <adapter>/run.py --in <audio> --out <dir> --device <d>
Result: stage output + meta.json, error.log on failure. The harness never aborts.

GPU (AMD ROCm): adapters that declare `[tool.stickler.rocm]` in their pyproject.toml get a
second environment `.venv-rocm` via `setup_adapter(spec, device="rocm")`. In it, the CPU torch
packages are replaced by AMD's ROCm wheels; all other versions come from the lock.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

OUTPUTS = {"separators": "drums.wav", "transcribers": "drums.mid", "beats": "beats.json"}
DEVICES = ("auto", "cpu", "gpu")
SETUP_DEVICES = ("cpu", "rocm")
ROCM_ENV = ".venv-rocm"


@dataclass(frozen=True)
class AdapterSpec:
    id: str
    stage: str
    path: Path

    @property
    def expected_output(self) -> str:
        return OUTPUTS[self.stage]

    @property
    def needs_stem(self) -> bool:
        """True if the model only accepts drum stems ([tool.stickler] input = "stem")."""
        pyproject = self.path / "pyproject.toml"
        if not pyproject.exists():
            return False
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return data.get("tool", {}).get("stickler", {}).get("input", "any") == "stem"


@dataclass(frozen=True)
class RocmConfig:
    index: str
    replace: list[str]
    packages: list[str]
    # False: still use CPU with device="auto" (if the GPU is slower for this model)
    prefer_gpu: bool = True


def rocm_config(spec: AdapterSpec) -> RocmConfig | None:
    data = tomllib.loads((spec.path / "pyproject.toml").read_text(encoding="utf-8"))
    cfg = data.get("tool", {}).get("stickler", {}).get("rocm")
    if not cfg:
        return None
    return RocmConfig(
        index=cfg["index"],
        replace=list(cfg["replace"]),
        packages=list(cfg["packages"]),
        prefer_gpu=bool(cfg.get("prefer_gpu", True)),
    )


def _rocm_python(spec: AdapterSpec) -> Path:
    return spec.path / ROCM_ENV / "bin" / "python"


def env_variant(spec: AdapterSpec, device: str) -> str | None:
    """Which environment runs: 'rocm' (if built and cpu not requested), else 'cpu'.
    With 'auto', `prefer_gpu` also decides. None if 'gpu' is requested but no ROCm
    environment exists."""
    has_rocm = _rocm_python(spec).exists()
    if device == "cpu":
        return "cpu"
    if device == "gpu":
        return "rocm" if has_rocm else None
    cfg = rocm_config(spec) if has_rocm else None
    return "rocm" if cfg and cfg.prefer_gpu else "cpu"


def rocm_requirements(spec: AdapterSpec, replace: list[str]) -> list[str]:
    """Direct dependencies from pyproject.toml without the packages to be replaced.

    Deliberately not the CPU lock: its transitive pins (e.g. setuptools) do not match the
    ROCm wheels. Path sources from [tool.uv.sources] become `-e <path>`.
    """
    data = tomllib.loads((spec.path / "pyproject.toml").read_text(encoding="utf-8"))
    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    reqs = []
    for dep in data.get("project", {}).get("dependencies", []):
        name = re.split(r"[=<>~!;\[ ]", dep, maxsplit=1)[0].strip().lower()
        if name in replace:
            continue
        source = sources.get(name, {})
        reqs.append(f"-e {source['path']}" if "path" in source else dep)
    return reqs


@dataclass(frozen=True)
class AdapterResult:
    ok: bool
    output: Path | None
    meta: dict | None
    error: str | None


def discover(root: Path) -> dict[str, AdapterSpec]:
    """Finds `root/<stage>/<id>/run.py`. Folders starting with `_` are skipped."""
    found: dict[str, AdapterSpec] = {}
    for run_py in sorted(root.glob("*/*/run.py")):
        adapter_dir = run_py.parent
        stage = adapter_dir.parent.name
        if stage.startswith("_"):
            continue
        if stage not in OUTPUTS:
            raise ValueError(f"Unknown stage {stage!r} in {adapter_dir}")
        found[adapter_dir.name] = AdapterSpec(id=adapter_dir.name, stage=stage, path=adapter_dir)
    return found


def _run_group(cmd: list[str], timeout: float | None) -> subprocess.CompletedProcess | None:
    """Starts the adapter in its own process group. On timeout the whole group is killed:
    `uv run` starts the model as a grandchild process that would otherwise keep running.
    Returns None on timeout."""
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return None
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _fail(out_dir: Path, message: str) -> AdapterResult:
    log.warning(message)
    (out_dir / "error.log").write_text(message, encoding="utf-8")
    return AdapterResult(ok=False, output=None, meta=None, error=message)


def run_adapter(
    spec: AdapterSpec,
    audio: Path,
    out_dir: Path,
    device: str = "auto",
    timeout: float | None = None,
) -> AdapterResult:
    if device not in DEVICES:
        raise ValueError(f"device must be one of {DEVICES}, not {device!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    variant = env_variant(spec, device)
    if variant is None:
        return _fail(
            out_dir,
            f"{spec.id}: GPU requested, but no ROCm environment. "
            f"First run: stickler setup --adapter {spec.id} --device rocm",
        )
    if variant == "rocm":
        python = [str(_rocm_python(spec))]
    else:
        python = ["uv", "run", "--quiet", "--project", str(spec.path), "python"]
    args = ["--in", str(audio), "--out", str(out_dir), "--device", device]
    cmd = [*python, str(spec.path / "run.py"), *args]
    log.info("%s: %s", spec.id, audio.name)
    proc = _run_group(cmd, timeout)
    if proc is None:
        return _fail(out_dir, f"{spec.id}: time limit of {timeout} s exceeded")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        return _fail(out_dir, f"{spec.id} (exit {proc.returncode}):\n{tail}")
    output = out_dir / spec.expected_output
    meta_path = out_dir / "meta.json"
    if not output.exists() or not meta_path.exists():
        return _fail(out_dir, f"{spec.id}: {spec.expected_output} or meta.json missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return AdapterResult(ok=True, output=output, meta=meta, error=None)


def _check(cmd: list[str], spec: AdapterSpec, **kw) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        raise RuntimeError(f"Setup of {spec.id} failed ({cmd[0]} {cmd[1]}):\n{tail}")
    return proc.stdout


def _setup_rocm(spec: AdapterSpec) -> Path:
    cfg = rocm_config(spec)
    if cfg is None:
        raise RuntimeError(f"{spec.id} declares no ROCm packages ([tool.stickler.rocm])")
    python = _rocm_python(spec)
    if not python.exists():
        _check(["uv", "venv", "--quiet", "--python", "3.12", ROCM_ENV], spec, cwd=spec.path)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(rocm_requirements(spec, cfg.replace)) + "\n")
    _check(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            str(python),
            "--index",
            cfg.index,
            "--index-strategy",
            "unsafe-best-match",
            "-r",
            f.name,
            *cfg.packages,
        ],
        spec,
        cwd=spec.path,
    )
    return python


def setup_adapter(spec: AdapterSpec, device: str = "cpu") -> None:
    """Builds the environment (cpu: uv sync, rocm: .venv-rocm) and runs setup.py if present."""
    if device not in SETUP_DEVICES:
        raise ValueError(f"device must be one of {SETUP_DEVICES}, not {device!r}")
    if device == "rocm":
        python = [str(_setup_rocm(spec))]
    else:
        _check(["uv", "sync", "--quiet", "--project", str(spec.path)], spec)
        python = ["uv", "run", "--quiet", "--project", str(spec.path), "python"]
    if (spec.path / "setup.py").exists():
        _check([*python, str(spec.path / "setup.py")], spec)
    log.info("%s: setup (%s) done", spec.id, device)
