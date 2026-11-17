"""Tests for the adapter contract (subprocess, meta.json, error log, extensibility)."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from stickler import adapters
from stickler.midi import read_drum_notes

FIXTURES = Path(__file__).parent / "fixtures" / "adapters"


@pytest.fixture(scope="module")
def registry():
    return adapters.discover(FIXTURES)


def test_discover_finds_adapters_by_folder(registry):
    assert set(registry) == {"dummy", "broken", "copysep", "stemonly", "sleepy"}
    assert registry["dummy"].stage == "transcribers"
    assert registry["dummy"].expected_output == "drums.mid"


def test_discover_ignores_folders_without_run_py(tmp_path):
    (tmp_path / "transcribers" / "halb").mkdir(parents=True)
    assert adapters.discover(tmp_path) == {}


def test_discover_rejects_unknown_stage(tmp_path):
    d = tmp_path / "mixers" / "x"
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="mixers"):
        adapters.discover(tmp_path)


def test_dummy_adapter_runs_and_writes_meta(registry, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"")
    result = adapters.run_adapter(registry["dummy"], audio, tmp_path / "out", device="cpu")
    assert result.ok, result.error
    assert result.output == tmp_path / "out" / "drums.mid"
    assert read_drum_notes(result.output) == [(0.5, 36), (1.0, 38)]
    meta = json.loads((tmp_path / "out" / "meta.json").read_text())
    assert meta["adapter"] == "dummy"
    assert meta["version"] == "1.0"
    assert meta["device"] == "cpu"
    assert meta["seconds"] >= 0
    assert meta["peak_rss_mb"] > 0
    assert result.meta == meta


def test_broken_adapter_is_logged_not_raised(registry, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"")
    result = adapters.run_adapter(registry["broken"], audio, tmp_path / "out", device="cpu")
    assert not result.ok
    assert "Model exploded" in result.error
    assert "Model exploded" in (tmp_path / "out" / "error.log").read_text()


def test_missing_output_counts_as_error(tmp_path):
    spec = adapters.AdapterSpec(id="leer", stage="transcribers", path=tmp_path)
    (tmp_path / "run.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "leer"\nversion = "0"\nrequires-python = ">=3.12,<3.13"\n',
        encoding="utf-8",
    )
    result = adapters.run_adapter(spec, tmp_path / "in.wav", tmp_path / "out", device="cpu")
    assert not result.ok
    assert "drums.mid" in result.error


def test_invalid_device_is_rejected(registry, tmp_path):
    with pytest.raises(ValueError, match="device"):
        adapters.run_adapter(registry["dummy"], tmp_path / "x.wav", tmp_path / "o", device="tpu")


def test_discover_skips_underscore_folders(tmp_path):
    d = tmp_path / "_common" / "helfer"
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    assert adapters.discover(tmp_path) == {}


def test_timeout_is_logged(registry, tmp_path):
    result = adapters.run_adapter(
        registry["dummy"], tmp_path / "in.wav", tmp_path / "out", device="cpu", timeout=0.001
    )
    assert not result.ok
    assert "time limit" in result.error


def test_setup_adapter_syncs_and_runs_setup_py(registry):
    marker = registry["dummy"].path / ".setup-done"
    marker.unlink(missing_ok=True)
    adapters.setup_adapter(registry["dummy"])
    assert marker.read_text() == "ok"


def test_setup_without_setup_py_only_syncs(registry):
    adapters.setup_adapter(registry["broken"])  # must not raise


def test_setup_failure_raises(tmp_path):
    (tmp_path / "pyproject.toml").write_text("kaputt = [", encoding="utf-8")
    spec = adapters.AdapterSpec(id="kaputt", stage="transcribers", path=tmp_path)
    with pytest.raises(RuntimeError, match="kaputt"):
        adapters.setup_adapter(spec)


def test_input_requirement_is_read(registry):
    assert registry["stemonly"].needs_stem
    assert not registry["dummy"].needs_stem


def test_timeout_kills_model_process_under_uv(registry, tmp_path, processes):
    import time

    out = tmp_path / "out"
    start = time.monotonic()
    result = adapters.run_adapter(registry["sleepy"], tmp_path / "a.wav", out, timeout=5)
    assert time.monotonic() - start < 20
    assert not result.ok and "time limit" in result.error
    pid = int((out / "pid").read_text())
    time.sleep(0.5)
    assert not processes.running(pid), "model process keeps running after the time limit"


def _cancel_when_running(pid_file: Path, token, seen: dict) -> None:
    """Sets `token` once the model process has written its pid; records the pid, its process
    group and the moment of cancelling in `seen`."""
    import os
    import threading
    import time

    def watch() -> None:
        while not (pid_file.exists() and pid_file.read_text()):
            time.sleep(0.01)
        seen["pid"] = int(pid_file.read_text())
        seen["group"] = os.getpgid(seen["pid"])
        seen["at"] = time.monotonic()
        token.cancel()

    threading.Thread(target=watch, daemon=True).start()


def test_cancel_ends_the_process_group_within_a_second(registry, tmp_path, processes):
    import time

    out = tmp_path / "out"
    token, seen = adapters.CancelToken(), {}
    _cancel_when_running(out / "pid", token, seen)
    with pytest.raises(adapters.Cancelled):
        adapters.run_adapter(registry["sleepy"], tmp_path / "a.wav", out, timeout=30, cancel=token)
    assert time.monotonic() - seen["at"] < 1
    assert processes.group_gone(seen["group"]), "a process of the adapter's group survived"


def test_cancelled_run_leaves_no_output_behind(registry, tmp_path):
    out = tmp_path / "out"
    token, seen = adapters.CancelToken(), {}
    _cancel_when_running(out / "pid", token, seen)
    with pytest.raises(adapters.Cancelled):
        adapters.run_adapter(registry["sleepy"], tmp_path / "a.wav", out, timeout=30, cancel=token)
    assert not out.exists()


def test_an_unset_token_changes_nothing(registry, tmp_path):
    token = adapters.CancelToken()
    result = adapters.run_adapter(
        registry["dummy"], tmp_path / "in.wav", tmp_path / "out", device="cpu", cancel=token
    )
    assert result.ok, result.error
    assert not token.is_set()


COMMON = Path(__file__).parents[1] / "adapters" / "_common"


def _local_adapter(root: Path, name: str = "t", weights: bool = True) -> adapters.AdapterSpec:
    """An adapter outside the fixtures, set up offline: its only dependency is the local
    stickler-adapter package; its setup.py "downloads" weights."""
    d = root / "transcribers" / name
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0"\nrequires-python = ">=3.12,<3.13"\n'
        'dependencies = ["stickler-adapter"]\n'
        f'[tool.uv.sources]\nstickler-adapter = {{ path = "{COMMON}", editable = true }}\n',
        encoding="utf-8",
    )
    if weights:
        (d / "setup.py").write_text(
            "from pathlib import Path\n"
            "w = Path(__file__).parent / 'weights' / 'hub'\n"
            "w.mkdir(parents=True, exist_ok=True)\n"
            "(w / 'model.ckpt').write_bytes(b'x')\n",
            encoding="utf-8",
        )
    return adapters.AdapterSpec(id=name, stage="transcribers", path=d)


def test_an_adapter_without_environment_is_not_set_up(tmp_path):
    spec = _local_adapter(tmp_path)
    assert adapters.missing_setup(spec) == ["environment", "weights"]


def test_an_empty_venv_left_by_a_killed_sync_does_not_count(tmp_path):
    spec = _local_adapter(tmp_path, weights=False)
    (spec.path / ".venv").mkdir()
    assert adapters.missing_setup(spec) == ["environment"]


def test_a_finished_setup_is_ready(tmp_path):
    spec = _local_adapter(tmp_path)
    adapters.setup_adapter(spec)
    assert adapters.missing_setup(spec) == []
    assert adapters.missing_setup(_local_adapter(tmp_path, "nw", weights=False)) == ["environment"]


def test_cancelling_the_weights_download_keeps_them_not_set_up(tmp_path, processes):
    """setup.py hangs mid-download; cancel kills its group. As measured in Task 32 the weights
    then do not count, and the next setup cleans up the partial file and finishes."""
    spec = _local_adapter(tmp_path)
    setup_py = spec.path / "setup.py"
    finishing = setup_py.read_text(encoding="utf-8")
    setup_py.write_text(
        "import os, time\nfrom pathlib import Path\n"
        "w = Path(__file__).parent / 'weights' / 'hub'\n"
        "w.mkdir(parents=True, exist_ok=True)\n"
        "(w / 'model.ckpt.1a2b.partial').write_bytes(b'half')\n"
        "(Path(__file__).parent / 'pid').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    token, seen = adapters.CancelToken(), {}
    _cancel_when_running(spec.path / "pid", token, seen)
    with pytest.raises(adapters.Cancelled):
        adapters.setup_adapter(spec, cancel=token)
    assert processes.group_gone(seen["group"])
    assert adapters.missing_setup(spec) == ["weights"]
    setup_py.write_text(finishing, encoding="utf-8")
    adapters.setup_adapter(spec)
    assert adapters.missing_setup(spec) == []
    assert not list((spec.path / "weights").rglob("*.partial"))


def test_cancelling_uv_sync_leaves_the_environment_not_set_up(tmp_path, processes, monkeypatch):
    """A stand-in for `uv` that hangs: cancel kills it; the next setup with the real uv builds
    the environment (uv resumes, Task 32)."""
    spec = _local_adapter(tmp_path, weights=False)
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text('#!/bin/sh\necho $$ > "$STUB_PID"\nexec sleep 60\n', encoding="utf-8")
    (stub / "uv").chmod(0o755)
    token, seen = adapters.CancelToken(), {}
    _cancel_when_running(tmp_path / "uv.pid", token, seen)
    with monkeypatch.context() as m:
        m.setenv("PATH", f"{stub}:{os.environ['PATH']}")
        m.setenv("STUB_PID", str(tmp_path / "uv.pid"))
        with pytest.raises(adapters.Cancelled):
            adapters.setup_adapter(spec, cancel=token)
    assert processes.group_gone(seen["group"])
    assert adapters.missing_setup(spec) == ["environment"]
    adapters.setup_adapter(spec)
    assert adapters.missing_setup(spec) == []


def test_setup_steps_can_run_one_by_one(tmp_path):
    spec = _local_adapter(tmp_path)
    assert adapters.needs_weights(spec)
    python = adapters.setup_environment(spec)
    assert adapters.missing_setup(spec) == ["weights"]
    adapters.setup_weights(spec, python)
    assert adapters.missing_setup(spec) == []
    assert not adapters.needs_weights(_local_adapter(tmp_path, "nw", weights=False))


def dead_network(monkeypatch) -> None:
    """Every HTTP request of uv goes to a closed local port."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")
    monkeypatch.setenv("UV_HTTP_RETRIES", "0")


