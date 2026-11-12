"""Run a benchmark config on a rented GPU (e.g. a RunPod pod) over SSH, for development only.

Steps: bootstrap the host (rsync, ffmpeg, uv), upload code (git-tracked files), the audio the
config needs and the cache, build CUDA environments, run with `--device gpu`, download new
cache entries, and stop the pod if a RunPod pod id and API key are given, also on failure.

Secrets never appear on a command line or on disk: the Hugging Face token is sent on the SSH
session's stdin, the RunPod API key only goes into an HTTPS header.
"""

from __future__ import annotations

import shlex
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from stickler.datasets import own
from stickler.runner import BUILTIN_SEPARATORS

REMOTE_DIR = "stickler"
RUNPOD_API = "https://rest.runpod.io/v1"
SSH_OPTIONS = ["-o", "ServerAliveInterval=30", "-o", "StrictHostKeyChecking=accept-new"]
BOOTSTRAP = (
    "command -v rsync >/dev/null && command -v ffmpeg >/dev/null || "
    "(apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync ffmpeg)"
    " && (command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh)"
)


@dataclass(frozen=True)
class Host:
    target: str  # user@address
    port: int = 22


@dataclass(frozen=True)
class SyncPlan:
    code: list[str]  # git-tracked files, relative to the project root
    data_dirs: list[str] = field(default_factory=list)  # relative to the project root
    data_files: list[str] = field(default_factory=list)  # relative to the project root
    home_files: list[str] = field(default_factory=list)  # own songs' audio, relative to ~


def ssh_command(host: Host) -> list[str]:
    return ["ssh", "-p", str(host.port), *SSH_OPTIONS, host.target]


def rsync_command(host: Host, options: list[str], source: str, dest: str) -> list[str]:
    """rsync to the host (dest is remote) or from it (source starting with ':')."""
    shell = " ".join(["ssh", "-p", str(host.port), *SSH_OPTIONS])
    remote = f"{host.target}:"
    src = remote + source[1:] if source.startswith(":") else source
    dst = dest if source.startswith(":") else remote + dest
    return ["rsync", "-az", "--partial", "-e", shell, *options, src, dst]


def adapters_for(config: Path) -> list[str]:
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    seps = [s for s in raw.get("separators", []) if s not in BUILTIN_SEPARATORS]
    return [*seps, *raw.get("transcribers", [])]


def home_relative(files: list[Path], home: Path) -> list[str]:
    out = []
    for f in files:
        try:
            out.append(str(f.resolve().relative_to(home.resolve())))
        except ValueError:
            raise ValueError(f"{f} is not below the home folder {home}") from None
    return out


def tracked_files(root: Path) -> list[str]:
    proc = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root)
    return [line for line in proc.stdout.splitlines() if line]


def sync_plan(
    config: Path, *, project_root: Path, references_dir: Path, data_dir: Path, home: Path
) -> SyncPlan:
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    data_dirs, data_files, audio = [], [], []
    for name in raw.get("datasets", []):
        if name == "mdb":
            data_dirs.append(str((data_dir / "mdb").relative_to(project_root)))
        elif name == "own":
            for track in own.tracks(references_dir, data_dir):
                aligned = data_dir / "own" / track.id / "aligned.json"
                data_files.append(str(aligned.relative_to(project_root)))
                audio.append(track.mix)
    return SyncPlan(tracked_files(project_root), data_dirs, data_files, home_relative(audio, home))


def remote_script(config: str, adapter_ids: list[str]) -> str:
    """Bash script run on the host; the first stdin line is the Hugging Face token."""
    setups = "\n".join(f"uv run stickler setup --adapter {a} --device cuda" for a in adapter_ids)
    return f"""set -euo pipefail
read -r HF_TOKEN || true
export HF_TOKEN
export PATH="$HOME/.local/bin:$PATH"
cd ~/{REMOTE_DIR}
uv sync --quiet
{setups}
uv run stickler doctor || true
uv run stickler run --config {config} --device gpu
uv run stickler eval --config {config}
"""


def stop_pod(pod_id: str, api_key: str, opener: Callable = urllib.request.urlopen) -> None:
    request = urllib.request.Request(
        f"{RUNPOD_API}/pods/{pod_id}/stop",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with opener(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"RunPod: stopping pod {pod_id} failed ({response.status})")


def _ok(proc: subprocess.CompletedProcess, step: str) -> None:
    if proc.returncode != 0:
        tail = (proc.stderr or "see output above").strip().splitlines()[-5:]
        raise RuntimeError(f"remote {step} failed (exit {proc.returncode}): {' | '.join(tail)}")


def run_remote(
    host: Host,
    config: str,
    adapter_ids: list[str],
    plan: SyncPlan,
    *,
    project_root: Path,
    home: Path,
    hf_token: str,
    stop: Callable[[], None] | None = None,
    execute: Callable = subprocess.run,
) -> None:
    """Upload, run and download; `stop` (e.g. stop the pod) runs in any case at the end."""

    def run(cmd: list[str], step: str, stdin: str | None = None, live: bool = False) -> None:
        # live: show the long benchmark run in the terminal instead of buffering it
        _ok(execute(cmd, input=stdin, capture_output=not live, text=True), step)

    def upload(files: list[str], base: Path, dest: str, step: str) -> None:
        if files:
            listing = "\n".join(files) + "\n"
            run(rsync_command(host, ["--files-from=-"], f"{base}/", dest), step, listing)

    try:
        run([*ssh_command(host), BOOTSTRAP], "bootstrap")
        root = project_root
        upload(plan.code + plan.data_files, root, f"{REMOTE_DIR}/", "code upload")
        for d in plan.data_dirs:
            run(rsync_command(host, [], f"{root / d}/", f"{REMOTE_DIR}/{d}/"), "data upload")
        upload(plan.home_files, home, "", "audio upload")
        run(rsync_command(host, [], f"{root / 'cache'}/", f"{REMOTE_DIR}/cache/"), "cache upload")
        script = remote_script(config, adapter_ids)
        # script as argument (not secret), token as the only stdin line (read -r HF_TOKEN)
        run([*ssh_command(host), f"bash -c {shlex.quote(script)}"], "run", f"{hf_token}\n", True)
        run(
            rsync_command(host, ["--update"], f":{REMOTE_DIR}/cache/", f"{root / 'cache'}/"),
            "cache download",
        )
        # Scores computed on the host: GPU cache entries count as local cache hits only after
        # the device-independent cache migration (tasks: Task 20).
        stem = Path(config).stem
        results = "results/" if stem == "benchmark" else f"results/{stem}/"  # see results_dir_for
        (root / results).mkdir(parents=True, exist_ok=True)
        run(rsync_command(host, [], f":{REMOTE_DIR}/{results}", f"{root / results}/"), "results")
    finally:
        if stop is not None:
            stop()
