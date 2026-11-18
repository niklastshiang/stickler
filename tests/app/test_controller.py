"""The controller's flows with stickler.api faked (no models): what the GTK window did in
release 7, reported as events."""

import threading
import time
from pathlib import Path

import pytest

from stickler import api
from stickler_app import controller, corrections, recent, session


def _wait(predicate, seconds=5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _groove_score():
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
        engraved = _groove_score()
        Path(out).write_text(engraved.musicxml, encoding="utf-8")
        t = api.SongTranscription(song, "fast", None, [], [], [])
        tempo = {"half": 54, "normal": 109, "double": 218}[fix.tempo]
        return api.Notation(Path(out), None, None, t, engraved.bars, tempo, (4, 4))


class Host:
    """Collects the events, as the bridge's queue does."""

    def __init__(self):
        self.events: list[controller.Event] = []
        self.lock = threading.Lock()

    def post(self, event):
        with self.lock:
            self.events.append(event)

    def states(self):
        with self.lock:
            return [e.state for e in self.events if isinstance(e, controller.Changed)]

    def notices(self):
        with self.lock:
            return [e.text for e in self.events if isinstance(e, controller.Notice)]

    def recents(self):
        with self.lock:
            return [e.songs for e in self.events if isinstance(e, controller.RecentChanged)]


@pytest.fixture
def host():
    return Host()


def _made(host) -> controller.Controller:
    return controller.Controller(post=host.post)


def _result(ctl, song) -> session.Result:
    ctl.open(song)
    assert _wait(lambda: isinstance(ctl.state, session.Result))
    return ctl.state


def test_an_analysis_reports_its_steps_and_ends_on_the_result(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert _wait(lambda: isinstance(ctl.state, session.Result))
    states = host.states()
    assert isinstance(states[0], session.Analysing) and states[0].song == song
    assert all(s.state == "waiting" for s in states[0].steps)
    running = [s for s in states if isinstance(s, session.Analysing)]
    assert len(running) == 7  # planned, then each of three steps started and done
    assert [r.state for r in running[-1].steps] == ["done"] * len(running[-1].steps)
    result = states[-1]
    assert result is ctl.state and result.subtitle == "Survivor · ♩ = 109 · 4/4"
    # the song is recent now, saved and reported before the result
    assert [s.title for s in recent.load(recent.store_path())] == ["Eye of the Tiger"]
    assert ctl.recent[0].path == song
    kinds = [type(e) for e in host.events]
    assert kinds[-2:] == [controller.RecentChanged, controller.Changed]


def test_a_cancel_goes_back_at_once_and_stops_the_job(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    assert not ctl.cancel()  # nothing runs
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert _wait(lambda: fake.runs)
    start = time.monotonic()
    assert ctl.cancel()
    assert isinstance(ctl.state, session.Empty)
    assert time.monotonic() - start < 0.1
    assert _wait(lambda: fake.cancelled == [song], seconds=1)
    time.sleep(0.05)
    assert isinstance(host.states()[-1], session.Empty)  # the job's end changes nothing
    assert recent.load(recent.store_path()) == []


def test_a_cancel_returns_to_the_song_shown_before(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    first = _result(ctl, tmp_path / "first.flac")
    fake.hold = True
    ctl.open(tmp_path / "second.flac")
    assert isinstance(ctl.state, session.Analysing)
    assert ctl.state.previous is first
    ctl.cancel()
    assert ctl.state is first


def test_a_second_song_replaces_the_running_one(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    first, second = tmp_path / "first.flac", tmp_path / "second.flac"
    ctl.open(first)
    assert _wait(lambda: len(fake.runs) == 1)
    ctl.open(second)
    assert ctl.state.previous == session.Empty()  # not the cancelled analysis
    assert _wait(lambda: fake.cancelled == [first], seconds=1)
    fake.release.set()
    assert _wait(lambda: isinstance(ctl.state, session.Result))
    assert ctl.state.song == second
    results = [s for s in host.states() if isinstance(s, session.Result)]
    assert [r.song for r in results] == [second]
    assert [s.path for s in ctl.recent] == [second]


def test_an_unreadable_file_fails_without_try_again(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    ctl = _made(host)
    ctl.open(tmp_path / "notes.txt")
    assert _wait(lambda: isinstance(ctl.state, session.Failed))
    failed = ctl.state
    assert failed.kind == "unreadable" and failed.title == "Cannot Read This File"
    assert failed.details == "ffprobe: invalid data"
    assert not failed.can_retry
    assert not ctl.retry()


def test_a_failed_analysis_can_be_tried_again(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    fake.error = RuntimeError("adtof (exit 1): out of memory")
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert _wait(lambda: isinstance(ctl.state, session.Failed))
    assert ctl.state.kind == "analysis" and ctl.state.can_retry
    assert ctl.state.details == "adtof (exit 1): out of memory"
    fake.error = None
    assert ctl.retry()
    assert _wait(lambda: isinstance(ctl.state, session.Result))
    assert [r[0] for r in fake.runs] == [song, song]
    assert ctl.state.song == song


def test_missing_models_ask_for_consent_with_the_song(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    fake.error = api.SetupMissing(["adtof"])
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert _wait(lambda: isinstance(ctl.state, session.Consent))
    assert ctl.state == session.Consent(("adtof",), song)


def test_close_goes_back_to_the_empty_window_and_stops_the_job(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert _wait(lambda: fake.runs)
    ctl.close()
    assert ctl.state == session.Empty()
    assert _wait(lambda: fake.cancelled == [song], seconds=1)


def test_shutdown_waits_for_the_job_to_clean_up(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    ctl.open(tmp_path / "eye.flac")
    assert _wait(lambda: fake.runs)
    start = time.monotonic()
    ctl.shutdown(2.0)
    assert fake.cancelled and time.monotonic() - start < 1
    ctl.shutdown()  # nothing left to stop


def test_recent_songs_can_be_forgotten(monkeypatch, tmp_path, host):
    there, gone = tmp_path / "there.flac", tmp_path / "gone.flac"
    today = recent.opened_now(there, "There", "").opened
    recent.save(
        recent.store_path(),
        [recent.Recent(there, "There", "", today), recent.Recent(gone, "Gone", "", today)],
    )
    ctl = _made(host)
    assert [s.title for s in ctl.recent] == ["There", "Gone"]
    ctl.forget_recent(gone)
    assert [s.title for s in ctl.recent] == ["There"]
    assert [s.title for s in recent.load(recent.store_path())] == ["There"]
    assert [[s.title for s in songs] for songs in host.recents()] == [["There"]]


def test_recent_songs_that_cannot_be_saved_still_change_with_a_notice(monkeypatch, tmp_path, host):
    def full(store, songs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(recent, "save", full)
    FakeApi(monkeypatch)
    ctl = _made(host)
    _result(ctl, tmp_path / "eye.flac")
    assert [s.title for s in ctl.recent] == ["Eye of the Tiger"]
    assert host.notices() == ["Recent songs could not be saved: No space left on device"]


def test_quick_corrections_make_one_run_and_the_newest_is_stored(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    assert not ctl.correct(api.Corrections(tempo="half"))  # no result yet
    song = tmp_path / "eye.flac"
    _result(ctl, song)
    runs = len(fake.runs)
    assert ctl.correct(api.Corrections(tempo="double"))
    assert ctl.correct(api.Corrections(tempo="half"))
    assert ctl.state.wanted == api.Corrections(tempo="half")  # shown before the sheet is ready
    assert ctl.state.notation.tempo == 109
    assert _wait(lambda: ctl.state.pending is None)
    assert fake.runs[runs:] == [(song, api.Corrections(tempo="half"))]
    assert ctl.state.notation.tempo == 54
    assert ctl.state.corrections == api.Corrections(tempo="half")
    stored = corrections.load(corrections.store_path())
    assert stored == {song.absolute(): api.Corrections(tempo="half")}

    ctl.open(song)  # opened again: with its corrections
    assert _wait(lambda: isinstance(ctl.state, session.Result))
    assert fake.runs[-1] == (song, api.Corrections(tempo="half"))
    assert ctl.state.notation.tempo == 54


def test_a_failed_correction_keeps_the_sheet_and_says_why(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    before = _result(ctl, tmp_path / "eye.flac")
    fake.error = RuntimeError("engrave failed")
    ctl.correct(api.Corrections(tempo="half"))
    assert _wait(lambda: ctl.state.pending is None)
    assert ctl.state.notation is before.notation
    assert ctl.state.corrections == api.Corrections()
    assert host.notices() == ["The correction did not work: engrave failed"]
    assert corrections.load(corrections.store_path()) == {}


def test_a_correction_that_cannot_be_stored_still_shows(monkeypatch, tmp_path, host):
    def read_only(store, song, fix):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(corrections, "remember", read_only)
    FakeApi(monkeypatch)
    ctl = _made(host)
    _result(ctl, tmp_path / "eye.flac")
    ctl.correct(api.Corrections(tempo="half"))
    assert _wait(lambda: ctl.state.pending is None)
    assert ctl.state.notation.tempo == 54
    assert host.notices() == ["The correction could not be saved: Read-only file system"]


def test_a_correction_waiting_for_a_pause_is_dropped_by_a_new_song(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    _result(ctl, tmp_path / "first.flac")
    ctl.correct(api.Corrections(tempo="half"))
    ctl.open(tmp_path / "second.flac")
    assert _wait(lambda: isinstance(ctl.state, session.Result))
    time.sleep(controller.CORRECT_AFTER + 0.1)
    assert [r[1] for r in fake.runs] == [api.Corrections(), api.Corrections()]
    assert ctl.state.song == tmp_path / "second.flac"


def test_shutdown_drops_a_correction_waiting_for_a_pause(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    _result(ctl, tmp_path / "eye.flac")
    ctl.correct(api.Corrections(tempo="half"))
    ctl.shutdown()
    time.sleep(controller.CORRECT_AFTER + 0.1)
    assert len(fake.runs) == 1
