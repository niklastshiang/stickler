"""Tests for running a benchmark config on a rented GPU over SSH (all commands mocked)."""

import json
import subprocess
from pathlib import Path

import pytest

from stickler import remote

HOST = remote.Host("root@203.0.113.7", 22077)


def test_ssh_and_rsync_use_the_port_and_keepalive():
    ssh = remote.ssh_command(HOST)
    assert ssh[:3] == ["ssh", "-p", "22077"] and ssh[-1] == "root@203.0.113.7"
    assert "ServerAliveInterval=30" in ssh
    rsync = remote.rsync_command(HOST, ["--files-from=x"], "src/", "dst/")
    assert rsync[0] == "rsync" and "-e" in rsync
    assert "ssh -p 22077" in rsync[rsync.index("-e") + 1]
    assert rsync[-1] == "root@203.0.113.7:dst/"


def test_script_installs_tools_sets_up_cuda_and_runs_on_gpu():
    script = remote.remote_script("config/own.yaml", ["demucs", "adt_str"])
    assert "read -r HF_TOKEN" in script and "export HF_TOKEN" in script
    assert "stickler setup --adapter demucs --device cuda" in script
    assert "stickler setup --adapter adt_str --device cuda" in script
    assert "stickler run --config config/own.yaml --device gpu" in script
    assert "stickler eval --config config/own.yaml" in script
    assert script.index("setup --adapter") < script.index("stickler run")
    assert script.index("stickler run") < script.index("stickler eval")


def test_adapters_for_config_skips_builtin_separators(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "datasets: [mdb]\nseparators: [none, oracle, demucs]\ntranscribers: [adtof]\n",
        encoding="utf-8",
    )
    assert remote.adapters_for(cfg) == ["demucs", "adtof"]


def test_own_song_audio_is_mirrored_relative_to_home(tmp_path):
    home = tmp_path / "home"
    audio = home / "Musik" / "a.flac"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")
    assert remote.home_relative([audio], home) == ["Musik/a.flac"]
    with pytest.raises(ValueError, match="home"):
        remote.home_relative([tmp_path / "elsewhere.flac"], home)


class Recorder:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[list[str], str | None]] = []
        self.fail_on = fail_on

    def __call__(self, cmd, input=None, **kw):
        self.calls.append((cmd, input))
        if self.fail_on and any(self.fail_on in part for part in cmd):
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def plan(tmp_path):
    return remote.SyncPlan(
        code=["src/stickler/api.py", "pyproject.toml"],
        data_dirs=["data/mdb"],
        data_files=["data/own/x/aligned.json"],
        home_files=["Musik/a.flac"],
    )


def test_run_remote_order_and_secret_on_stdin(tmp_path, plan):
    rec = Recorder()
    stopped = []
    remote.run_remote(
        HOST,
        "config/own.yaml",
        ["demucs"],
        plan,
        project_root=tmp_path,
        home=tmp_path,
        hf_token="secret-token",
        stop=lambda: stopped.append(True),
        execute=rec,
    )
    cmds = [c for c, _ in rec.calls]
    assert cmds[0][0] == "ssh" and "apt-get" in cmds[0][-1]  # bootstrap: rsync, ffmpeg
    rsyncs = [c for c in cmds if c[0] == "rsync"]
    assert any(c[-1].endswith(":stickler/cache/") for c in rsyncs)  # cache up
    cache_down = [c for c in rsyncs if c[-2].endswith(":stickler/cache/")]
    assert cache_down and cache_down[0][-1].endswith("cache/")
    results_down = rsyncs[-1]
    assert results_down[-2].endswith(":stickler/results/own/")
    assert results_down[-1].endswith("results/own/")
    script_call = next((c, i) for c, i in rec.calls if c[0] == "ssh" and i)
    assert script_call[1].startswith("secret-token\n")
    assert all("secret-token" not in part for c in cmds for part in c)
    assert stopped == [True]


def test_pod_is_stopped_even_if_the_run_fails(tmp_path, plan):
    rec = Recorder(fail_on="bash")
    stopped = []
    with pytest.raises(RuntimeError, match="remote"):
        remote.run_remote(
            HOST,
            "config/own.yaml",
            ["demucs"],
            plan,
            project_root=tmp_path,
            home=tmp_path,
            hf_token="",
            stop=lambda: stopped.append(True),
            execute=rec,
        )
    assert stopped == [True]


class _Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_stop_pod_calls_the_runpod_api_v2():
    seen = {}

    def opener(request, timeout):
        seen["url"], seen["method"] = request.full_url, request.get_method()
        seen["auth"] = request.get_header("Authorization")
        seen["agent"] = request.get_header("User-agent")
        seen["body"] = json.loads(request.data)
        return _Response(200)

    remote.stop_pod("abc123", "key", opener=opener)
    assert seen == {
        "url": "https://api.runpod.io/v2/pods/abc123/action",
        "method": "POST",
        "auth": "Bearer key",
        "agent": remote.USER_AGENT,  # Cloudflare blocks Python's default agent (error 1010)
        "body": {"action": "stop"},
    }


def test_stop_pod_already_stopped_is_fine():
    import urllib.error

    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 409, "Conflict", {}, None)

    remote.stop_pod("abc123", "key", opener=opener)


def test_stop_pod_rejected_key_raises():
    import urllib.error

    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    with pytest.raises(RuntimeError, match="401"):
        remote.stop_pod("abc123", "key", opener=opener)


def test_sync_plan_for_own_songs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    audio = home / "Musik" / "s.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")
    refs, data = tmp_path / "refs", tmp_path / "data"
    refs.mkdir()
    (refs / "s.yaml").write_text(f'title: "S"\naudio: "{audio}"\n', encoding="utf-8")
    from stickler.datasets import own

    (song,) = own.songs(refs, data)
    own.save_alignment(song, notes=[], excluded=[], quality={}, reasons=[], shift=0.0)
    cfg = tmp_path / "c.yaml"
    cfg.write_text("datasets: [own]\nseparators: [demucs]\ntranscribers: [adtof]\n")
    monkeypatch.setattr(remote, "tracked_files", lambda root: ["pyproject.toml"])
    plan = remote.sync_plan(
        cfg, project_root=tmp_path, references_dir=refs, data_dir=data, home=home
    )
    assert plan.code == ["pyproject.toml"]
    assert plan.data_files == ["data/own/s/aligned.json"]
    assert plan.home_files == ["Musik/s.mp3"] and plan.data_dirs == []
    assert Path("data/own/s/aligned.json") == Path(plan.data_files[0])
