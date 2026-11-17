"""Export of MusicXML and the drum track (design screen 8), without GTK."""

from pathlib import Path

import pytest

from stickler import api
from stickler_app import exports, paths, session, steps


def _result(title="Eye of the Tiger", seconds=246.0):
    state = session.open_song(Path("/music/eye.flac"), session.Empty())
    t = api.SongTranscription(Path("/music/eye.flac"), "fast", None, [], [], [])
    notation = api.Notation(Path("/cache/eye.musicxml"), None, None, t, [], 109, (4, 4))
    return session.finished(state, state.job, api.SongInfo(title, "Survivor", seconds), notation)


def test_the_save_dialog_proposes_the_opened_files_name():
    """Named like the file that was opened, not its tags' title (owner, 2026-11-15)."""
    song = Path("/music/Survivor - Eye of the Tiger.flac")
    assert exports.musicxml_name(song) == "Survivor - Eye of the Tiger.musicxml"
    assert exports.drum_track_name(song) == "Survivor - Eye of the Tiger (drums).flac"
    assert exports.musicxml_name(Path("AC-DC - T.N.T..mp3")) == "AC-DC - T.N.T..musicxml"


def test_the_drum_track_names_its_cost_before_it_starts():
    ready = exports.drum_track_cost(246.0, download=False)
    assert ready.minutes == 8  # 1.84 × 4:06 ≈ 7.5 minutes on the laptop's CPU
    assert "8 minutes" in ready.text and "GB" not in ready.text
    first = exports.drum_track_cost(246.0, download=True)
    assert "8 minutes" in first.text and "1.2 GB" in first.text
    assert exports.drum_track_cost(10.0, download=False).minutes == 1  # never "0 minutes"


def test_a_musicxml_export_is_a_copy_of_the_apps_file(tmp_path):
    source = tmp_path / "cache" / "eye.musicxml"
    source.parent.mkdir()
    source.write_text("<score/>", encoding="utf-8")
    dest = exports.save_musicxml(source, tmp_path / "out" / "Eye.musicxml")
    assert dest.read_text(encoding="utf-8") == "<score/>"


def test_the_drum_track_job_sets_up_demucs_first_when_needed(monkeypatch, tmp_path):
    calls = []
    stem = tmp_path / "drums.wav"
    folders = []

    def setup_adapters(adapter, **kw):
        folders.append(kw["adapters_root"])
        calls.append(("setup", adapter))
        return [adapter]

    monkeypatch.setattr(api, "setup_adapters", setup_adapters)

    def transcribe(song, **kw):
        folders.append((kw["adapters_root"], kw["cache_dir"]))
        calls.append(("transcribe", kw["drums"]))
        return api.SongTranscription(song, "fast", stem, [], [], [])

    monkeypatch.setattr(api, "transcribe_song", transcribe)
    monkeypatch.setattr(api, "export_drum_track", lambda s, d: calls.append(("export", s)) or d)
    token, dest = api.CancelToken(), tmp_path / "Eye (drums).flac"
    assert exports.drum_track(Path("eye.flac"), dest, print, token, setup=True) == dest
    assert calls == [("setup", api.DRUM_TRACK_SEPARATOR), ("transcribe", True), ("export", stem)]
    assert folders == [paths.adapters_root(), (paths.adapters_root(), paths.results_cache())]
    calls.clear()
    exports.drum_track(Path("eye.flac"), dest, print, token, setup=False)
    assert calls[0] == ("transcribe", True)


def test_a_drum_track_job_without_a_separated_track_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        api,
        "transcribe_song",
        lambda song, **kw: api.SongTranscription(song, "x", None, [], [], []),
    )
    with pytest.raises(RuntimeError, match="drum track"):
        exports.drum_track(Path("eye.flac"), tmp_path / "d.flac", print, api.CancelToken())


def test_exporting_lists_its_steps_and_returns_to_the_result():
    result = _result()
    state = session.export_drums(result, Path("/out/d.flac"), setup=True)
    assert [r.id for r in state.steps] == ["environment:demucs", "weights:demucs", "separate"]
    assert session.export_drums(result, Path("/d.flac"), setup=False).steps[0].id == "separate"
    # reports come with the API's own numbering; the rows follow their ids
    state = session.on_step(state, state.job, api.Step("transcribe", 1, 3, "done", True))
    state = session.on_step(state, state.job, api.Step("separate", 2, 3, "started"))
    assert [r.state for r in state.steps] == ["waiting", "waiting", "running"]
    done = session.exported(state, state.job)
    assert done is result
    assert session.cancel(state) is result
    failed = session.failed(state, state.job, RuntimeError("ffmpeg: disk full"))
    assert isinstance(failed, session.Failed) and failed.previous is result


def test_setup_steps_are_named_for_drummers():
    assert steps.row("environment:demucs").label == "Download the programs for Demucs"
    assert steps.row("weights:demucs").label == "Download the Demucs model"


def test_a_failed_export_says_so_and_does_not_offer_to_analyse_again():
    result = _result()
    state = session.export_drums(result, Path("/out/d.flac"), setup=False)
    failed = session.failed(state, state.job, RuntimeError("ffmpeg: disk full"))
    assert failed.kind == "export" and not failed.can_retry
    assert "eye.flac" in failed.description and failed.details == "ffmpeg: disk full"
    missing = session.failed(state, state.job, api.SetupMissing(["demucs"]))
    assert isinstance(missing, session.Consent) and missing.missing == ("demucs",)


def test_the_pdf_is_named_like_the_opened_file():
    assert exports.pdf_name(Path("/music/Survivor - Eye of the Tiger.flac")) == (
        "Survivor - Eye of the Tiger.pdf"
    )
