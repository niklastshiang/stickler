"""Adapter contract: models run as a subprocess in their own uv environment.

Aufruf:  uv run --project <adapter> python <adapter>/run.py --in <audio> --out <dir> --device <d>
Result: stage output + meta.json, error.log on failure. The harness never aborts.

GPU (AMD ROCm): adapters that declare `[tool.stickler.rocm]` in their pyproject.toml get a
second environment `.venv-rocm` via `setup_adapter(spec, device="rocm")`. In it, the CPU torch
packages are replaced by AMD's ROCm wheels; all other versions come from the lock.

GPU (NVIDIA CUDA, e.g. a rented RunPod GPU): `setup_adapter(spec, device="cuda")` builds
`.venv-cuda` for any adapter without touching its files: every package at its `uv.lock`
version, the packages from the PyTorch CPU index at the same version from a CUDA index.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

OUTPUTS = {"separators": "drums.wav", "transcribers": "drums.mid", "beats": "beats.json"}
DEVICES = ("auto", "cpu", "gpu")
SETUP_DEVICES = ("cpu", "rocm", "cuda")
ROCM_ENV = ".venv-rocm"
CUDA_ENV = ".venv-cuda"
PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
# Tried in this order; newer torch releases are not built for every CUDA version.
CUDA_INDEXES = tuple(f"https://download.pytorch.org/whl/{v}" for v in ("cu128", "cu130", "cu126"))


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


def _cuda_python(spec: AdapterSpec) -> Path:
    return spec.path / CUDA_ENV / "bin" / "python"


def env_variant(spec: AdapterSpec, device: str) -> str | None:
    """Which environment runs. 'cpu' if requested; a built CUDA environment always wins
    (only built on machines with an NVIDIA GPU); then 'rocm' (with 'auto' only if
    `prefer_gpu`). None if 'gpu' is requested but no GPU environment exists."""
    has_rocm = _rocm_python(spec).exists()
    if device == "cpu":
        return "cpu"
    if _cuda_python(spec).exists():
        return "cuda"
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
    cached: bool = False  # taken from the cache, nothing was computed


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


# uv settings that point at the harness's own Python or environment. Inherited by an adapter's
# `uv run` or `uv sync`, they would run it on the wrong Python or build it in the wrong place.
HARNESS_ONLY_ENV = ("UV_PYTHON", "UV_PROJECT_ENVIRONMENT", "UV_PROJECT", "VIRTUAL_ENV")


def adapter_env() -> dict[str, str]:
    """The environment for adapter processes: the harness's, without HARNESS_ONLY_ENV."""
    return {k: v for k, v in os.environ.items() if k not in HARNESS_ONLY_ENV}


class CancelToken(threading.Event):
    """Set from any thread (`cancel()`) to stop a running call: the adapter's whole process
    group is killed and the call raises Cancelled."""

    def cancel(self) -> None:
        self.set()


class Cancelled(Exception):
    """A call was stopped through its CancelToken."""


CANCEL_POLL = 0.05  # seconds between looks at the cancel token while an adapter runs


def _kill_group(proc: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError):  # the whole group may have just exited
        os.killpg(proc.pid, signal.SIGKILL)
    proc.communicate()


