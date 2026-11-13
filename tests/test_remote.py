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
    # the CUDA environments are copies, so the uv cache (~18 GB) only fills the pod's disk;
    # it is cleaned after every single setup (all at once overflowed 60 GB on 2026-11-13)
    lines = script.splitlines()
    for i, line in enumerate(lines):
        if "stickler setup" in line:
            assert lines[i + 1].startswith("uv cache clean")
    assert script.rindex("uv cache clean") < script.index("stickler run")


def test_adapters_for_config_skips_builtin_separators(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "datasets: [mdb]\nseparators: [none, oracle, demucs]\ntranscribers: [adtof]\n",
        encoding="utf-8",
    )
    assert remote.adapters_for(cfg) == ["demucs", "adtof"]


def test_sync_plan_uploads_the_enst_folder(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("datasets: [mdb, enst]\nseparators: [none]\ntranscribers: [adtof]\n")
    monkeypatch.setattr(remote, "tracked_files", lambda root: [])
    plan = remote.sync_plan(
        cfg,
        project_root=tmp_path,
        references_dir=tmp_path,
        data_dir=tmp_path / "data",
    )
    assert plan.data_dirs == ["data/mdb", "data/enst"]


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
        audio=[("/music/Playlist/a.flac", "data/own/a")],
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
        hf_token="secret-token",
        stop=lambda: stopped.append(True),
        execute=rec,
    )
    cmds = [c for c, _ in rec.calls]
    assert cmds[0][0] == "ssh" and "apt-get" in cmds[0][-1]  # bootstrap: rsync, ffmpeg
    rsyncs = [c for c in cmds if c[0] == "rsync"]
    assert any(c[-1].endswith(":stickler/cache/") for c in rsyncs)  # cache up
    song_up = [c for c in rsyncs if c[-1].endswith(":stickler/data/own/a/")]
    assert song_up and song_up[0][-2] == "/music/Playlist/a.flac" and "--mkpath" in song_up[0]
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
    audio = tmp_path / "music" / "Playlist" / "s.mp3"
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
    plan = remote.sync_plan(cfg, project_root=tmp_path, references_dir=refs, data_dir=data)
    assert plan.code == ["pyproject.toml"]
    assert plan.data_files == ["data/own/s/aligned.json"]
    # into the song folder on the host, where the file-name lookup finds it first
    assert plan.audio == [(str(audio), "data/own/s")] and plan.data_dirs == []
    assert Path("data/own/s/aligned.json") == Path(plan.data_files[0])


def test_wipe_deletes_uploads_after_download_and_before_stop(tmp_path, plan):
    rec = Recorder()
    events = []
    remote.run_remote(
        HOST,
        "config/enst.yaml",
        ["demucs"],
        plan,
        project_root=tmp_path,
        hf_token="",
        stop=lambda: events.append("stop"),
        execute=lambda cmd, **kw: events.append(cmd) or rec(cmd, **kw),
        wipe=True,
    )
    wipe = [i for i, e in enumerate(events) if e != "stop" and "rm -rf" in e[-1]]
    assert len(wipe) == 1
    cmd = events[wipe[0]][-1]
    assert cmd == "rm -rf ~/stickler"  # the songs were uploaded into the project folder
    cache_down = max(
        i for i, e in enumerate(events) if e != "stop" and e[-2].endswith(":stickler/cache/")
    )
    assert cache_down < wipe[0] < events.index("stop")


def test_wipe_after_a_failed_run_still_tries_to_save_the_cache(tmp_path, plan):
    rec = Recorder(fail_on="bash")
    with pytest.raises(RuntimeError, match="remote run"):
        remote.run_remote(
            HOST,
            "config/enst.yaml",
            ["demucs"],
            plan,
            project_root=tmp_path,
            hf_token="",
            execute=rec,
            wipe=True,
        )
    cmds = [c for c, _ in rec.calls]
    down = [i for i, c in enumerate(cmds) if c[0] == "rsync" and c[-2].endswith(":stickler/cache/")]
    wipe = [i for i, c in enumerate(cmds) if "rm -rf" in c[-1]]
    assert down and wipe and down[0] < wipe[0]


