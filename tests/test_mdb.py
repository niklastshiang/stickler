"""Tests for the MDB Drums loader. A local fake repo replaces GitHub (no network needed)."""

import subprocess
from pathlib import Path

import pytest

from stickler.datasets import mdb

ROOT = "MDB Drums"


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "remote"
    files = {
        f"{ROOT}/annotations/subclass/MusicDelta_Rock_subclass.txt": (
            "0.000000 \t KD \n0.020000 \t CHH \n0.528254 \t SD \n0.6 \t SST \n0.7 \t TMB \n"
        ),
        f"{ROOT}/annotations/subclass/MusicDelta_Punk_subclass.txt": "1.0 \t RDC \n",
        f"{ROOT}/audio/full_mix/MusicDelta_Rock_MIX.wav": "mix",
        f"{ROOT}/audio/drum_only/MusicDelta_Rock_Drum.wav": "drums",
        f"{ROOT}/audio/full_mix/MusicDelta_Punk_MIX.wav": "mix",
        f"{ROOT}/audio/drum_only/MusicDelta_Punk_Drum.wav": "drums",
        f"{ROOT}/audio/multi-tracks/MusicDelta_Rock/RAW/big.wav": "do not download",
        "README.md": "readme",
    }
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git("init", "-q", "-b", "master", cwd=repo)
    git("add", "-A", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init", cwd=repo)
    return repo


def test_fetch_checks_out_only_needed_folders(fake_repo, tmp_path):
    target = tmp_path / "data" / "mdb"
    assert mdb.fetch(target, repo_url=str(fake_repo)) == 2
    assert (target / ROOT / "audio" / "full_mix" / "MusicDelta_Rock_MIX.wav").exists()
    assert not (target / ROOT / "audio" / "multi-tracks").exists()


def test_fetch_is_idempotent(fake_repo, tmp_path):
    target = tmp_path / "mdb"
    mdb.fetch(target, repo_url=str(fake_repo))
    assert mdb.fetch(target, repo_url="/gibt/es/nicht") == 2  # no second clone


def test_fetch_failure_raises(tmp_path):
    with pytest.raises(RuntimeError, match="MDB"):
        mdb.fetch(tmp_path / "mdb", repo_url=str(tmp_path / "fehlt"))


def test_tracks_are_listed_sorted_with_paths(fake_repo, tmp_path):
    target = tmp_path / "mdb"
    mdb.fetch(target, repo_url=str(fake_repo))
    tracks = mdb.tracks(target)
    assert [t.id for t in tracks] == ["MusicDelta_Punk", "MusicDelta_Rock"]
    assert tracks[1].mix.name == "MusicDelta_Rock_MIX.wav"
    assert tracks[1].drums.name == "MusicDelta_Rock_Drum.wav"


def test_reference_maps_subclasses_to_gm(fake_repo, tmp_path):
    target = tmp_path / "mdb"
    mdb.fetch(target, repo_url=str(fake_repo))
    rock = mdb.tracks(target)[1]
    # TMB (tambourine) has no class in the scheme → GM 54, ignored later during mapping
    assert rock.reference_notes() == [(0.0, 36), (0.02, 42), (0.528254, 38), (0.6, 37), (0.7, 54)]


def test_unknown_subclass_is_an_error(tmp_path):
    ann = tmp_path / "x_subclass.txt"
    ann.write_text("0.1 \t XYZ \n", encoding="utf-8")
    with pytest.raises(ValueError, match="XYZ"):
        mdb.read_subclass_file(ann)


def test_tracks_on_missing_dataset_is_empty(tmp_path):
    assert mdb.tracks(tmp_path / "leer") == []
