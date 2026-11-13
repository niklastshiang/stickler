"""Run a benchmark config on a rented GPU (e.g. a RunPod pod) over SSH, for development only.

Steps: bootstrap the host (rsync, ffmpeg, uv), upload code (git-tracked files), the audio the
config needs and the cache, build CUDA environments, run with `--device gpu`, download new
cache entries, and stop the pod if a RunPod pod id and API key are given, also on failure.

With `wipe`, everything uploaded (code, data, cache, own songs) is deleted from the host after
the cache has been downloaded and before the pod is stopped, also on failure: for data whose
licence forbids leaving it on third-party machines (ENST-Drums) and for the owner's music.

Secrets never appear on a command line or on disk: the Hugging Face token is sent on the SSH
session's stdin, the RunPod API key only goes into an HTTPS header.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from stickler.datasets import own
from stickler.runner import BUILTIN_SEPARATORS

REMOTE_DIR = "stickler"
# REST API v2 (v1 on rest.runpod.io is being retired and rejects the new scoped keys)
RUNPOD_API = "https://api.runpod.io/v2"
# Cloudflare in front of the RunPod API rejects Python's default user agent (error 1010).
USER_AGENT = "stickler (+https://github.com/niklastshiang/stickler)"
# Checked before anything is uploaded (lessons of 2026-11-13: one pod ran out of disk during
# setup, another could not reach github.com; both failed only after a long upload).
MIN_FREE_GB = 45  # CUDA environments of all models ~38 GB, plus data and cache
PREFLIGHT_URLS = (
    "https://pypi.org",  # packages
    "https://files.pythonhosted.org",
    "https://download.pytorch.org",  # CUDA builds of torch
    "https://huggingface.co",  # weights
    "https://github.com",  # uv installer, some packages
)
# Adapters whose weights come from GitHub releases: uploaded from the local copy, because a pod
# could not reach github.com on 2026-11-13 (Hugging Face downloads work and are faster there).
UPLOAD_WEIGHTS = {"roformer": "adapters/separators/roformer/weights"}
SSH_OPTIONS = ["-o", "ServerAliveInterval=30", "-o", "StrictHostKeyChecking=accept-new"]
BOOTSTRAP = (
    "command -v rsync >/dev/null && command -v ffmpeg >/dev/null && command -v zstd >/dev/null || "
    "(apt-get update -qq && DEBIAN_FRONTEND=noninteractive "
    "apt-get install -y -qq rsync ffmpeg zstd)"
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
    # own songs' recordings: (local path, song folder relative to the project root); they are
    # uploaded into the song folder, where the file-name lookup (datasets.own) finds them first
    audio: list[tuple[str, str]] = field(default_factory=list)
    # cache entries the run needs ("<adapter>/<key>"); None uploads the whole cache
    cache: list[str] | None = None
    # datasets the host downloads itself (faster from a data centre than an upload from home)
    fetch: list[str] = field(default_factory=list)


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


def tracked_files(root: Path) -> list[str]:
    proc = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root)
    return [line for line in proc.stdout.splitlines() if line]


def sync_plan(
    config: Path, *, project_root: Path, references_dir: Path, data_dir: Path
) -> SyncPlan:
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    data_dirs, data_files, audio, fetch = [], [], [], []
    for name in raw.get("datasets", []):
        if name == "mdb":
            data_dirs.append(str((data_dir / name).relative_to(project_root)))
        elif name == "enst":
            fetch.append(name)
        elif name == "own":
            for track in own.tracks(references_dir, data_dir):
                aligned = data_dir / "own" / track.id / "aligned.json"
                data_files.append(str(aligned.relative_to(project_root)))
                song_dir = str((data_dir / "own" / track.id).relative_to(project_root))
                audio.append((str(track.mix), song_dir))
    for adapter in adapters_for(config):
        weights = UPLOAD_WEIGHTS.get(adapter)
        if weights and (project_root / weights).is_dir():
            data_dirs.append(weights)
    return SyncPlan(tracked_files(project_root), data_dirs, data_files, audio, fetch=fetch)


def remote_script(config: str, adapter_ids: list[str], fetch: list[str] = ()) -> str:
    """Bash script run on the host; the first stdin line is the Hugging Face token."""
    # The environments hold copies of their packages; the uv cache (~18 GB with CUDA torch) only
    # fills the pod's disk, so it is cleaned after every setup (cleaning once after all of them
    # overflowed the 60 GB disk on 2026-11-13).
    setups = "\n".join(
        f"uv run stickler setup --adapter {a} --device cuda\nuv cache clean || true"
        for a in adapter_ids
    )
    fetches = "\n".join(f"uv run stickler fetch {name}" for name in fetch)
    return f"""set -euo pipefail
