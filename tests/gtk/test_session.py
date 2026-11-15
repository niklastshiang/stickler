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
    row = steps.row("mystery")
    assert row.label == "mystery" and row.detail == ""


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


def _shown(fix=None):
    state = session.open_song(Path("eye.flac"), session.Empty(), fix or api.Corrections())
    t = api.SongTranscription(Path("eye.flac"), "fast", None, [], [], [])
    notation = api.Notation(Path("eye.musicxml"), None, None, t, [], 109, (4, 4))
    return session.finished(state, state.job, api.SongInfo("Eye", "", 246.0), notation)


def test_a_song_opens_with_its_stored_corrections():
    half = api.Corrections(tempo="half")
    result = _shown(half)
    assert result.corrections == half and result.wanted == half and result.pending is None


def test_only_the_newest_correction_is_shown_and_a_failed_one_keeps_the_sheet():
    from dataclasses import replace

    result = _shown()
    half, double = api.Corrections(tempo="half"), api.Corrections(tempo="double")
    first = session.correct(result, half)
    second = session.correct(first, double)
    assert second.wanted == double and second.corrections == result.corrections
    halved = replace(result.notation, tempo=54)
    assert session.corrected(second, first.pending.job, halved) is second  # stale: ignored
    doubled = replace(result.notation, tempo=218)
    done = session.corrected(second, second.pending.job, doubled)
    assert (done.notation.tempo, done.corrections, done.pending) == (218, double, None)
    again = session.correct(done, half)
    kept = session.correction_failed(again, again.pending.job)
    assert (kept.notation.tempo, kept.wanted, kept.pending) == (218, double, None)
    assert session.correction_failed(kept, 999) is kept
    assert session.corrected(session.Empty(), 1, doubled) == session.Empty()


def test_the_setup_runs_its_steps_and_then_opens_the_song_it_was_for():
    asked = session.consent(("adtof", "beat_this"), Path("eye.flac"))
    running = session.start_setup(
        ("environment:adtof", "weights:beat_this"), asked.song, asked.missing
    )
    assert [r.state for r in running.steps] == ["waiting", "waiting"]
    step = api.Step("environment:adtof", 1, 1, "started", False, None)
    running = session.on_setup_step(running, running.job, step)
    assert running.steps[0].state == "running" and running.grown == 0
    running = session.setup_grew(running, running.job, 5_000)
    assert running.grown == 5_000 and session.setup_grew(running, 999, 1) is running
    assert session.setup_done(running, 999) is running
    assert session.setup_done(running, running.job) == session.Empty()
    assert session.cancel(running) == session.Empty()
    assert session.failed(running, running.job, api.Cancelled()) == session.Empty()
