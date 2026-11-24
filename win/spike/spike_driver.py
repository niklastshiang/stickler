"""The spike's driver (SPEC.md, module `win-spike`, task 170): drives `stickler-bridge` the way
the Windows app will, from the installed folder. It agrees to the download when the bridge asks,
sets the Fast models up, opens the song, waits for the result and saves its MusicXML. Everything
goes to a log file with a time stamp. Nothing is sent anywhere by this script.

    python spike_driver.py --song <song> --out <folder> --log <log file> [--limit SECONDS]

Exit status 0 only when the MusicXML file exists and is not empty."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

GRACE = 20.0  # seconds to wait for the bridge to say "consent" before taking the models as ready


class Failure(Exception):
    """The first error, in words."""


class Log:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()

    def __call__(self, kind: str, text: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        line = f"{stamp} [{kind}] {text}"
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()
            print(line, flush=True)


class Bridge:
    def __init__(self, log: Log, deadline: float) -> None:
        self.log = log
        self.deadline = deadline
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "stickler_app.bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        log("bridge", f"started, pid {self.proc.pid}: {sys.executable} -m stickler_app.bridge")
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._id = 0

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put("")

    def _read_stderr(self) -> None:
        for line in self.proc.stderr:
            self.log("bridge-stderr", line.rstrip())

    def next(self, wait: float | None = None) -> dict | None:
        """The next line as an object; None when `wait` seconds pass without one."""
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Failure("the time limit was reached")
        try:
            line = self.lines.get(timeout=left if wait is None else min(wait, left))
        except queue.Empty:
            if wait is None:
                raise Failure("the time limit was reached") from None
            return None
        if not line:
            raise Failure(f"the bridge ended (exit code {self.proc.poll()}); see its stderr above")
        return json.loads(line)

    def send(self, cmd: str, **args) -> int:
        self._id += 1
        self.log("send", json.dumps({"id": self._id, "cmd": cmd, **args}))
        self.proc.stdin.write(json.dumps({"id": self._id, "cmd": cmd, **args}) + "\n")
        self.proc.stdin.flush()
        return self._id

    def reply(self, ident: int) -> dict:
        while True:
            line = self.next()
            if line.get("id") == ident:
                if not line["ok"]:
                    error = line["error"]
                    raise Failure(f"{error['code']}: {error['message']}")
                self.log("reply", f"id {ident} ok")
                return line
            self.note(line)

    def note(self, line: dict) -> dict | None:
        """Logs an event's essentials; returns the state when it is one."""
        event = line.get("event")
        if event == "state":
            state = line["state"]
            self.log("state", describe(state))
            return state
        if event == "notice":
            self.log("notice", line.get("text", ""))
        elif event == "hello":
            self.log("hello", f"protocol {line['protocol']}, release {line['version']}")
        elif event == "recent":
            self.log("recent", f"{len(line.get('rows', []))} rows")
        return None


def describe(state: dict) -> str:
    kind = state["kind"]
    steps = " | ".join(
        f"{s['id']}={s['state']}" + (f" ({s['detail']})" if s["state"] == "running" else "")
        for s in state.get("steps", [])
    )
    extra = ""
    if kind == "failed":
        extra = f" {state['title']}: {state['description']} -- {state['details']}"
    elif kind == "setup_failed":
        extra = f" step {state['step']}, server {state['server']}: {state['details']}"
    elif kind == "result":
        extra = f" {state['title']} / {state['subtitle']}, musicxml {state['musicxml']}"
    elif kind == "consent":
        extra = " models " + ", ".join(m["id"] for m in state["models"])
    return f"{kind}{extra} {steps}".rstrip()


class Tracker:
    """Logs a state only when its kind or one of its steps changed (the download's byte count
    changes twice a second)."""

    def __init__(self, log: Log) -> None:
        self.log = log
        self.last: object = None

    def __call__(self, state: dict) -> None:
        key = (state["kind"], tuple((s["id"], s["state"]) for s in state.get("steps", [])))
        if key != self.last:
            self.last = key
            self.log("state", describe(state))


def fail_if_failed(state: dict) -> None:
    if state["kind"] == "setup_failed":
        raise Failure(
            f"setup of the models failed at {state['step']} ({state['server']}): {state['details']}"
        )
    if state["kind"] == "failed":
        raise Failure(f"{state['title']}: {state['description']} -- {state['details']}")


def wait_state(bridge: Bridge, track: Tracker, kinds: set[str], wait: float | None = None):
    """The first state whose kind is in `kinds` (None when `wait` runs out first)."""
    end = None if wait is None else time.monotonic() + wait
    while True:
        left = None if end is None else max(0.0, end - time.monotonic())
        line = bridge.next(left)
        if line is None:
            return None
        if line.get("event") != "state":
            bridge.note(line)
            continue
        state = line["state"]
        track(state)
        fail_if_failed(state)
        if state["kind"] in kinds:
            return state
        if end is not None and time.monotonic() >= end:
            return None


