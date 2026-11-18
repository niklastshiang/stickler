"""The bridge in process: its loop reads and writes in-memory streams; stickler.api is faked
(SPEC.md, module `core-bridge`, Testing)."""

import gettext
import json
import queue
import threading
import time
from pathlib import Path

import pytest
from fakes import FakeApi, FakeSetup, groove_score, wait

from stickler import api
from stickler_app import bridge, i18n, recent, session, steps


class Stdin:
    """Lines sent by the test, as a pipe gives them; `close()` is the app going away."""

    def __init__(self):
        self._lines: queue.Queue[str | None] = queue.Queue()

    def send(self, line: str) -> None:
        self._lines.put(line + "\n")

    def close(self) -> None:
        self._lines.put(None)

    def __iter__(self):
        while (line := self._lines.get()) is not None:
            yield line


class Stdout:
    """Collects the lines; each must be one whole JSON object."""

    def __init__(self):
        self.text = ""
        self.lock = threading.Lock()

    def write(self, text: str) -> int:
        with self.lock:
            self.text += text
        return len(text)

    def flush(self) -> None:
        pass

    def lines(self) -> list[dict]:
        with self.lock:
            return [json.loads(line) for line in self.text.splitlines()]


class Running:
    """A bridge in a thread, with helpers to send commands and wait for lines."""

    def __init__(self):
        self.stdin, self.stdout = Stdin(), Stdout()
        self.bridge = bridge.Bridge(self.stdin, self.stdout)
        self.status: list[int] = []
        self.thread = threading.Thread(target=lambda: self.status.append(self.bridge.run()))
        self.thread.start()
        self._next = 0

    def send(self, cmd: str, **args) -> dict:
        """Sends a command and returns its reply."""
        self._next += 1
        ident = self._next
        self.stdin.send(json.dumps({"id": ident, "cmd": cmd, **args}))
        assert wait(lambda: self.reply(ident) is not None), f"no reply to {cmd}"
        return self.reply(ident)

    def reply(self, ident) -> dict | None:
        found = [line for line in self.stdout.lines() if "id" in line and line["id"] == ident]
        assert len(found) <= 1, "one reply per command"
        return found[0] if found else None

    def events(self, kind=None) -> list[dict]:
        events = [line for line in self.stdout.lines() if "event" in line]
        return [e for e in events if kind is None or e["event"] == kind]

    def states(self) -> list[dict]:
        return [e["state"] for e in self.events("state")]

    def state(self) -> dict:
        return self.states()[-1]

    def until(self, kind: str, seconds=5.0) -> dict:
        assert wait(lambda: self.states() and self.state()["kind"] == kind, seconds), (
            f"no {kind} state, last: {self.states()[-1:]}"
        )
        return self.state()

    def stop(self) -> None:
        self.stdin.close()
        self.thread.join(5)
        assert not self.thread.is_alive()


@pytest.fixture
def running():
    made = Running()
    yield made
    made.stop()


def test_the_bridge_says_hello_then_sends_the_state_and_the_recent_songs(running):
    assert wait(lambda: len(running.stdout.lines()) >= 3)
    hello, state, songs = running.stdout.lines()[:3]
    assert hello == {"event": "hello", "protocol": 1, "version": "7", "language": "en"}
    assert state["event"] == "state" and state["seq"] == 1
    assert state["state"] == {
        "kind": "empty",
        "can_open": True,
        "can_cancel": False,
        "can_retry": False,
        "can_close": False,
        "can_export": False,
        "can_agree": False,
        "can_not_now": False,
        "can_retry_setup": False,
        "can_remove_models": False,
    }
    assert songs == {"event": "recent", "seq": 2, "rows": []}


def test_quit_is_answered_and_ends_the_bridge_with_status_0(running):
    assert running.send("quit") == {"id": 1, "ok": True}
    running.thread.join(5)
    assert running.status == [0]


def test_the_end_of_stdin_ends_the_bridge(running):
    running.stdin.close()
    running.thread.join(5)
    assert running.status == [0]


