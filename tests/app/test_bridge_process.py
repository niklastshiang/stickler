"""The bridge as a real process (SPEC.md, module `core-bridge`, Testing): `python -m
stickler_app.bridge` with stand-in models called `adtof` and `beat_this`, which run through the
real chain (their own uv environment and process group, the results cache), so closing stdin
during an analysis must end the model too and leave no half-written cache entry."""

import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import pytest

from stickler import adapters, runner

COMMON = Path(__file__).resolve().parents[2] / "adapters" / "_common"

PYPROJECT = """[project]
name = "stand-in-{name}"
version = "0"
requires-python = ">=3.12,<3.13"
dependencies = ["stickler-adapter"]

[tool.uv.sources]
stickler-adapter = {{ path = "{common}", editable = true }}
"""

TRANSCRIBER = '''"""Stand-in for ADTOF: a groove; with STICKLER_TEST_HOLD it writes its pid
there and waits like a long model."""

import os
import time
from pathlib import Path

from stickler_adapter import run, write_drum_midi


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    hold = os.environ.get("STICKLER_TEST_HOLD")
    if hold:
        Path(hold).write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(60)
    notes = [(k * 0.5, 36 if k % 2 == 0 else 38, 100) for k in range(16)]
    write_drum_midi(out_dir / "drums.mid", notes)


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="adtof", version="stand-in")
'''

BEATS = '''"""Stand-in for Beat This!: a beat every half second, a bar every two seconds."""

import json
from pathlib import Path

from stickler_adapter import run


def track_beats(audio: Path, out_dir: Path, device: str) -> None:
    beats = [k * 0.5 for k in range(17)]
    data = {"beats": beats, "downbeats": beats[::4]}
    (out_dir / "beats.json").write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    run(track_beats, stage="beats", adapter="beat_this", version="stand-in")
'''


@pytest.fixture(scope="module")
def models(tmp_path_factory) -> Path:
    """The stand-ins, set up once (uv sync, offline: their only dependency is local)."""
    root = tmp_path_factory.mktemp("models")
    for stage, name, code in (
        ("transcribers", "adtof", TRANSCRIBER),
        ("beats", "beat_this", BEATS),
    ):
        folder = root / stage / name
        folder.mkdir(parents=True)
        (folder / "run.py").write_text(code, encoding="utf-8")
        (folder / "pyproject.toml").write_text(
            PYPROJECT.format(name=name, common=COMMON.as_posix()), encoding="utf-8"
        )
    for spec in adapters.discover(root).values():
        adapters.setup_adapter(spec)
    return root


@pytest.fixture
def song(tmp_path) -> Path:
    """Eight seconds of quiet: enough for ffprobe and the stand-ins."""
    path = tmp_path / "Groove.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\0\0" * 8000 * 8)
    return path


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