read -r HF_TOKEN || true
export HF_TOKEN
export PATH="$HOME/.local/bin:$PATH"
cd ~/{REMOTE_DIR}
uv sync --quiet
{setups}
{fetches}
uv run stickler doctor || true
uv run stickler run --config {config} --device gpu
uv run stickler eval --config {config}
"""


def stop_pod(pod_id: str, api_key: str, opener: Callable = urllib.request.urlopen) -> None:
    """Stops a RunPod pod (`POST /v2/pods/{id}/action {"action": "stop"}`). A pod that is
    already stopped (409) is fine; any other error raises RuntimeError."""
    request = urllib.request.Request(
        f"{RUNPOD_API}/pods/{pod_id}/action",
        data=json.dumps({"action": "stop"}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(request, timeout=60) as response:
            if response.status not in (200, 202, 204):
                raise RuntimeError(f"RunPod: stopping pod {pod_id} failed ({response.status})")
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise RuntimeError(f"RunPod: stopping pod {pod_id} failed ({exc.code})") from None


def preflight_command() -> str:
    """Fails with a readable message if the host lacks disk space or cannot reach a source."""
    checks = [
        f'free=$(df -BG --output=avail ~ | tail -1 | tr -dc 0-9); [ "$free" -ge {MIN_FREE_GB} ] '
        f'|| {{ echo "only ${{free}} GB free, need {MIN_FREE_GB} GB" >&2; exit 1; }}'
    ]
    checks += [
        f"curl -sS -o /dev/null --max-time 20 -I {url} "
        f'|| {{ echo "cannot reach {url}" >&2; exit 1; }}'
        for url in PREFLIGHT_URLS
    ]
    return " && ".join(checks)


def wipe_command(plan: SyncPlan) -> str:
    """Deletes the project folder, which holds everything uploaded (code, data, songs, cache)."""
    return f"rm -rf ~/{REMOTE_DIR}"


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
    hf_token: str,
    stop: Callable[[], None] | None = None,
    execute: Callable = subprocess.run,
    wipe: bool = False,
) -> None:
    """Upload, run and download; `stop` (e.g. stop the pod) runs in any case at the end,
    after the optional wipe (see module docstring)."""

    def run(cmd: list[str], step: str, stdin: str | None = None, live: bool = False) -> None:
        # live: show the long benchmark run in the terminal instead of buffering it
        _ok(execute(cmd, input=stdin, capture_output=not live, text=True), step)

    def upload(files: list[str], base: Path, dest: str, step: str) -> None:
        if files:
            listing = "\n".join(files) + "\n"
            run(rsync_command(host, ["--files-from=-"], f"{base}/", dest), step, listing)

    cache_down = rsync_command(
        host, ["--update"], f":{REMOTE_DIR}/cache/", f"{project_root / 'cache'}/"
    )
    downloaded = False
    try:
        run([*ssh_command(host), BOOTSTRAP], "bootstrap")
        run([*ssh_command(host), preflight_command()], "preflight")
        root = project_root
        upload(plan.code + plan.data_files, root, f"{REMOTE_DIR}/", "code upload")
        for d in plan.data_dirs:
            dest = f"{REMOTE_DIR}/{d}/"
            run(rsync_command(host, ["--mkpath"], f"{root / d}/", dest), "data upload")
        for local, song_dir in plan.audio:
            dest = f"{REMOTE_DIR}/{song_dir}/"
            run(rsync_command(host, ["--mkpath"], local, dest), "audio upload")
        if plan.cache is None:
            run(
                rsync_command(host, [], f"{root / 'cache'}/", f"{REMOTE_DIR}/cache/"),
                "cache upload",
            )
        elif plan.cache:
            listing = "\n".join(plan.cache) + "\n"
            cmd = rsync_command(
                host,
                ["-r", "--mkpath", "--files-from=-"],
                f"{root / 'cache'}/",
                f"{REMOTE_DIR}/cache/",
            )
            run(cmd, "cache upload", listing)
        script = remote_script(config, adapter_ids, plan.fetch)
        # script as argument (not secret), token as the only stdin line (read -r HF_TOKEN)
        run([*ssh_command(host), f"bash -c {shlex.quote(script)}"], "run", f"{hf_token}\n", True)
        run(cache_down, "cache download")
        downloaded = True
        # Scores computed on the host: GPU cache entries count as local cache hits only after
        # the device-independent cache migration (tasks: Task 20).
        stem = Path(config).stem
        results = "results/" if stem == "benchmark" else f"results/{stem}/"  # see results_dir_for
        (root / results).mkdir(parents=True, exist_ok=True)
        run(rsync_command(host, [], f":{REMOTE_DIR}/{results}", f"{root / results}/"), "results")
    finally:
        try:
            if wipe:
                if not downloaded:  # keep what the failed run computed, if anything
                    execute(cache_down, input=None, capture_output=True, text=True)
                run([*ssh_command(host), wipe_command(plan)], "wipe")
        finally:
            if stop is not None:
                stop()
