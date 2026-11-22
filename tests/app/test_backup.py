"""Back Up… and Restore Backup… without GTK (SPEC.md "Release 10 (proposed): keep and remove",
scope A): one zip with the settings, the recent songs, the corrections and the models' results,
restored into any package's folders."""

import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

import stickler
from stickler import api
from stickler_app import backup, corrections, paths, recent, settings

ROOT = Path(__file__).resolve().parents[2]


def _linux(home: Path) -> dict[str, str]:
    return {"HOME": str(home), "APPIMAGE": "/x/Stickler.AppImage", "SHARUN_DIR": "/tmp/.mount_x"}


def _mac(home: Path) -> dict[str, str]:
    return {"HOME": str(home), "STICKLER_PACKAGED": "macos"}


def _analysed(env, digest_folder: str, adapter: str = "adtof", size: int = 10) -> Path:
    folder = paths.results_cache(env) / adapter / digest_folder
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text("{}")
    (folder / "drums.mid").write_bytes(b"x" * size)
    return folder


def _filled(env) -> None:
    settings.save(settings.store_path(env), settings.Settings(song_volume=0.5, setup_agreed=True))
    song = recent.Recent(Path("/music/eye.flac"), "Eye", "Survivor", date(2026, 11, 20), "abc")
    recent.save(recent.store_path(env), [song])
    corrections.remember(
        corrections.store_path(env), Path("/music/eye.flac"), api.Corrections(tempo="half"), "abc"
    )
    _analysed(env, "k1")
    _analysed(env, "k1", adapter="beat_this")
    _analysed(env, "k2", adapter="demucs", size=1000)  # a separated drum track: left out


def test_a_backup_holds_settings_songs_corrections_and_results_but_no_separated_tracks(tmp_path):
    env = _linux(tmp_path / "home")
    _filled(env)
    made = backup.write(tmp_path / "b.zip", env, today=date(2026, 11, 22))
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        names = set(z.namelist())
        meta = json.loads(z.read("backup.json"))
    assert {"backup.json", "settings.json", "recent.json", "corrections.json"} <= names
    assert "results/adtof/k1/drums.mid" in names and "results/beat_this/k1/meta.json" in names
    assert not any(n.startswith("results/demucs/") for n in names)
    assert meta["format"] == backup.FORMAT and meta["created"] == "2026-11-22"
    assert meta["system"] == "appimage" and meta["app"] == stickler.__version__
    assert made == backup.Summary(date(2026, 11, 22), songs=1, size=made.size)


def test_the_name_says_what_and_when():
    assert backup.file_name(date(2026, 11, 22)) == "Stickler Backup 2026-11-22.zip"


def test_a_backup_restores_into_the_macs_folders_and_the_song_is_found_by_content(tmp_path):
    linux = _linux(tmp_path / "linux")
    _filled(linux)
    backup.write(tmp_path / "b.zip", linux, today=date(2026, 11, 22))
    mac = _mac(tmp_path / "mac")

    summary = backup.read(tmp_path / "b.zip")
    assert summary.songs == 1 and summary.created == date(2026, 11, 22)
    backup.restore(tmp_path / "b.zip", mac)

    assert (paths.results_cache(mac) / "adtof" / "k1" / "drums.mid").is_file()
    restored = settings.load(settings.store_path(mac))
    assert restored.song_volume == 0.5
    # the consent to download the models is this computer's, never the backup's
    assert restored.setup_agreed is False
    assert [r.digest for r in recent.load(recent.store_path(mac))] == ["abc"]
    # on the Mac the song lies elsewhere: found by its content
    moved = Path("/Users/me/Music/eye.flac")
    store = corrections.store_path(mac)
    assert corrections.lookup(store, moved, "abc") == api.Corrections(tempo="half")


def test_a_restore_adds_what_is_missing_and_keeps_what_is_here(tmp_path):
    old = _linux(tmp_path / "old")
    _filled(old)
    backup.write(tmp_path / "b.zip", old, today=date(2026, 11, 22))
    here = _linux(tmp_path / "here")
    mine = recent.Recent(Path("/m/mine.flac"), "Mine", "", date(2026, 11, 21), "zzz")
    recent.save(recent.store_path(here), [mine])
    corrections.remember(
        corrections.store_path(here),
        Path("/music/eye.flac"),
        api.Corrections(tempo="double"),
        "abc",
    )
    kept = _analysed(here, "k1")
    (kept / "drums.mid").write_bytes(b"mine")

    backup.restore(tmp_path / "b.zip", here)

    assert [r.path for r in recent.load(recent.store_path(here))] == [
        Path("/m/mine.flac"),
        Path("/music/eye.flac"),
    ]
    stored = corrections.load(corrections.store_path(here))
    assert stored == {Path("/music/eye.flac"): api.Corrections(tempo="double")}  # here's stays
    assert (kept / "drums.mid").read_bytes() == b"mine"
    assert (paths.results_cache(here) / "beat_this" / "k1" / "meta.json").is_file()


@pytest.mark.parametrize(
    "made",
    [
        "not a zip at all",
        "a zip without backup.json",
        "a newer format",
        "a path outside",
    ],
)
def test_a_broken_foreign_or_newer_file_is_refused_and_changes_nothing(tmp_path, made):
    bad = tmp_path / "bad.zip"
    if made == "not a zip at all":
        bad.write_text("hello")
    else:
        with zipfile.ZipFile(bad, "w") as z:
            if made != "a zip without backup.json":
                fmt = backup.FORMAT + 1 if made == "a newer format" else backup.FORMAT
                z.writestr("backup.json", json.dumps({"format": fmt, "created": "2026-11-22"}))
            if made == "a path outside":
                z.writestr("../../evil.txt", "x")
    env = _linux(tmp_path / "home")
    with pytest.raises(backup.NotABackup):
        backup.read(bad)
    with pytest.raises(backup.NotABackup):
        backup.restore(bad, env)
    assert not (tmp_path / "home").exists()
    assert not (tmp_path / "evil.txt").exists()


def test_the_left_out_results_are_the_repositorys_separators():
    on_disk = {p.name for p in (ROOT / "adapters" / "separators").iterdir() if p.is_dir()}
    assert set(backup.SEPARATORS) == on_disk