@pytest.mark.parametrize(
    "line",
    ["not json", "[1, 2]", '{"cmd": "start"}', '{"id": true, "cmd": "start"}', '{"id": "1"}'],
)
def test_a_line_that_is_no_command_gets_bad_request_and_the_bridge_goes_on(running, line):
    running.stdin.send(line)
    assert wait(lambda: any(not x.get("ok", True) for x in running.stdout.lines()))
    (error,) = [x for x in running.stdout.lines() if "ok" in x]
    assert error == {
        "id": None,
        "ok": False,
        "error": {"code": "bad_request", "message": "The request could not be read."},
    }
    assert running.send("close")["ok"]


def test_blank_lines_are_skipped(running):
    running.stdin.send("   ")
    assert running.send("close") == {"id": 1, "ok": True}
    assert not [x for x in running.stdout.lines() if "ok" in x and x["id"] is None]


def test_a_command_without_its_id_still_gets_an_answer_with_it(running):
    running.stdin.send('{"id": 7, "cmd": 3}')
    assert wait(lambda: running.reply(7) is not None)
    assert running.reply(7)["error"]["code"] == "bad_request"


def test_an_unknown_command_and_a_wrong_argument_are_named(running):
    reply = running.send("dance")
    assert reply == {
        "id": 1,
        "ok": False,
        "error": {
            "code": "unknown_command",
            "message": "Stickler does not know the command “dance”.",
        },
    }
    for args in ({}, {"path": ""}, {"path": 3}):
        reply = running.send("open", **args)
        assert reply["error"] == {
            "code": "bad_argument",
            "message": "The value of “path” is not valid.",
        }


@pytest.mark.parametrize("cmd", ["agree", "not_now", "retry_setup", "cancel", "retry"])
def test_a_command_that_does_not_fit_the_state_gets_not_now(running, cmd):
    assert running.send(cmd)["error"] == {
        "code": "not_now",
        "message": "This is not possible right now.",
    }
    assert running.state()["kind"] == "empty"


def test_a_song_becomes_a_result_with_events_in_order(monkeypatch, tmp_path):
    FakeApi(monkeypatch)
    running = Running()
    try:
        song = tmp_path / "Eye.flac"
        assert running.send("open", path=str(song)) == {"id": 1, "ok": True}
        result = running.until("result")
        assert result["title"] == "Eye of the Tiger"
        assert result["subtitle"] == "Survivor · ♩ = 109 · 4/4"
        assert result["tempo"] == 109 and result["meter"] == [4, 4]
        assert result["seconds"] == 246.0 and result["artist"] == "Survivor"
        assert Path(result["musicxml"]).is_file()
        assert result["corrections"] == {
            "tempo": "normal",
            "beats_per_bar": None,
            "first_downbeat": None,
            "simplify": True,
            "repeats": True,
        }
        assert not result["correcting"]
        assert result["can_export"] and result["can_close"] and not result["can_cancel"]
        analysing = [s for s in running.states() if s["kind"] == "analysing"]
        assert analysing[0]["name"] == "Eye" and analysing[0]["can_cancel"]
        assert [r["id"] for r in analysing[0]["steps"]] == ["transcribe", "beats", "engrave"]
        assert analysing[0]["steps"][0] == {
            "id": "transcribe",
            "label": "Detect the hits",
            "detail": "Kick, snare, toms, hi-hat, cymbals",
            "state": "waiting",
        }
        assert wait(lambda: len(running.events("recent")) == 2)
        assert running.events("recent")[-1]["rows"][0]["title"] == "Eye of the Tiger"
        seqs = [e["seq"] for e in running.events() if e["event"] != "hello"]
        assert seqs == list(range(1, len(seqs) + 1))
        assert running.send("close")["ok"]
        assert running.state()["kind"] == "empty"
    finally:
        running.stop()


def test_cancel_goes_back_at_once_and_stops_the_job(monkeypatch, tmp_path):
    fake = FakeApi(monkeypatch, hold=True)
    running = Running()
    try:
        running.send("open", path=str(tmp_path / "eye.flac"))
        assert wait(lambda: fake.runs)
        assert running.send("cancel") == {"id": 2, "ok": True}
        assert running.state()["kind"] == "empty"
        assert wait(lambda: fake.cancelled, seconds=1)
    finally:
        running.stop()


