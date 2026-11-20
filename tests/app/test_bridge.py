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

import stickler
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
    assert hello == {
        "event": "hello",
        "protocol": 1,
        "version": stickler.__version__,  # the release's number, not one frozen here
        "language": "en",
    }
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


# the commands of Task 104


def _with_result(monkeypatch, tmp_path) -> Running:
    FakeApi(monkeypatch)
    running = Running()
    running.send("open", path=str(tmp_path / "eye.flac"))
    running.until("result")
    return running


@pytest.mark.parametrize(
    ("cmd", "args"),
    [
        ("pages", {"width": 800}),
        ("a4_pages", {}),
        ("export_musicxml", {"dest": "/x.musicxml"}),
        ("drum_track_cost", {}),
        ("export_drum_track", {"dest": "/x.flac"}),
        ("remove_models", {"everything": False}),
    ],
)
def test_the_result_commands_need_a_result(running, cmd, args):
    assert running.send(cmd, **args)["error"]["code"] == "not_now"


def test_the_pages_come_as_svg_with_their_bars(monkeypatch, tmp_path):
    from stickler_app import settings

    running = _with_result(monkeypatch, tmp_path)
    try:
        reply = running.send("pages", width=800)
        assert reply["zoom"] == 1.0
        (page,) = reply["pages"]
        assert page["svg"].startswith("<svg") and page["width"] == 800.0
        assert [b["bar"] for b in page["bars"]] == list(range(1, 9))
        assert set(page["bars"][0]) == {"bar", "x", "y", "width", "height"}
        settings.update(settings.store_path(), zoom=2.0)
        larger = running.send("pages", width=800)  # the stored note size
        assert larger["zoom"] == 2.0 and larger["pages"][0]["height"] > page["height"]
        assert running.send("pages", width=800, zoom=9)["zoom"] == 3.0  # clamped
        for bad in (
            {},
            {"width": 0},
            {"width": "800"},
            {"width": True},
            {"width": 800, "zoom": -1},
        ):
            assert running.send("pages", **bad)["error"]["code"] == "bad_argument"

        a4 = running.send("a4_pages")
        assert a4["title"] == "Eye of the Tiger"
        assert [(p["width"], p["height"]) for p in a4["pages"]] == [(1050.0, 1485.0)]
    finally:
        running.stop()


def test_the_musicxml_is_saved_and_a_notice_offers_to_open_it(monkeypatch, tmp_path):
    running = _with_result(monkeypatch, tmp_path)
    try:
        dest = tmp_path / "out" / "eye.musicxml"
        assert running.send("export_musicxml", dest=str(dest)) == {"id": 2, "ok": True}
        assert dest.is_file()
        assert wait(lambda: running.events("notice"))
        notice = running.events("notice")[-1]
        assert notice["text"] == "Saved “eye.musicxml”" and notice["opens"] == str(dest)
        assert running.send("export_musicxml")["error"]["code"] == "bad_argument"
    finally:
        running.stop()


def test_the_drum_track_says_its_cost_then_is_saved(monkeypatch, tmp_path):
    running = _with_result(monkeypatch, tmp_path)
    FakeSetup(monkeypatch, missing=())
    stem = tmp_path / "stem.wav"
    stem.write_bytes(b"RIFF")

    def transcribe(song, *, drums, progress, cancel, adapters_root, cache_dir):
        return api.SongTranscription(song, "fast", stem, [], [], [])

    def export(source, dest):
        dest.write_bytes(source.read_bytes())
        return dest

    monkeypatch.setattr(api, "transcribe_song", transcribe)
    monkeypatch.setattr(api, "export_drum_track", export)
    try:
        cost = running.send("drum_track_cost")
        assert cost == {
            "id": 2,
            "ok": True,
            "minutes": 8,
            "text": "Separating the drums takes about 8 minutes on this computer.",
            "download": False,
        }
        dest = tmp_path / "drums.flac"
        assert running.send("export_drum_track", dest=str(dest))["ok"]
        assert wait(lambda: dest.is_file() and running.state()["kind"] == "result")
        assert any(s["kind"] == "exporting" for s in running.states())
    finally:
        running.stop()


