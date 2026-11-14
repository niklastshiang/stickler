"""The window's decisions, without GTK: steps, states, where files go."""

from pathlib import Path

from stickler import api
from stickler_gtk.logic import paths, session, steps


def _step(step_id, index, total, state, cached=False):
    return api.Step(step_id, index, total, state, cached, None)


def test_every_analysis_step_has_a_label_and_a_line_of_what_it_does():
    for step_id in ("separate", "transcribe", "beats", "engrave", "pdf"):
        row = steps.row(step_id)
        assert row.label and row.detail and row.label != step_id
        assert row.state == "waiting"


def test_an_unknown_step_still_gets_a_row():
    row = steps.row("environment:adtof")
    assert row.label == "environment:adtof" and row.detail == ""


def test_fast_is_planned_as_three_waiting_steps():
    rows = session.open_song(Path("song.flac"), session.Empty()).steps
    assert [r.id for r in rows] == ["transcribe", "beats", "engrave"]
    assert {r.state for r in rows} == {"waiting"}


def test_progress_moves_each_step_from_waiting_to_running_to_done():
    state = session.open_song(Path("song.flac"), session.Empty())
    state = session.on_step(state, state.job, _step("transcribe", 1, 3, "started"))
    assert [r.state for r in state.steps] == ["running", "waiting", "waiting"]
    state = session.on_step(state, state.job, _step("transcribe", 1, 3, "done"))
    state = session.on_step(state, state.job, _step("beats", 2, 3, "started"))
    assert [r.state for r in state.steps] == ["done", "running", "waiting"]


def test_steps_the_plan_did_not_expect_are_added():
    state = session.open_song(Path("song.flac"), session.Empty())
    state = session.on_step(state, state.job, _step("separate", 4, 4, "started"))
    assert [r.id for r in state.steps] == ["transcribe", "beats", "engrave", "separate"]
    assert state.steps[3].state == "running"


def test_progress_after_the_analysis_changes_nothing():
    state = session.open_song(Path("s.flac"), session.Empty())
    result = session.finished(state, state.job, api.SongInfo("T", "A", 1.0), _notation())
    assert session.on_step(result, state.job, _step("engrave", 3, 3, "done")) is result


def _notation(tempo=109, meter=(4, 4)):
    t = api.SongTranscription(Path("s.flac"), "fast", None, [], [], [])
    return api.Notation(Path("s.musicxml"), None, None, t, [], tempo, meter)


def test_the_result_names_artist_tempo_and_meter():
    state = session.open_song(Path("eye.flac"), session.Empty())
    info = api.SongInfo("Eye of the Tiger", "Survivor", 246.0)
    result = session.finished(state, state.job, info, _notation())
    assert result.title == "Eye of the Tiger"
    assert result.subtitle == "Survivor · ♩ = 109 · 4/4"
    untagged = session.finished(
        state, state.job, api.SongInfo("eye", "", 1.0), _notation(96, (3, 4))
    )
    assert untagged.subtitle == "♩ = 96 · 3/4"


def test_a_failed_analysis_leads_to_an_error_page_that_can_go_back():
    empty = session.Empty()
    state = session.open_song(Path("s.flac"), empty)
    error = session.failed(state, state.job, RuntimeError("ffmpeg: no audio"))
    assert isinstance(error, session.Failed) and error.details == "ffmpeg: no audio"
    assert error.previous is empty


def test_only_audio_files_are_taken():
    assert paths.is_audio(Path("Song.FLAC")) and paths.is_audio(Path("a.mp3"))
    assert not paths.is_audio(Path("notes.pdf")) and not paths.is_audio(Path("folder"))


def test_scores_go_to_the_apps_cache_one_per_song(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    a = paths.score_path(Path("/music/a/Song.flac"), env)
    b = paths.score_path(Path("/music/b/Song.flac"), env)
    assert a.parent == tmp_path / "stickler" / "scores" and a.suffix == ".musicxml"
    assert a != b and a.name.startswith("Song-")
    assert paths.score_path(Path("/music/a/Song.flac"), {"HOME": str(tmp_path)}).is_relative_to(
        tmp_path / ".cache" / "stickler"
    )