def test_stdin_closing_during_an_analysis_cancels_it_and_ends_the_bridge(monkeypatch, tmp_path):
    fake = FakeApi(monkeypatch, hold=True)
    running = Running()
    running.send("open", path=str(tmp_path / "eye.flac"))
    assert wait(lambda: fake.runs)
    start = time.monotonic()
    running.stop()
    assert fake.cancelled and running.status == [0]
    assert time.monotonic() - start < bridge.QUIT_WAIT


def test_a_failed_analysis_can_be_tried_again(monkeypatch, tmp_path):
    fake = FakeApi(monkeypatch)
    fake.error = RuntimeError("adtof (exit 1): out of memory")
    running = Running()
    try:
        running.send("open", path=str(tmp_path / "eye.flac"))
        failed = running.until("failed")
        assert failed["reason"] == "analysis" and failed["title"] == "The Analysis Failed"
        assert failed["details"] == "adtof (exit 1): out of memory"
        assert failed["can_retry"] and failed["name"] == "eye"
        fake.error = None
        assert running.send("retry")["ok"]
        running.until("result")
    finally:
        running.stop()


def test_the_first_start_asks_then_downloads(monkeypatch):
    fake = FakeSetup(monkeypatch, hold=True)
    running = Running()
    try:
        assert running.send("start")["ok"]
        consent = running.until("consent")
        assert consent["song"] is None and consent["can_agree"] and consent["can_not_now"]
        assert consent["total_size"] == "2.2 GB"
        assert consent["models"][0] == {
            "id": "adtof",
            "name": "ADTOF",
            "does": "detects the hits",
            "licence": "Its trained model is free for non-commercial use only (CC BY-NC-SA 4.0).",
            "size": "1.3 GB",
        }
        assert running.send("agree")["ok"]
        setting_up = running.until("setting_up")
        assert setting_up["can_cancel"] and setting_up["song"] is None
        assert setting_up["steps"][0]["label"] == "Download the programs for ADTOF"
        fake.release.set()
        assert wait(lambda: running.state()["kind"] == "empty" and fake.done)
    finally:
        running.stop()


def test_a_failed_download_names_the_server_and_can_be_tried_again(monkeypatch):
    from stickler_app import settings

    settings.update(settings.store_path(), setup_agreed=True)
    FakeSetup(monkeypatch, missing=("beat_this",), fail="weights:beat_this")
    running = Running()
    try:
        running.send("start")
        failed = running.until("setup_failed")
        assert failed["step"] == "weights:beat_this"
        assert failed["server"] == "JKU Linz (cloud.cp.jku.at) and Stickler’s copy (github.com)"
        assert failed["details"] == "Beat This! model not downloaded. JKU Linz: 500"
        assert failed["can_retry_setup"] and failed["can_not_now"]
        assert running.send("retry_setup")["ok"]
        assert wait(lambda: running.state()["kind"] == "empty")
        running.send("start")
        assert running.send("not_now")["error"]["code"] == "not_now"
    finally:
        running.stop()


def test_a_notice_reaches_the_app(monkeypatch):
    def broken(*a, **kw):
        raise RuntimeError("uv not found")

    monkeypatch.setattr(api, "mode_ready", broken)
    running = Running()
    try:
        running.send("start")
        assert wait(lambda: running.events("notice"))
        (notice,) = running.events("notice")
        assert notice["text"] == "Could not check the models: uv not found"
        assert notice["opens"] is None and notice["seq"] == 3
    finally:
        running.stop()


def test_the_recent_songs_are_sent_with_their_rows(tmp_path):
    there = tmp_path / "there.flac"
    there.write_bytes(b"x")
    recent.save(recent.store_path(), [recent.opened_now(there, "There", "Band")])
    running = Running()
    try:
        assert wait(lambda: running.events("recent"))
        assert running.events("recent")[0]["rows"] == [
            {
                "path": str(there),
                "title": "There",
                "detail": "Band · opened today",
                "missing": False,
            }
        ]
    finally:
        running.stop()


