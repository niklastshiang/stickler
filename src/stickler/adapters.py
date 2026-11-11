"""Adapter-Vertrag: Modelle laufen als Subprozess in ihrer eigenen uv-Umgebung.

Aufruf:  uv run --project <adapter> python <adapter>/run.py --in <audio> --out <dir> --device <d>
Ergebnis: Stufen-Ausgabe + meta.json, bei Fehlern error.log. Der Harness bricht nie ab.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

OUTPUTS = {"separators": "drums.wav", "transcribers": "drums.mid", "beats": "beats.json"}
DEVICES = ("auto", "cpu", "gpu")


@dataclass(frozen=True)
class AdapterSpec:
    id: str
    stage: str
    path: Path

    @property
    def expected_output(self) -> str:
        return OUTPUTS[self.stage]


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
    cmd = [
        "uv",
        "run",
        "--quiet",
        "--project",
        str(spec.path),
        "python",
        str(spec.path / "run.py"),
        "--in",
        str(audio),
        "--out",
        str(out_dir),
        "--device",
        device,
    ]
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


def setup_adapter(spec: AdapterSpec) -> None:
    """Baut die uv-Umgebung des Adapters und führt ggf. dessen setup.py aus (Gewichte laden)."""
    steps = [["uv", "sync", "--quiet", "--project", str(spec.path)]]
    if (spec.path / "setup.py").exists():
        steps.append(
            [
                "uv",
                "run",
                "--quiet",
                "--project",
                str(spec.path),
                "python",
                str(spec.path / "setup.py"),
            ]
        )
    for cmd in steps:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
            raise RuntimeError(f"Setup von {spec.id} fehlgeschlagen:\n{tail}")
    log.info("%s: Setup fertig", spec.id)
