"""The bridge as a real process (SPEC.md, module `core-bridge`, Testing): `python -m
stickler_app.bridge` with stand-in models called `adtof` and `beat_this`, which run through the
real chain (their own uv environment and process group, the results cache), so closing stdin
during an analysis must end the model too and leave no half-written cache entry."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from stickler import adapters, runner

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "bridge_stand_ins", ROOT / "scripts" / "bridge_stand_ins.py"
)
assert _spec and _spec.loader
stand_ins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stand_ins)


@pytest.fixture(scope="module")
def models(tmp_path_factory) -> Path:
    """The stand-ins, set up once (uv sync, offline: their only dependency is local)."""
    return stand_ins.set_up(tmp_path_factory.mktemp("models"))


@pytest.fixture
def song(tmp_path) -> Path:
    """Eight seconds of quiet: enough for ffprobe and the stand-ins."""
    return stand_ins.quiet_song(tmp_path / "Groove.wav")


class Process:
    def __init__(self, models: Path, tmp_path: Path, **env: str):
        self.cache = tmp_path / "results"
        environment = {
            **os.environ,
            "STICKLER_ADAPTERS": str(models),
            "STICKLER_RESULTS_CACHE": str(self.cache),
            **env,
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "stickler_app.bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        self.lines: list[dict] = []
        self._id = 0

    def read(self) -> dict:
        line = self.proc.stdout.readline()
        assert line, f"the bridge ended: {self.proc.stderr.read()}"
        self.lines.append(json.loads(line))
        return self.lines[-1]

    def send(self, cmd: str, **args) -> int:
        self._id += 1
        self.proc.stdin.write(json.dumps({"id": self._id, "cmd": cmd, **args}) + "\n")
        self.proc.stdin.flush()
        return self._id

    def until(self, test, seconds=60.0) -> dict:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            line = self.read()
            if test(line):
                return line
        raise AssertionError(f"not seen in {seconds} s; last lines: {self.lines[-3:]}")

    def reply(self, ident: int) -> dict:
        return self.until(lambda line: line.get("id") == ident)

    def state(self, kind: str) -> dict:
        found = self.until(
            lambda line: line.get("event") == "state" and line["state"]["kind"] == kind
        )
        return found["state"]


def test_a_song_becomes_a_result_and_its_pages_through_the_process(models, song, tmp_path):
    bridge = Process(models, tmp_path)
    try:
        hello = bridge.read()
        assert hello["event"] == "hello" and hello["protocol"] == 1
        assert bridge.state("empty")["can_open"]
        bridge.send("open", path=str(song))
        result = bridge.state("result")
        assert result["title"] == "Groove" and result["meter"] == [4, 4]
        assert result["tempo"] == 120
        ident = bridge.send("pages", width=800)
        pages = bridge.reply(ident)
        assert pages["ok"] and pages["pages"][0]["svg"].startswith("<svg")
        assert [b["bar"] for b in pages["pages"][0]["bars"]][:1] == [1]
        ident = bridge.send("quit")
        assert bridge.reply(ident) == {"id": ident, "ok": True}
        assert bridge.proc.wait(10) == 0
        assert all("event" in line or "id" in line for line in bridge.lines)
    finally:
        bridge.proc.kill()
        bridge.proc.wait()


def test_closing_stdin_during_an_analysis_ends_the_model_and_leaves_no_cache_entry(
    models, song, tmp_path
):
    pid_file = tmp_path / "model.pid"
    bridge = Process(models, tmp_path, STICKLER_TEST_HOLD=str(pid_file))
    try:
        bridge.read()  # hello
        bridge.send("open", path=str(song))
        bridge.state("analysing")
        end = time.monotonic() + 60
        while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < end:
            time.sleep(0.05)
        model = int(pid_file.read_text())
        start = time.monotonic()
        bridge.proc.stdin.close()
        assert bridge.proc.wait(3) == 0
        while _alive(model) and time.monotonic() - start < 3:
            time.sleep(0.05)
        assert not _alive(model), "the model outlived the bridge"
        assert time.monotonic() - start < 3
        spec = adapters.discover(models)["adtof"]
        assert not runner.cache_dir_for(bridge.cache, spec, song).exists()
    finally:
        bridge.proc.kill()
        bridge.proc.wait()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


STRAY = """import os
import sys

import stickler_app.bridge as bridge

started = bridge.Bridge.run


def run(self):
    print("stray print")  # a library's print
    os.write(1, b"stray fd\\n")  # a model process writing to the inherited stdout
    return started(self)


bridge.Bridge.run = run
sys.exit(bridge.main())
"""


def test_stray_output_cannot_break_a_line(tmp_path):
    """Whatever writes to file descriptor 1 lands on stderr; stdout carries only the protocol."""
    script = tmp_path / "stray.py"
    script.write_text(STRAY, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)],
        input='{"id": 1, "cmd": "quit"}\n',
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines()]
    assert lines[0]["event"] == "hello" and lines[-1] == {"id": 1, "ok": True}
    assert "stray print" in proc.stderr and "stray fd" in proc.stderr


def test_every_line_ends_in_a_bare_newline_and_a_crlf_request_is_answered(tmp_path):
    """Passes on Linux before and after the fix too; the Windows CI job is what proves it."""
    proc = subprocess.run(
        [sys.executable, "-m", "stickler_app.bridge"],
        input=b'{"id": 1, "cmd": "quit"}\r\n',
        capture_output=True,
        timeout=30,
        env={**os.environ, "STICKLER_RESULTS_CACHE": str(tmp_path / "results")},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.endswith(b"\n") and b"\r" not in proc.stdout
    lines = proc.stdout.split(b"\n")[:-1]
    assert json.loads(lines[0])["event"] == "hello"
    assert json.loads(lines[-1]) == {"id": 1, "ok": True}


def test_the_demo_finds_the_same_musicxml_as_the_gtk_app(models, song, tmp_path):
    """scripts/bridge_demo.py with the stand-ins; on the laptop it runs the real Fast models."""
    demo = Path(__file__).resolve().parents[2] / "scripts" / "bridge_demo.py"
    out = tmp_path / "out.musicxml"
    environment = {
        **os.environ,
        "STICKLER_ADAPTERS": str(models),
        "STICKLER_RESULTS_CACHE": str(tmp_path / "results"),
    }
    proc = subprocess.run(
        [sys.executable, str(demo), str(song), "--out", str(out), "--width", "600"],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "result after" in proc.stdout and "pages at 600 px: 1 page(s)" in proc.stdout
    assert "the GTK app's MusicXML: identical" in proc.stdout
    assert out.is_file()