# the states the commands of Task 103 do not reach yet, encoded directly


def _notation(tmp_path) -> api.Notation:
    score = tmp_path / "eye.musicxml"
    score.write_text(groove_score().musicxml, encoding="utf-8")
    t = api.SongTranscription(tmp_path / "eye.flac", "fast", None, [], [], [])
    return api.Notation(score, None, None, t, [], 54, (3, 4))


def test_an_export_a_correction_and_a_failed_export_are_encoded(tmp_path):
    song = tmp_path / "eye.flac"
    info = api.SongInfo("Eye of the Tiger", "", 246.0)
    result = session.Result(song, info, _notation(tmp_path))
    exporting = session.export_drums(result, tmp_path / "drums.flac", setup=False)
    encoded = bridge.encode(exporting)
    assert encoded["kind"] == "exporting" and encoded["can_cancel"]
    assert encoded["title"] == "Eye of the Tiger" and encoded["subtitle"] == "♩ = 54 · 3/4"
    assert encoded["dest"] == str(tmp_path / "drums.flac")
    assert [r["id"] for r in encoded["steps"]] == ["separate"]

    correcting = session.correct(result, api.Corrections(tempo="half"))
    encoded = bridge.encode(correcting, remove_models=True)
    assert encoded["correcting"] and encoded["corrections"]["tempo"] == "half"
    assert encoded["can_remove_models"]

    failed = session.failed(exporting, exporting.job, RuntimeError("disk full"))
    encoded = bridge.encode(failed)
    assert encoded["reason"] == "export" and not encoded["can_retry"]


def test_a_running_download_says_how_much_it_has(tmp_path):
    state = session.start_setup(("environment:adtof", "weights:beat_this"))
    running_row = steps.row("environment:adtof", "running")
    state = session.SettingUp((running_row, *state.steps[1:]), state.job, grown=650_000_000)
    rows = bridge.encode(state)["steps"]
    assert rows[0]["detail"] == "650 MB of 1.3 GB"
    assert rows[1]["detail"] == "Once; later songs use it too"  # waiting: its line stays


def test_every_state_kind_is_encoded():
    assert set(bridge.KINDS) == set(bridge.ENCODERS)
    assert len(set(bridge.KINDS.values())) == len(bridge.KINDS)


# the lines going out


def test_a_full_queue_keeps_only_the_newest_states_and_every_other_line(monkeypatch):
    monkeypatch.setattr(bridge, "QUEUE_STATES", 3)
    box = bridge.Outbox()
    box.put("line", "hello")
    for n in range(5):
        box.put("state", n)
        box.put("notice", f"n{n}")
    box.close()
    taken = []
    while (item := box.take()) is not None:
        taken.append(item)
    assert [i for k, i in taken if k == "state"] == [2, 3, 4]
    assert [i for k, i in taken if k == "notice"] == ["n0", "n1", "n2", "n3", "n4"]
    assert taken[0] == ("line", "hello")


def test_a_line_that_cannot_be_written_is_logged_and_the_bridge_goes_on(caplog):
    class Gone(Stdout):
        def write(self, text):
            raise BrokenPipeError(32, "Broken pipe")

    stdin = Stdin()
    stdin.send('{"id": 1, "cmd": "quit"}')
    assert bridge.Bridge(stdin, Gone()).run() == 0
    assert "could not write a line" in caplog.text


def test_hello_names_the_language_the_bridge_speaks(monkeypatch):
    class German(gettext.NullTranslations):
        def info(self):
            return {"language": "de"}

        def gettext(self, message):
            return {"This is not possible right now.": "Das geht gerade nicht."}.get(
                message, message
            )

    monkeypatch.setattr(i18n, "_translation", German())
    assert bridge.hello()["language"] == "de"
    running = Running()
    try:
        assert running.send("cancel")["error"]["message"] == "Das geht gerade nicht."
    finally:
        running.stop()


def test_the_commands_of_this_release(running):
    assert running.bridge.commands == {
        "start",
        "agree",
        "not_now",
        "retry_setup",
        "open",
        "cancel",
        "retry",
        "close",
        "quit",
    }
