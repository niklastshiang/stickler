"""The controller's flows with stickler.api faked (no models): what the GTK window did in
release 7, reported as events."""

import threading
import time

import pytest
from fakes import FakeApi, FakeSetup, wait

from stickler import api
from stickler_app import controller, corrections, recent, session


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
    assert wait(lambda: isinstance(ctl.state, session.Result))
    return ctl.state


def test_an_analysis_reports_its_steps_and_ends_on_the_result(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert wait(lambda: isinstance(ctl.state, session.Result))
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
    assert wait(lambda: fake.runs)
    start = time.monotonic()
    assert ctl.cancel()
    assert isinstance(ctl.state, session.Empty)
    assert time.monotonic() - start < 0.1
    assert wait(lambda: fake.cancelled == [song], seconds=1)
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
    assert wait(lambda: len(fake.runs) == 1)
    ctl.open(second)
    assert ctl.state.previous == session.Empty()  # not the cancelled analysis
    assert wait(lambda: fake.cancelled == [first], seconds=1)
    fake.release.set()
    assert wait(lambda: isinstance(ctl.state, session.Result))
    assert ctl.state.song == second
    results = [s for s in host.states() if isinstance(s, session.Result)]
    assert [r.song for r in results] == [second]
    assert [s.path for s in ctl.recent] == [second]


def test_an_unreadable_file_fails_without_try_again(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    ctl = _made(host)
    ctl.open(tmp_path / "notes.txt")
    assert wait(lambda: isinstance(ctl.state, session.Failed))
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
    assert wait(lambda: isinstance(ctl.state, session.Failed))
    assert ctl.state.kind == "analysis" and ctl.state.can_retry
    assert ctl.state.details == "adtof (exit 1): out of memory"
    fake.error = None
    assert ctl.retry()
    assert wait(lambda: isinstance(ctl.state, session.Result))
    assert [r[0] for r in fake.runs] == [song, song]
    assert ctl.state.song == song


def test_missing_models_ask_for_consent_with_the_song(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    fake.error = api.SetupMissing(["adtof"])
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert wait(lambda: isinstance(ctl.state, session.Consent))
    assert ctl.state == session.Consent(("adtof",), song)


def test_close_goes_back_to_the_empty_window_and_stops_the_job(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert wait(lambda: fake.runs)
    ctl.close()
    assert ctl.state == session.Empty()
    assert wait(lambda: fake.cancelled == [song], seconds=1)


def test_shutdown_waits_for_the_job_to_clean_up(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    ctl.open(tmp_path / "eye.flac")
    assert wait(lambda: fake.runs)
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
    assert wait(lambda: ctl.state.pending is None)
    assert fake.runs[runs:] == [(song, api.Corrections(tempo="half"))]
    assert ctl.state.notation.tempo == 54
    assert ctl.state.corrections == api.Corrections(tempo="half")
    stored = corrections.load(corrections.store_path())
    assert stored == {song.absolute(): api.Corrections(tempo="half")}

    ctl.open(song)  # opened again: with its corrections
    assert wait(lambda: isinstance(ctl.state, session.Result))
    assert fake.runs[-1] == (song, api.Corrections(tempo="half"))
    assert ctl.state.notation.tempo == 54


def test_a_failed_correction_keeps_the_sheet_and_says_why(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    before = _result(ctl, tmp_path / "eye.flac")
    fake.error = RuntimeError("engrave failed")
    ctl.correct(api.Corrections(tempo="half"))
    assert wait(lambda: ctl.state.pending is None)
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
    assert wait(lambda: ctl.state.pending is None)
    assert ctl.state.notation.tempo == 54
    assert host.notices() == ["The correction could not be saved: Read-only file system"]


def test_a_correction_waiting_for_a_pause_is_dropped_by_a_new_song(monkeypatch, tmp_path, host):
    fake = FakeApi(monkeypatch)
    ctl = _made(host)
    _result(ctl, tmp_path / "first.flac")
    ctl.correct(api.Corrections(tempo="half"))
    ctl.open(tmp_path / "second.flac")
    assert wait(lambda: isinstance(ctl.state, session.Result))
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


# the setup assistant, exports and removal (Task 101)


def _agreed() -> bool:
    from stickler_app import settings

    return settings.load(settings.store_path()).setup_agreed


def _agree_before():
    from stickler_app import settings

    settings.update(settings.store_path(), setup_agreed=True)


def test_a_start_with_the_models_set_up_stays_empty(host):
    ctl = _made(host)
    ctl.start()
    time.sleep(0.1)
    assert ctl.state == session.Empty() and host.events == []
    ctl.shutdown()  # the model check is no job to wait for


def test_the_first_start_asks_and_not_now_goes_back_to_the_empty_window(monkeypatch, host):
    FakeSetup(monkeypatch)
    ctl = _made(host)
    assert not ctl.agree() and not ctl.not_now() and not ctl.retry_setup()
    ctl.start()
    assert wait(lambda: isinstance(ctl.state, session.Consent))
    assert ctl.state == session.Consent(("adtof", "beat_this"))
    assert ctl.not_now()
    assert ctl.state == session.Empty() and not _agreed()


def test_agreeing_downloads_the_models_and_opens_the_song_it_was_for(monkeypatch, tmp_path, host):
    fake = FakeSetup(monkeypatch, missing=("adtof",))
    analysed = FakeApi(monkeypatch)
    real = api.notate

    def notate(song, out, **kw):
        if "adtof" not in fake.done:
            raise api.SetupMissing(["adtof"])
        return real(song, out, **kw)

    monkeypatch.setattr(api, "notate", notate)
    ctl = _made(host)
    song = tmp_path / "eye.flac"
    ctl.open(song)
    assert wait(lambda: isinstance(ctl.state, session.Consent))
    assert ctl.agree()
    assert _agreed()
    assert wait(lambda: isinstance(ctl.state, session.Result))
    assert fake.done == ["adtof"] and ctl.state.song == song
    setting_up = [s for s in host.states() if isinstance(s, session.SettingUp)]
    assert [r.id for r in setting_up[0].steps] == ["environment:adtof"]
    assert setting_up[0].song == song
    assert [r[0] for r in analysed.runs] == [song]  # the first try stopped before the models


def test_an_agreed_download_goes_on_at_the_next_start_and_is_measured(monkeypatch, host):
    from stickler_app import setup

    _agree_before()
    fake = FakeSetup(monkeypatch, missing=("beat_this",), hold=True)
    fake.adapter_of_step = "beat_this"
    measured = []
    monkeypatch.setattr(controller, "SAMPLE", 0.02)
    monkeypatch.setattr(
        setup,
        "meter",
        lambda step_id, root, folder: measured.append(step_id) or (lambda: 39_000_000),
    )
    ctl = _made(host)
    ctl.start()
    assert wait(lambda: isinstance(ctl.state, session.SettingUp) and ctl.state.grown > 0)
    assert measured == ["environment:beat_this"]
    assert ctl.state.grown == 39_000_000
    fake.release.set()
    assert wait(lambda: ctl.state == session.Empty())
    assert fake.done == ["beat_this"]
    count = len(host.states())
    time.sleep(0.1)
    assert len(host.states()) == count  # the measuring stopped with the setup


def test_a_cancelled_download_goes_back_to_the_empty_window(monkeypatch, host):
    _agree_before()
    fake = FakeSetup(monkeypatch, hold=True)
    monkeypatch.setattr(controller, "SAMPLE", 0.02)
    ctl = _made(host)
    ctl.start()
    assert wait(lambda: isinstance(ctl.state, session.SettingUp))
    assert ctl.cancel()
    assert ctl.state == session.Empty()
    assert wait(lambda: fake.cancelled, seconds=1)
    assert fake.done == []


def test_a_failed_download_names_its_step_and_can_be_tried_again(monkeypatch, host):
    _agree_before()
    fake = FakeSetup(monkeypatch, missing=("beat_this",), fail="weights:beat_this")
    ctl = _made(host)
    ctl.start()
    assert wait(lambda: isinstance(ctl.state, session.SetupFailed))
    failed = ctl.state
    assert failed.step == "weights:beat_this" and failed.missing == ("beat_this",)
    assert "JKU Linz: 500" in failed.details
    assert ctl.retry_setup()
    assert wait(lambda: ctl.state == session.Empty())
    assert fake.attempts == ["beat_this", "beat_this"] and fake.done == ["beat_this"]


def test_later_after_a_failed_download_goes_back_to_the_empty_window(monkeypatch, host):
    _agree_before()
    FakeSetup(monkeypatch, missing=("adtof",), fail="environment:adtof")
    ctl = _made(host)
    ctl.start()
    assert wait(lambda: isinstance(ctl.state, session.SetupFailed))
    assert ctl.not_now()
    assert ctl.state == session.Empty()


def test_a_model_check_that_fails_says_so(monkeypatch, host):
    def broken(*a, **kw):
        raise RuntimeError("uv not found")

    monkeypatch.setattr(api, "mode_ready", broken)
    ctl = _made(host)
    ctl.start()
    assert wait(lambda: host.notices())
    assert host.notices() == ["Could not check the models: uv not found"]
    assert ctl.state == session.Empty()


def test_a_packaged_app_brings_its_adapters_up_to_date_before_the_check(
    monkeypatch, tmp_path, host
):
    from stickler_app import setup

    synced = []
    monkeypatch.setenv("STICKLER_ADAPTER_SOURCES", str(tmp_path / "shipped"))
    monkeypatch.setattr(setup, "sync_adapters", lambda shipped, root: synced.append(shipped))
    ctl = _made(host)
    ctl.start()
    assert wait(lambda: synced == [tmp_path / "shipped"])


def test_a_song_opened_during_the_check_is_not_interrupted(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    checked = threading.Event()

    def slow_check(*a, **kw):
        checked.wait(5)
        return ["adtof"]

    monkeypatch.setattr(api, "mode_ready", slow_check)
    ctl = _made(host)
    ctl.start()
    _result(ctl, tmp_path / "eye.flac")
    checked.set()
    time.sleep(0.1)
    assert isinstance(ctl.state, session.Result)


def test_the_musicxml_is_saved_where_chosen(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    ctl = _made(host)
    dest = tmp_path / "out" / "eye.musicxml"
    assert not ctl.export_musicxml(dest)
    result = _result(ctl, tmp_path / "eye.flac")
    assert ctl.export_musicxml(dest)
    assert dest.read_bytes() == result.notation.musicxml.read_bytes()
    assert host.events[-1] == controller.Notice("Saved “eye.musicxml”", dest)
    (tmp_path / "file").write_text("")
    assert ctl.export_musicxml(tmp_path / "file" / "eye.musicxml")  # a file is in the way
    assert host.notices()[-1].startswith("Could not save: ")
    assert ctl.state is result


def test_the_drum_track_cost_says_whether_demucs_comes_first(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    fake = FakeSetup(monkeypatch, missing=())
    ctl = _made(host)
    assert ctl.drum_track_cost() is None
    _result(ctl, tmp_path / "eye.flac")  # 246 s at 1.84: about 8 minutes
    cost = ctl.drum_track_cost()
    assert cost == controller.DrumTrackCost(
        8, "Separating the drums takes about 8 minutes on this computer.", False
    )
    fake.missing = ["demucs"]
    cost = ctl.drum_track_cost()
    assert cost.download and "Demucs is downloaded once (about 1.2 GB)" in cost.text


def _fake_drums(monkeypatch, tmp_path, error=None):
    stem = tmp_path / "stem.wav"
    stem.write_bytes(b"RIFF")
    separated = []

    def transcribe(song, *, drums, progress, cancel, adapters_root, cache_dir):
        progress(api.Step("separate", 1, 1, "started", False, "demucs"))
        if error is not None:
            raise error
        progress(api.Step("separate", 1, 1, "done", False, "demucs"))
        separated.append(song)
        return api.SongTranscription(song, "fast", stem, [], [], [])

    def export(stem, dest):
        dest.write_bytes(stem.read_bytes())
        return dest

    monkeypatch.setattr(api, "transcribe_song", transcribe)
    monkeypatch.setattr(api, "export_drum_track", export)
    return separated


def test_the_drum_track_is_saved_with_steps_and_back_to_the_result(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    fake = FakeSetup(monkeypatch, missing=())
    separated = _fake_drums(monkeypatch, tmp_path)
    ctl = _made(host)
    dest = tmp_path / "eye (drums).flac"
    assert not ctl.export_drum_track(dest)
    result = _result(ctl, tmp_path / "eye.flac")
    assert ctl.export_drum_track(dest)
    assert wait(lambda: ctl.state is result)
    exporting = [s for s in host.states() if isinstance(s, session.Exporting)]
    assert [r.id for r in exporting[0].steps] == ["separate"]
    assert [r.state for r in exporting[-1].steps] == ["done"]
    assert dest.read_bytes() == b"RIFF" and separated == [result.song]
    assert host.events[-1] == controller.Notice("Saved “eye (drums).flac”", dest)
    assert fake.attempts == []


def test_the_drum_track_downloads_demucs_first_when_missing(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    fake = FakeSetup(monkeypatch, missing=("demucs",))
    _fake_drums(monkeypatch, tmp_path)
    ctl = _made(host)
    result = _result(ctl, tmp_path / "eye.flac")
    ctl.export_drum_track(tmp_path / "drums.flac")
    assert wait(lambda: ctl.state is result)
    exporting = [s for s in host.states() if isinstance(s, session.Exporting)]
    assert [r.id for r in exporting[0].steps] == [
        "environment:demucs",
        "weights:demucs",
        "separate",
    ]
    assert fake.done == ["demucs"]


def test_a_failed_drum_track_shows_the_error_and_can_be_cancelled(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    FakeSetup(monkeypatch, missing=())
    _fake_drums(monkeypatch, tmp_path, error=RuntimeError("demucs (exit 1)"))
    ctl = _made(host)
    result = _result(ctl, tmp_path / "eye.flac")
    ctl.export_drum_track(tmp_path / "drums.flac")
    assert wait(lambda: isinstance(ctl.state, session.Failed))
    assert ctl.state.kind == "export" and ctl.state.previous is result
    assert not ctl.state.can_retry


def test_a_cancelled_drum_track_goes_back_to_the_result(monkeypatch, tmp_path, host):
    FakeApi(monkeypatch)
    fake = FakeSetup(monkeypatch, missing=("demucs",), hold=True)
    ctl = _made(host)
    result = _result(ctl, tmp_path / "eye.flac")
    ctl.export_drum_track(tmp_path / "drums.flac")
    assert wait(lambda: fake.attempts == ["demucs"])
    assert ctl.cancel()
    assert ctl.state is result
    assert wait(lambda: fake.cancelled, seconds=1)


def _installed(monkeypatch):
    """An AppImage with downloaded models, inside the tests' private XDG folders."""
    import os

    from stickler_app import paths, settings

    monkeypatch.setenv("APPIMAGE", "/x/Stickler.AppImage")
    monkeypatch.setenv("SHARUN_DIR", "/tmp/.mount_x")
    weights = paths.data_home() / "adapters" / "transcribers" / "adtof" / "weights"
    weights.mkdir(parents=True)
    (weights / "model.pt").write_bytes(b"x" * 1000)
    (paths.cache_home() / "scores").mkdir(parents=True)
    (paths.cache_home() / "scores" / "eye.musicxml").write_bytes(b"x" * 100)
    settings.update(settings.store_path(), setup_agreed=True)
    assert os.environ["APPIMAGE"]
    return weights


def test_models_are_removed_only_from_an_installed_app(monkeypatch, tmp_path, host):
    ctl = _made(host)
    assert not ctl.can_remove_models and not ctl.remove_models(False)
    assert ctl.removal_sizes() == (0, 0)


def test_removing_the_models_asks_again_before_the_next_download(monkeypatch, tmp_path, host):
    from stickler_app import paths, settings

    weights = _installed(monkeypatch)
    there = tmp_path / "there.flac"
    recent.save(recent.store_path(), [recent.opened_now(there, "There", "")])
    ctl = _made(host)
    models, everything = ctl.removal_sizes()
    assert models == 1100 and everything > models  # the settings and recent songs too
    assert ctl.can_remove_models
    assert ctl.remove_models(False)
    assert wait(lambda: host.notices())
    assert host.notices() == ["The downloaded models are removed"]
    assert not weights.exists() and not paths.cache_home().exists()
    assert not settings.load(settings.store_path()).setup_agreed
    assert [s.title for s in ctl.recent] == ["There"]
    assert ctl.state == session.Empty() and ctl.can_remove_models


def test_removing_everything_also_forgets_the_recent_songs(monkeypatch, tmp_path, host):
    from stickler_app import paths, setup

    _installed(monkeypatch)
    shipped = tmp_path / "shipped"
    monkeypatch.setenv("STICKLER_ADAPTER_SOURCES", str(shipped))
    synced = []
    monkeypatch.setattr(setup, "sync_adapters", lambda source, root: synced.append(root))
    recent.save(recent.store_path(), [recent.opened_now(tmp_path / "a.flac", "A", "")])
    ctl = _made(host)
    assert ctl.remove_models(True)
    assert wait(lambda: host.notices())
    assert ctl.recent == () and host.recents() == [()]
    assert not recent.store_path().exists()
    assert synced == [paths.adapters_root()]  # the sources are back for the next setup


def test_a_removal_that_fails_says_why(monkeypatch, tmp_path, host):
    from stickler_app import removal

    _installed(monkeypatch)

    def busy(folders):
        raise OSError(16, "Device or resource busy")

    monkeypatch.setattr(removal, "remove", busy)
    ctl = _made(host)
    ctl.remove_models(False)
    assert wait(lambda: host.notices())
    assert host.notices() == ["Could not remove everything: [Errno 16] Device or resource busy"]
    assert ctl.can_remove_models


def test_models_are_not_removed_while_something_runs(monkeypatch, tmp_path, host):
    _installed(monkeypatch)
    FakeApi(monkeypatch, hold=True)
    ctl = _made(host)
    ctl.open(tmp_path / "eye.flac")
    assert not ctl.can_remove_models and not ctl.remove_models(False)
    ctl.shutdown()
