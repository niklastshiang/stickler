"""Adapter-Vertrag: Modelle laufen als Subprozess in ihrer eigenen uv-Umgebung.

Aufruf:  uv run --project <adapter> python <adapter>/run.py --in <audio> --out <dir> --device <d>
Ergebnis: Stufen-Ausgabe + meta.json, bei Fehlern error.log. Der Harness bricht nie ab.

GPU (AMD ROCm): Adapter, die in ihrem pyproject.toml `[tool.stickler.rocm]` deklarieren, bekommen
mit `setup_adapter(spec, device="rocm")` eine zweite Umgebung `.venv-rocm`. Darin sind die
CPU-Torch-Pakete durch die ROCm-Wheels von AMD ersetzt, alle anderen Versionen kommen aus dem Lock.
"""

from __future__ import annotations

import json
import logging
import re
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


@dataclass(frozen=True)
class RocmConfig:
    index: str
    replace: list[str]
    packages: list[str]
    # False: bei device="auto" trotzdem CPU (wenn die GPU für dieses Modell langsamer ist)
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
    """Welche Umgebung läuft: 'rocm' (falls gebaut und nicht cpu verlangt), sonst 'cpu'.
    Bei 'auto' entscheidet zusätzlich `prefer_gpu`. None, wenn 'gpu' verlangt ist, aber keine
    ROCm-Umgebung existiert."""
    has_rocm = _rocm_python(spec).exists()
    if device == "cpu":
        return "cpu"
    if device == "gpu":
        return "rocm" if has_rocm else None
    cfg = rocm_config(spec) if has_rocm else None
    return "rocm" if cfg and cfg.prefer_gpu else "cpu"


def rocm_requirements(spec: AdapterSpec, replace: list[str]) -> list[str]:
    """Direkte Abhängigkeiten aus pyproject.toml ohne die zu ersetzenden Pakete.

    Bewusst nicht der CPU-Lock: dessen transitive Pins (z. B. setuptools) passen nicht zu den
    ROCm-Wheels. Pfad-Quellen aus [tool.uv.sources] werden zu `-e <pfad>`.
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
    """Findet `root/<stufe>/<id>/run.py`. Ordner mit `_` am Anfang werden übersprungen."""
    found: dict[str, AdapterSpec] = {}
    for run_py in sorted(root.glob("*/*/run.py")):
        adapter_dir = run_py.parent
        stage = adapter_dir.parent.name
        if stage.startswith("_"):
            continue
        if stage not in OUTPUTS:
            raise ValueError(f"Unbekannte Stufe {stage!r} in {adapter_dir}")
        found[adapter_dir.name] = AdapterSpec(id=adapter_dir.name, stage=stage, path=adapter_dir)
    return found


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
        raise ValueError(f"device muss eines von {DEVICES} sein, nicht {device!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    variant = env_variant(spec, device)
    if variant is None:
        return _fail(
            out_dir,
            f"{spec.id}: GPU verlangt, aber keine ROCm-Umgebung. "
            f"Zuerst: stickler setup --adapter {spec.id} --device rocm",
        )
    if variant == "rocm":
        python = [str(_rocm_python(spec))]
    else:
        python = ["uv", "run", "--quiet", "--project", str(spec.path), "python"]
    args = ["--in", str(audio), "--out", str(out_dir), "--device", device]
    cmd = [*python, str(spec.path / "run.py"), *args]
    log.info("%s: %s", spec.id, audio.name)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _fail(out_dir, f"{spec.id}: Zeitlimit {timeout} s überschritten")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        return _fail(out_dir, f"{spec.id} (Exit {proc.returncode}):\n{tail}")
    output = out_dir / spec.expected_output
    meta_path = out_dir / "meta.json"
    if not output.exists() or not meta_path.exists():
        return _fail(out_dir, f"{spec.id}: {spec.expected_output} oder meta.json fehlt")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return AdapterResult(ok=True, output=output, meta=meta, error=None)


def _check(cmd: list[str], spec: AdapterSpec, **kw) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        raise RuntimeError(f"Setup von {spec.id} fehlgeschlagen ({cmd[0]} {cmd[1]}):\n{tail}")
    return proc.stdout


def _setup_rocm(spec: AdapterSpec) -> Path:
    cfg = rocm_config(spec)
    if cfg is None:
        raise RuntimeError(f"{spec.id} deklariert keine ROCm-Pakete ([tool.stickler.rocm])")
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
    """Baut die Umgebung (cpu: uv sync, rocm: .venv-rocm) und führt ggf. setup.py aus."""
    if device not in SETUP_DEVICES:
        raise ValueError(f"device muss eines von {SETUP_DEVICES} sein, nicht {device!r}")
    if device == "rocm":
        python = [str(_setup_rocm(spec))]
    else:
        _check(["uv", "sync", "--quiet", "--project", str(spec.path)], spec)
        python = ["uv", "run", "--quiet", "--project", str(spec.path), "python"]
    if (spec.path / "setup.py").exists():
        _check([*python, str(spec.path / "setup.py")], spec)
    log.info("%s: Setup (%s) fertig", spec.id, device)
