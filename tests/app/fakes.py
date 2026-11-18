"""stickler.api without models, for the controller's and the bridge's tests."""

import threading
import time
from pathlib import Path

from stickler import api


def wait(predicate, seconds=5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def groove_score():
    """Eight bars of a plain groove, engraved like the app's own results."""
    from stickler import notation

    beats = [k * 0.5 for k in range(33)]
    notes = [(b * 2.0 + k * 0.5, 36 + (b % 2) * 2, 100) for b in range(8) for k in range(4)]
    return notation.engrave(notes, beats, beats[:-1:4], repeats=False)


class FakeApi:
    """stickler.api without models: three steps, then a result in 4/4 at 109 (54 for half
    tempo). With `hold`, each run waits until it is released or cancelled."""

    def __init__(self, monkeypatch, hold=False):
        self.runs: list[tuple[Path, api.Corrections]] = []
        self.cancelled: list[Path] = []
        self.hold = hold
        self.release = threading.Event()
        self.error: BaseException | None = None
        monkeypatch.setattr(api, "song_info", self.song_info)
        monkeypatch.setattr(api, "notate", self.notate)

    @staticmethod
    def song_info(song):
        if song.suffix == ".txt":
            raise RuntimeError("ffprobe: invalid data")
        return api.SongInfo("Eye of the Tiger", "Survivor", 246.0)

    def notate(self, song, out, *, progress, cancel, corrections=None, **kw):
        fix = corrections or api.Corrections()
        self.runs.append((song, fix))
        for i, step_id in enumerate(("transcribe", "beats", "engrave"), 1):
            progress(api.Step(step_id, i, 3, "started", False, None))
            if i == 1 and self.hold:
                while not (self.release.is_set() or cancel.is_set()):
                    time.sleep(0.005)
            if cancel.is_set():
                self.cancelled.append(song)
                raise api.Cancelled("cancelled")
            if self.error is not None:
                raise self.error
            progress(api.Step(step_id, i, 3, "done", False, None))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        engraved = groove_score()
        Path(out).write_text(engraved.musicxml, encoding="utf-8")
        t = api.SongTranscription(song, "fast", None, [], [], [])
        tempo = {"half": 54, "normal": 109, "double": 218}[fix.tempo]
        return api.Notation(Path(out), None, None, t, engraved.bars, tempo, (4, 4))


class FakeSetup:
    """api without downloads: `missing` are not set up until setup_adapters ran for them.
    With `hold`, each step waits until released or cancelled; `fail` raises in the step with
    that id once."""

    def __init__(self, monkeypatch, missing=("adtof", "beat_this"), hold=False, fail=None):
        self.missing, self.hold, self.fail = list(missing), hold, fail
        self.done: list[str] = []
        self.attempts: list[str] = []
        self.release = threading.Event()
        self.cancelled = False
        self.adapter_of_step: str | None = None  # what the steps name as their model
        monkeypatch.setattr(api, "mode_ready", self.mode_ready)
        monkeypatch.setattr(api, "setup_adapters", self.setup_adapters)

    def mode_ready(self, *a, drums=False, **kw):
        return [m for m in self.missing if m not in self.done]

    def setup_adapters(self, adapter, device="cpu", adapters_root=None, *, progress, cancel):
        self.attempts.append(adapter)
        ids = [f"environment:{adapter}"] + (["weights:beat_this"] if adapter == "beat_this" else [])
        for i, step_id in enumerate(ids, 1):
            progress(api.Step(step_id, i, len(ids), "started", False, self.adapter_of_step))
            if self.hold:
                while not (self.release.is_set() or cancel.is_set()):
                    time.sleep(0.005)
            if cancel.is_set():
                self.cancelled = True
                raise api.Cancelled("cancelled")
            if step_id == self.fail:
                self.fail = None
                raise RuntimeError("Beat This! model not downloaded. JKU Linz: 500")
            progress(api.Step(step_id, i, len(ids), "done", False, self.adapter_of_step))
        self.done.append(adapter)
        return [adapter]