def set_up(bridge: Bridge, track: Tracker) -> None:
    """`start` makes the bridge copy the shipped sources and look at the models: consent when
    one is missing. Agrees, then waits until the download is over."""
    bridge.reply(bridge.send("start"))
    state = wait_state(bridge, track, {"consent", "setting_up"}, GRACE)
    if state is None:
        bridge.log("setup", "no consent asked within the grace time: the models are set up")
        return
    started = time.monotonic()
    if state["kind"] == "consent":
        bridge.reply(bridge.send("agree"))
    wait_state(bridge, track, {"empty"})
    bridge.log("setup", f"setup seconds: {time.monotonic() - started:.1f}")


def analyse(bridge: Bridge, track: Tracker, song: Path) -> dict:
    started = time.monotonic()
    bridge.reply(bridge.send("open", path=str(song)))
    while True:
        state = wait_state(bridge, track, {"result", "consent"})
        if state["kind"] == "result":
            bridge.log("analysis", f"analysis seconds: {time.monotonic() - started:.1f}")
            return state
        bridge.log("analysis", "the bridge asked for consent again; agreeing")
        bridge.reply(bridge.send("agree"))


def log_environment(log: Log) -> None:
    log("env", f"sys.executable = {sys.executable}")
    log("env", f"sys.prefix = {sys.prefix}")
    log("env", f"python {sys.version.split()[0]}, platform {sys.platform}")
    for name in ("STICKLER_PACKAGED", "STICKLER_ADAPTER_SOURCES", "LOCALAPPDATA", "PYTHONUTF8"):
        log("env", f"{name} = {os.environ.get(name)!r}")
    entries = os.environ.get("PATH", "").split(os.pathsep)
    for i, entry in enumerate(entries[:5]):
        log("env", f"PATH[{i}] = {entry}")
    try:
        import stickler
        import stickler_app
        from stickler_app import paths

        merged = {**os.environ, **paths.packaged_env()}
        log("paths", f"stickler {stickler.__version__} from {Path(stickler.__file__).parent}")
        log("paths", f"stickler_app.prefix() = {stickler_app.prefix()}")
        log("paths", f"packaged = {paths.packaged()!r}")
        log("paths", f"data_home = {paths.data_home()}")
        log("paths", f"cache_home = {paths.cache_home()}")
        log("paths", f"config_home = {paths.config_home()}")
        log("paths", f"adapters_root = {paths.adapters_root()}")
        log("paths", f"adapter_sources (as the launcher left it) = {paths.adapter_sources()}")
        log("paths", f"adapter_sources (with packaged_env) = {paths.adapter_sources(merged)}")
        log("paths", f"packaged_env = {json.dumps(paths.packaged_env())}")
    except Exception as exc:  # the log must say why, not die
        log("paths", f"could not read the paths: {type(exc).__name__}: {exc}")


def run(args: argparse.Namespace, log: Log) -> Path:
    song, out = args.song.resolve(), args.out.resolve()
    log("start", f"song {song} ({song.stat().st_size if song.exists() else 'missing'} bytes)")
    if not song.is_file():
        raise Failure(f"the song does not exist: {song}")
    out.mkdir(parents=True, exist_ok=True)
    log_environment(log)
    bridge = Bridge(log, time.monotonic() + args.limit)
    track = Tracker(log)
    try:
        bridge.note(bridge.next())  # hello
        set_up(bridge, track)
        result = analyse(bridge, track, song)
        dest = out / f"{song.stem}.musicxml"
        bridge.reply(bridge.send("export_musicxml", dest=str(dest)))
        bridge.send("quit")
        try:
            code = bridge.proc.wait(15)
            log("bridge", f"ended with exit code {code}")
        except subprocess.TimeoutExpired:
            log("bridge", "did not end within 15 s; it is stopped")
            bridge.proc.kill()
        if not dest.is_file() or dest.stat().st_size == 0:
            raise Failure(f"the bridge saved no MusicXML at {dest} (result: {result['title']})")
        return dest
    finally:
        if bridge.proc.poll() is None:
            bridge.proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--song", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--limit", type=float, default=45 * 60, help="overall seconds")
    args = parser.parse_args()
    log = Log(args.log)
    begun = time.monotonic()
    log("start", "=" * 20 + " Stickler spike driver " + "=" * 20)
    try:
        dest = run(args, log)
    except Failure as exc:
        log("error", f"FAILED: {exc}")
        return 1
    except Exception as exc:
        log("error", f"FAILED: unexpected {type(exc).__name__}: {exc}")
        return 1
    log("done", f"total seconds: {time.monotonic() - begun:.1f}")
    log("done", f"MusicXML written: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