def _python(spec: adapters.AdapterSpec, code: str) -> subprocess.CompletedProcess:
    cmd = [*adapters.cpu_python(spec), "-c", code]
    return subprocess.run(cmd, capture_output=True, text=True, env=adapters.adapter_env())


def test_a_set_up_adapter_starts_without_network(tmp_path, monkeypatch):
    """Offline, ADTOF failed to start (2026-11-17; the real case is in test_adapter_smoke).
    Without network a set-up adapter starts, and a changed pyproject.toml still reaches its
    lock (so it never runs in the old environment)."""
    spec = _local_adapter(tmp_path, weights=False)
    adapters.setup_adapter(spec)
    dead_network(monkeypatch)
    proc = _python(spec, "print('ok')")
    assert (proc.returncode, proc.stdout.strip()) == (0, "ok"), proc.stderr
    pyproject = spec.path / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(text.replace('version = "0"', 'version = "1"'), encoding="utf-8")
    assert _python(spec, "print('ok')").returncode == 0
    assert 'version = "1"' in (spec.path / "uv.lock").read_text(encoding="utf-8")


def test_weights_count_only_after_setup_py_finished(tmp_path):
    spec = _local_adapter(tmp_path)
    adapters.setup_adapter(spec)
    (spec.path / adapters.SETUP_MARKER).unlink()  # as if setup.py had been killed
    assert adapters.missing_setup(spec) == ["weights"]