def test_data_upload_creates_missing_parent_folders(tmp_path, plan):
    rec = Recorder()
    remote.run_remote(HOST, "c.yaml", [], plan, project_root=tmp_path, hf_token="", execute=rec)
    data_up = [c for c, _ in rec.calls if c[0] == "rsync" and c[-1].endswith(":stickler/data/mdb/")]
    assert data_up and "--mkpath" in data_up[0]  # a fresh host has no stickler/data/ yet


def test_songs_from_anywhere_go_into_their_own_song_folders(tmp_path, monkeypatch):
    """Recordings no longer need to be below the home folder (paths are never mirrored)."""
    refs, data = tmp_path / "refs", tmp_path / "data"
    refs.mkdir()
    for sid in ("a", "b"):
        audio = tmp_path / "anywhere" / sid / f"{sid}.flac"
        audio.parent.mkdir(parents=True)
        audio.write_bytes(sid.encode())
        (refs / f"{sid}.yaml").write_text(f'title: "{sid}"\naudio: "{audio}"\n', encoding="utf-8")
        from stickler.datasets import own

        (song,) = [s for s in own.songs(refs, data) if s.id == sid]
        own.save_alignment(song, notes=[], excluded=[], quality={}, reasons=[], shift=0.0)
    cfg = tmp_path / "c.yaml"
    cfg.write_text("datasets: [own]\nseparators: [none]\ntranscribers: [adtof]\n")
    monkeypatch.setattr(remote, "tracked_files", lambda root: [])
    plan = remote.sync_plan(cfg, project_root=tmp_path, references_dir=refs, data_dir=data)
    assert [d for _, d in plan.audio] == ["data/own/a", "data/own/b"]
    assert all(Path(local).exists() for local, _ in plan.audio)


def test_only_the_listed_cache_entries_are_uploaded(tmp_path):
    rec = Recorder()
    plan = remote.SyncPlan(code=["pyproject.toml"], cache=["adtof/0123", "demucs/4567"])
    remote.run_remote(HOST, "c.yaml", [], plan, project_root=tmp_path, hf_token="", execute=rec)
    up = [(c, i) for c, i in rec.calls if c[0] == "rsync" and c[-1].endswith(":stickler/cache/")]
    assert len(up) == 1
    cmd, listing = up[0]
    assert "--files-from=-" in cmd and "-r" in cmd
    assert listing.split() == ["adtof/0123", "demucs/4567"]


def test_weights_from_github_releases_are_uploaded(tmp_path, monkeypatch):
    """RoFormer's weights come from GitHub releases, which a pod could not reach (2026-11-13)."""
    root = tmp_path
    w = root / "adapters" / "separators" / "roformer" / "weights"
    w.mkdir(parents=True)
    (w / "model.ckpt").write_bytes(b"x")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("datasets: [mdb]\nseparators: [none, roformer, demucs]\ntranscribers: [adtof]\n")
    monkeypatch.setattr(remote, "tracked_files", lambda r: [])
    plan = remote.sync_plan(cfg, project_root=root, references_dir=root, data_dir=root / "data")
    assert plan.data_dirs == ["data/mdb", "adapters/separators/roformer/weights"]


def test_preflight_runs_before_any_upload(tmp_path, plan):
    rec = Recorder()
    remote.run_remote(HOST, "c.yaml", [], plan, project_root=tmp_path, hf_token="", execute=rec)
    cmds = [c for c, _ in rec.calls]
    pre = next(i for i, c in enumerate(cmds) if c[0] == "ssh" and "df " in c[-1])
    first_upload = next(i for i, c in enumerate(cmds) if c[0] == "rsync")
    assert 0 < pre < first_upload
    for host in ("huggingface.co", "github.com", "pypi.org", "download.pytorch.org"):
        assert host in cmds[pre][-1]


def test_failed_preflight_uploads_nothing(tmp_path, plan):
    rec = Recorder(fail_on="df ")
    with pytest.raises(RuntimeError, match="preflight"):
        remote.run_remote(HOST, "c.yaml", [], plan, project_root=tmp_path, hf_token="", execute=rec)
    assert not [c for c, _ in rec.calls if c[0] == "rsync"]