def test_a_recent_song_can_be_forgotten(tmp_path):
    gone = tmp_path / "gone.flac"
    recent.save(recent.store_path(), [recent.opened_now(gone, "Gone", "")])
    running = Running()
    try:
        assert running.send("forget_recent", path=str(gone))["ok"]
        assert wait(lambda: len(running.events("recent")) == 2)
        assert running.events("recent")[-1]["rows"] == []
    finally:
        running.stop()


def test_the_note_size_is_set_stepped_and_remembered(running):
    from stickler_app import settings

    assert running.send("settings") == {
        "id": 1,
        "ok": True,
        "appearance": "system",
        "zoom": 1.0,
        "song_volume": 0.7,
        "hits_volume": 1.0,
        "setup_agreed": False,
        "percent": "100%",
    }
    assert running.send("zoom_in")["zoom"] == 1.25
    assert running.send("zoom_in")["percent"] == "156%"
    assert running.send("zoom_out")["zoom"] == 1.25
    assert running.send("set_zoom", zoom=9)["zoom"] == 3.0
    assert running.send("actual_size") == {"id": 6, "ok": True, "zoom": 1.0, "percent": "100%"}
    assert running.send("set_zoom", zoom=0.6)["zoom"] == 0.6
    assert settings.load(settings.store_path()).zoom == 0.6
    assert running.send("set_zoom", zoom="big")["error"]["code"] == "bad_argument"


def test_a_note_size_that_cannot_be_saved_still_holds(monkeypatch, running, caplog):
    from stickler_app import settings

    def read_only(store, **changes):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(settings, "update", read_only)
    assert running.send("zoom_in")["zoom"] == 1.25
    assert "could not be saved" in caplog.text


def test_removal_sizes_come_with_the_dialogs_texts(running):
    reply = running.send("removal_sizes")  # from the checkout nothing is removed
    assert reply == {
        "id": 1,
        "ok": True,
        "models": 0,
        "everything": 0,
        "models_text": "This frees 0 MB. Stickler asks before it downloads the models again.",
        "everything_text": "This frees 0 MB. Stickler asks before it downloads the models again.",
    }


def test_an_installed_app_removes_its_models(monkeypatch, tmp_path):
    from stickler_app import paths

    monkeypatch.setenv("STICKLER_PACKAGED", "macos")
    weights = paths.data_home() / "adapters" / "beats" / "beat_this" / "weights"
    weights.mkdir(parents=True)
    (weights / "model.ckpt").write_bytes(b"x" * 2_000_000)
    running = Running()
    try:
        assert wait(lambda: running.states())
        assert running.state()["can_remove_models"]
        sizes = running.send("removal_sizes")
        assert sizes["models"] == 2_000_000 and sizes["models_text"].startswith("This frees 2 MB.")
        assert running.send("remove_models")["error"]["code"] == "bad_argument"
        assert running.send("remove_models", everything=False)["ok"]
        assert wait(lambda: running.events("notice"))
        assert running.events("notice")[-1]["text"] == "The downloaded models are removed"
        assert not weights.exists()
    finally:
        running.stop()


def test_a_command_that_fails_unforeseen_gets_internal_and_the_bridge_goes_on(
    monkeypatch, running, caplog
):
    from stickler_app import controller

    def broken(self):
        raise KeyError("adtof")

    monkeypatch.setattr(controller.Controller, "start", broken)
    assert running.send("start")["error"] == {
        "code": "internal",
        "message": "Something went wrong inside Stickler.",
    }
    assert "command start failed" in caplog.text and "KeyError" in caplog.text
    assert running.send("close")["ok"]


def test_close_song_fits_only_while_a_song_is_in_the_window():
    song, failed = Path("eye.flac"), "analysis"
    with_song = (
        session.Analysing(song, (), 1, session.Empty()),
        session.Failed(song, failed, "Failed", "", "", session.Empty()),
    )
    without = (
        session.Empty(),
        session.Consent(("adtof",)),
        session.SettingUp((), 1),
        session.SetupFailed((), "weights:adtof", "", ("adtof",)),
    )
    for state in with_song:
        assert bridge.can(state, remove_models=False)["can_close"], state
    for state in without:
        assert not bridge.can(state, remove_models=False)["can_close"], state
