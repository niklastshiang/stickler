"""Drives `stickler-bridge` the way the Mac app will (SPEC.md, module `core-bridge`, success
criterion 2): opens a song, shows its steps, asks for the pages and saves the MusicXML. Then it
writes the same song's MusicXML the way the GTK app does (`stickler_app.analysis.analyse`, in
this process; the models' results come from the cache) and compares the two.

    uv run python scripts/bridge_demo.py <song> [--out song.musicxml] [--width 1000]

The Fast models must be set up (`uv run stickler setup --adapter adtof`, then `--adapter
beat_this`). Exit status: 0 when the two MusicXML files are identical, 1 otherwise."""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

WAIT = 30 * 60  # seconds: the first analysis on a slow CPU, models included


class Bridge:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "stickler_app.bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._id = 0

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put("")

    def next(self) -> tuple[dict, int]:
        """The next line and its size in bytes."""
        line = self.lines.get(timeout=WAIT)
        if not line:
            raise SystemExit("the bridge ended (see its log above)")
        return json.loads(line), len(line.encode("utf-8"))

    def send(self, cmd: str, **args) -> int:
        self._id += 1
        self.proc.stdin.write(json.dumps({"id": self._id, "cmd": cmd, **args}) + "\n")
        self.proc.stdin.flush()
        return self._id

    def reply(self, ident: int) -> tuple[dict, int]:
        while True:
            line, size = self.next()
            if line.get("id") == ident:
                if not line["ok"]:
                    raise SystemExit(f"{line['error']['code']}: {line['error']['message']}")
                return line, size


def analyse(bridge: Bridge, song: Path) -> dict:
    """Opens the song and prints each step as it changes, until the result."""
    bridge.send("open", path=str(song))
    shown = None
    while True:
        line, _size = bridge.next()
        if line.get("event") != "state":
            continue
        state = line["state"]
        if state["kind"] == "analysing":
            now = [(r["label"], r["state"]) for r in state["steps"]]
            if now != shown:
                shown = now
                print("  " + " · ".join(f"{label}: {s}" for label, s in now))
        elif state["kind"] == "result":
            return state
        elif state["kind"] == "consent":
            raise SystemExit(
                "the models are not set up: uv run stickler setup --adapter adtof, then "
                "--adapter beat_this"
            )
        elif state["kind"] == "failed":
            raise SystemExit(f"{state['title']}: {state['description']}\n{state['details']}")


def gtk_musicxml(song: Path, out: Path) -> None:
    """What the GTK app writes for the song: the same call with its stored corrections."""
    from stickler import api
    from stickler_app import analysis, corrections

    stored = corrections.load(corrections.store_path()).get(song.absolute())
    analysis.analyse(song, out, lambda _step: None, api.CancelToken(), corrections=stored)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("song", type=Path)
    parser.add_argument("--out", type=Path, help="where the MusicXML goes (default: next here)")
    parser.add_argument("--width", type=int, default=1000, help="the pages' width in pixels")
    args = parser.parse_args()
    song = args.song.resolve()
    out = (args.out or Path(f"{song.stem}.musicxml")).resolve()

    bridge = Bridge()
    hello, _size = bridge.next()
    print(f"bridge: protocol {hello['protocol']}, release {hello['version']}, {hello['language']}")
    start = time.monotonic()
    print(f"open {song.name}")
    result = analyse(bridge, song)
    print(f"result after {time.monotonic() - start:.1f} s: {result['title']}, {result['subtitle']}")

    start = time.monotonic()
    pages, size = bridge.reply(bridge.send("pages", width=args.width))
    bars = sum(len(p["bars"]) for p in pages["pages"])
    print(
        f"pages at {args.width} px: {len(pages['pages'])} page(s), {bars} bars, "
        f"the line {size / 1e6:.2f} MB, {time.monotonic() - start:.1f} s"
    )
    bridge.reply(bridge.send("export_musicxml", dest=str(out)))
    print(f"saved {out}")
    bridge.reply(bridge.send("quit"))
    bridge.proc.wait(10)

    with tempfile.TemporaryDirectory() as folder:
        theirs = Path(folder) / "gtk.musicxml"
        gtk_musicxml(song, theirs)
        same = theirs.read_bytes() == out.read_bytes()
    print("the GTK app's MusicXML: " + ("identical" if same else "DIFFERENT"))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