def test_setup_removes_stray_partial_downloads(tmp_path):
    spec = _local_adapter(tmp_path)
    partial = spec.path / "weights" / "hub" / "checkpoints" / "model.ckpt.1a2b.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"half")
    assert "weights" in adapters.missing_setup(spec)
    adapters.setup_adapter(spec)
    assert not partial.exists()
    assert adapters.missing_setup(spec) == []


def test_a_failed_setup_py_leaves_the_weights_not_set_up(tmp_path):
    spec = _local_adapter(tmp_path)
    adapters.setup_adapter(spec)
    (spec.path / "setup.py").write_text("raise SystemExit('server down')", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Setup of t"):
        adapters.setup_adapter(spec)
    assert adapters.missing_setup(spec) == ["weights"]


def test_harness_uv_settings_do_not_reach_the_adapters(registry, tmp_path, monkeypatch):
    """The harness may run on another Python or in another environment (CI matrix, the GTK
    app); the adapters keep their own pinned Python and environment."""
    elsewhere = tmp_path / "harness-venv"
    monkeypatch.setenv("UV_PYTHON", "3.14")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(elsewhere))
    monkeypatch.setenv("VIRTUAL_ENV", str(elsewhere))
    adapters.setup_adapter(registry["dummy"])
    result = adapters.run_adapter(registry["dummy"], tmp_path / "in.wav", tmp_path / "out")
    assert result.ok, result.error
    assert not elsewhere.exists(), "an adapter environment was built in the harness's place"


def test_gpu_environments_use_the_adapters_own_python(tmp_path):
    """ROCm and CUDA environments were built with 3.12 although ADTOF, Beat This! and Demucs
    moved to 3.14 (code review before release 5)."""
    from stickler import adapters as adapters_mod

    pinned = tmp_path / "pinned"
    pinned.mkdir()
    (pinned / ".python-version").write_text("3.14\n")
    assert adapters_mod.adapter_python(pinned) == "3.14"
    assert adapters_mod.adapter_python(tmp_path / "unpinned") == "3.12"
    real = Path(__file__).parents[1] / "adapters"
    assert adapters_mod.adapter_python(real / "separators" / "demucs") == "3.14"
    assert adapters_mod.adapter_python(real / "transcribers" / "muscriptor_m") == "3.12"