def _run_group(
    cmd: list[str], timeout: float | None, cancel: threading.Event | None = None
) -> subprocess.CompletedProcess | None:
    """Starts the adapter in its own process group. On timeout or cancel the whole group is
    killed: `uv run` starts the model as a grandchild process that would otherwise keep
    running. Returns None on timeout, raises Cancelled on cancel."""
    deadline = None if timeout is None else time.monotonic() + timeout
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=adapter_env(),
    ) as proc:
        while True:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            wait = remaining
            if cancel is not None:
                wait = CANCEL_POLL if remaining is None else min(CANCEL_POLL, remaining)
            try:
                stdout, stderr = proc.communicate(timeout=wait)
                break
            except subprocess.TimeoutExpired:  # retrying communicate loses no output
                if cancel is not None and cancel.is_set():
                    _kill_group(proc)
                    raise Cancelled("cancelled") from None
                if deadline is not None and time.monotonic() >= deadline:
                    _kill_group(proc)
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
    cancel: threading.Event | None = None,
) -> AdapterResult:
    """Runs the adapter on `audio` into `out_dir`. A set `cancel` token kills it and raises
    Cancelled; `out_dir` is then removed, so nothing half-written passes for a result."""
    if device not in DEVICES:
        raise ValueError(f"device must be one of {DEVICES}, not {device!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    variant = env_variant(spec, device)
    if variant is None:
        return _fail(
            out_dir,
            f"{spec.id}: GPU requested, but no GPU environment. "
            f"First run: stickler setup --adapter {spec.id} --device rocm (or cuda)",
        )
    if variant == "rocm":
        python = [str(_rocm_python(spec))]
    elif variant == "cuda":
        python = [str(_cuda_python(spec))]
    else:
        python = ["uv", "run", "--quiet", "--project", str(spec.path), "python"]
    args = ["--in", str(audio), "--out", str(out_dir), "--device", device]
    cmd = [*python, str(spec.path / "run.py"), *args]
    log.info("%s: %s", spec.id, audio.name)
    try:
        proc = _run_group(cmd, timeout, cancel)
    except Cancelled:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise Cancelled(f"{spec.id}: cancelled") from None
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
    proc = subprocess.run(cmd, capture_output=True, text=True, env=adapter_env(), **kw)
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


def cuda_pins(spec: AdapterSpec) -> list[str]:
    """`name==version` for every locked package from the PyTorch CPU index (local version
    label such as `+cpu` removed), to be installed from a CUDA index instead."""
    lock = tomllib.loads((spec.path / "uv.lock").read_text(encoding="utf-8"))
    pins = {}
    for pkg in lock.get("package", []):
        if pkg.get("source", {}).get("registry") == PYTORCH_CPU_INDEX:
            pins[pkg["name"]] = pkg["version"].split("+")[0]
    return [f"{name}=={version}" for name, version in sorted(pins.items())]


def cuda_requirements(export: str, replace: set[str]) -> list[str]:
    """Requirement lines from `uv export` without the packages in `replace`."""
    reqs = []
    for raw in export.splitlines():
        line = raw.split(" \\")[0].strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[=<>~!;\[ ]", line, maxsplit=1)[0].strip().lower()
        if line.startswith("-e") or name not in replace:
            reqs.append(line)
    return reqs


def _setup_cuda(spec: AdapterSpec) -> Path:
    python = _cuda_python(spec)
    if not python.exists():
        _check(["uv", "venv", "--quiet", "--python", "3.12", CUDA_ENV], spec, cwd=spec.path)
    pins = cuda_pins(spec)
    export = _check(
        [
            "uv",
            "export",
            "--frozen",
            "--no-hashes",
            "--no-emit-project",
            "--project",
            str(spec.path),
        ],
        spec,
    )
    replace = {p.split("==")[0] for p in pins}
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(cuda_requirements(export, replace)) + "\n")
    errors = []
    for index in CUDA_INDEXES:
        cmd = [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            str(python),
            "--index",
            index,
            "--index-strategy",
            "unsafe-best-match",
            "-r",
            f.name,
            *pins,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=spec.path, env=adapter_env())
        if proc.returncode == 0:
            return python
        errors.append(f"{index}: {proc.stderr.strip().splitlines()[-1:] or proc.returncode}")
    raise RuntimeError(f"CUDA setup of {spec.id} failed for {pins}: " + "; ".join(errors))


# Written by the harness once setup.py has finished. It lives in the git-ignored weights
# folder, so deleting the weights also drops it, and it is not part of any cache key.
SETUP_MARKER = Path("weights") / ".setup-complete"


def _environment_ready(spec: AdapterSpec, device: str) -> bool:
    """The environment that would run on `device` is complete. For the CPU environment that
    is what `uv sync --check --offline` says: a killed `uv sync` leaves a `.venv` behind
    without the packages."""
    variant = env_variant(spec, device)
    if variant == "rocm":
        return _rocm_python(spec).exists()
    if variant == "cuda":
        return _cuda_python(spec).exists()
    # without dependencies `uv sync --check` passes even when there is no environment at all
    if variant is None or not (spec.path / ".venv").is_dir():
        return False
    cmd = ["uv", "sync", "--check", "--offline", "--quiet", "--project", str(spec.path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, env=adapter_env())
    except OSError:  # no uv: nothing can run
        return False
    return proc.returncode == 0


def missing_setup(spec: AdapterSpec, device: str = "auto") -> list[str]:
    """What keeps the adapter from running on `device`: "environment" and/or "weights"
    (empty: set up). Weights count only once setup.py has finished (SETUP_MARKER)."""
    missing = [] if _environment_ready(spec, device) else ["environment"]
    if (spec.path / "setup.py").exists() and not (spec.path / SETUP_MARKER).exists():
        missing.append("weights")
    return missing


def _check_group(cmd: list[str], spec: AdapterSpec, cancel: threading.Event | None) -> None:
    """Like _check, in its own process group, so a set `cancel` kills it (raises Cancelled)."""
    try:
        proc = _run_group(cmd, None, cancel)
    except Cancelled:
        raise Cancelled(f"{spec.id}: setup cancelled") from None
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        raise RuntimeError(f"Setup of {spec.id} failed ({cmd[0]} {cmd[1]}):\n{tail}")


def needs_weights(spec: AdapterSpec) -> bool:
    """The adapter downloads weights in a setup.py."""
    return (spec.path / "setup.py").exists()


def setup_environment(
    spec: AdapterSpec, device: str = "cpu", cancel: threading.Event | None = None
) -> list[str]:
    """Builds the environment (cpu: uv sync, rocm: .venv-rocm, cuda: .venv-cuda); returns the
    command that runs Python in it. `cancel` kills a running `uv sync`; building the ROCm and
    CUDA environments (developer tools) is not cancelled midway."""
    if device not in SETUP_DEVICES:
        raise ValueError(f"device must be one of {SETUP_DEVICES}, not {device!r}")
    if device == "rocm":
        return [str(_setup_rocm(spec))]
    if device == "cuda":
        return [str(_setup_cuda(spec))]
    _check_group(["uv", "sync", "--quiet", "--project", str(spec.path)], spec, cancel)
    return ["uv", "run", "--quiet", "--project", str(spec.path), "python"]


def setup_weights(
    spec: AdapterSpec, python: list[str], cancel: threading.Event | None = None
) -> None:
    """Runs setup.py with `python` (from setup_environment). Stray `*.partial` downloads of an
    interrupted setup are removed first; SETUP_MARKER is written once setup.py has succeeded,
    so a failed or cancelled run leaves the weights not set up."""
    if not needs_weights(spec):
        return
    marker = spec.path / SETUP_MARKER
    marker.unlink(missing_ok=True)
    for partial in (spec.path / "weights").rglob("*.partial"):
        partial.unlink()
    _check_group([*python, str(spec.path / "setup.py")], spec, cancel)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")


def setup_adapter(
    spec: AdapterSpec, device: str = "cpu", cancel: threading.Event | None = None
) -> None:
    """setup_environment, then setup_weights."""
    setup_weights(spec, setup_environment(spec, device, cancel), cancel)
    log.info("%s: setup (%s) done", spec.id, device)
