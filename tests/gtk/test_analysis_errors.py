"""Cancel and errors of an analysis, without GTK (design: errors in the user's words)."""

from pathlib import Path

import pytest

from stickler import api
from stickler_gtk.logic import analysis, session


def _notation():
    t = api.SongTranscription(Path("s.flac"), "fast", None, [], [], [])
    return api.Notation(Path("s.musicxml"), None, None, t, [], 120, (4, 4))


def _result():
    state = session.open_song(Path("old.flac"), session.Empty())
    return session.finished(state, state.job, api.SongInfo("Old", "", 1.0), _notation())


def test_cancel_returns_to_where_the_user_came_from():
    empty = session.Empty()
    assert session.cancel(session.open_song(Path("s.flac"), empty)) is empty
    result = _result()
    assert session.cancel(session.open_song(Path("new.flac"), result)) is result


def test_reports_of_a_cancelled_or_replaced_job_are_ignored():
    first = session.open_song(Path("a.flac"), session.Empty())
    second = session.open_song(Path("b.flac"), first)
    assert second.job != first.job
    step = api.Step("transcribe", 1, 3, "started")
    assert session.on_step(second, first.job, step) is second
    assert session.finished(second, first.job, api.SongInfo("A", "", 1.0), _notation()) is second
    assert session.failed(second, first.job, RuntimeError("late")) is second
    back = session.cancel(second)
    assert session.finished(back, second.job, api.SongInfo("B", "", 1.0), _notation()) is back


def test_a_missing_model_names_it_and_the_command_that_sets_it_up():
    state = session.open_song(Path("s.flac"), session.Empty())
    error = session.failed(state, state.job, api.SetupMissing(["adtof", "beat_this"]))
    assert isinstance(error, session.Failed) and error.kind == "setup"
    assert "ADTOF" in error.description and "Beat This!" in error.description
    assert error.details == ("stickler setup --adapter adtof\nstickler setup --adapter beat_this")
    assert not error.can_retry


def test_an_unreadable_file_is_told_apart_from_a_failed_analysis():
    state = session.open_song(Path("notes.mp3"), session.Empty())
    unreadable = session.failed(state, state.job, analysis.Unreadable("ffprobe: Invalid data"))
    assert unreadable.kind == "unreadable" and "notes.mp3" in unreadable.description
    assert unreadable.details == "ffprobe: Invalid data" and not unreadable.can_retry
    broken = session.failed(state, state.job, RuntimeError("adtof (exit 1):\nTraceback ..."))
    assert broken.kind == "analysis" and broken.can_retry
    assert broken.details.startswith("adtof (exit 1)")


def test_a_cancel_reported_by_the_worker_goes_back_like_cancel():
    empty = session.Empty()
    state = session.open_song(Path("s.flac"), empty)
    assert session.failed(state, state.job, api.Cancelled("cancelled")) is empty


def test_try_again_starts_the_same_song_anew():
    state = session.open_song(Path("s.flac"), session.Empty())
    error = session.failed(state, state.job, RuntimeError("boom"))
    again = session.retry(error)
    assert isinstance(again, session.Analysing) and again.song == Path("s.flac")
    assert again.job != state.job and again.previous == error.previous


def test_the_analysis_job_reads_the_song_first_and_says_when_it_cannot(monkeypatch):
    calls = []

    def unreadable(path):
        raise RuntimeError("ffprobe: notes.mp3: Invalid data")

    monkeypatch.setattr(api, "song_info", unreadable)
    monkeypatch.setattr(api, "notate", lambda *a, **kw: calls.append(a))
    with pytest.raises(analysis.Unreadable, match="Invalid data"):
        analysis.analyse(Path("notes.mp3"), Path("out.musicxml"), lambda s: None, api.CancelToken())
    assert calls == []


def test_the_analysis_job_passes_progress_and_cancel_to_notate(monkeypatch):
    seen = {}
    info = api.SongInfo("Eye of the Tiger", "Survivor", 246.0)
    monkeypatch.setattr(api, "song_info", lambda p: info)

    def notate(song, out, **kw):
        seen.update(kw, song=song, out=out)
        return _notation()

    monkeypatch.setattr(api, "notate", notate)
    token = api.CancelToken()
    got = analysis.analyse(Path("eye.flac"), Path("eye.musicxml"), print, token)
    assert got == (info, _notation())
    assert seen["cancel"] is token and seen["progress"] is print and seen["pdf"] is False
    assert (seen["title"], seen["artist"]) == ("Eye of the Tiger", "Survivor")
