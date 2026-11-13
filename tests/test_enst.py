"""Tests for the ENST-Drums loader (minus-one tracks with accompaniment)."""

import numpy as np
import pytest

from stickler.audio import load_mono, write_wav
from stickler.datasets import enst

SR = 8000


@pytest.fixture
def root(tmp_path):
    """A fake ENST tree: one minus-one track per drummer 1, one hits track that is ignored."""
    d = tmp_path / "enst" / "drummer_1"
    for sub in ("annotation", "audio/wet_mix", "audio/accompaniment"):
        (d / sub).mkdir(parents=True)
    name = "107_minus-one_salsa_sticks"
    (d / "annotation" / f"{name}.txt").write_text(
        "0.444 cb\n0.446 bd\n0.737 sd-\n1.0 chh\n1.1 rc3\n1.2 lmt\n1.3 cs\n1.4 sweep\n",
        encoding="utf-8",
    )
    (d / "annotation" / "001_hits_snare-drum_sticks_x6.txt").write_text("0.1 sd\n")
    t = np.arange(SR) / SR
    write_wav(d / "audio/wet_mix" / f"{name}.wav", np.stack([0.6 * np.ones_like(t)] * 2, 1), SR)
    write_wav(
        d / "audio/accompaniment" / f"{name}.wav", np.stack([0.3 * np.ones_like(t)] * 2, 1), SR
    )
    return tmp_path / "enst"


def test_labels_map_to_gm_and_unknown_raise(tmp_path):
    ann = tmp_path / "a.txt"
    ann.write_text("0.5 bd\n0.6 cr2\n0.7 ohh\n0.8 sweep\n0.9 mtr\n", encoding="utf-8")
    assert enst.read_annotation(ann) == [(0.5, 36), (0.6, 49), (0.7, 46), (0.9, 48)]
    ann.write_text("0.5 xyz\n", encoding="utf-8")
    with pytest.raises(ValueError, match="xyz"):
        enst.read_annotation(ann)


def test_tracks_need_a_prepared_mix(root):
    assert enst.tracks(root) == []
    assert enst.prepare(root) == 1
    (track,) = enst.tracks(root)
    assert track.id == "d1_107_minus-one_salsa_sticks"
    assert track.drums.name == "107_minus-one_salsa_sticks.wav"
    assert [p for _, p in track.reference_notes()] == [56, 36, 38, 42, 51, 47, 37]
    assert enst.prepare(root) == 1  # idempotent


def test_mix_is_two_thirds_drums_one_third_accompaniment(root):
    enst.prepare(root)
    (track,) = enst.tracks(root)
    mix = load_mono(track.mix, sr=SR)
    assert mix[100:-100].mean() == pytest.approx(2 / 3 * 0.6 + 1 / 3 * 0.3, abs=1e-3)


def test_prepare_without_data_explains_how_to_get_it(tmp_path):
    with pytest.raises(RuntimeError, match="stickler fetch enst"):
        enst.prepare(tmp_path / "missing")


def _archive(tmp_path, root):
    """The fake ENST tree packed like the Zenodo archive (top folder enst_drums_public/)."""
    import hashlib
    import shutil
    import subprocess

    src = tmp_path / "pack" / "enst_drums_public"
    shutil.copytree(root, src)
    (src / "drummer_1" / "video").mkdir()
    (src / "drummer_1" / "video" / "big.mp4").write_bytes(b"not needed")
    archive = tmp_path / "enst.tar.zst"
    subprocess.run(
        ["tar", "--zstd", "-cf", str(archive), "-C", str(tmp_path / "pack"), "enst_drums_public"],
        check=True,
    )
    return archive, hashlib.md5(archive.read_bytes()).hexdigest()


def test_fetch_downloads_checks_and_unpacks_only_what_is_needed(tmp_path, root, monkeypatch):
    archive, md5 = _archive(tmp_path, root)
    monkeypatch.setattr(enst, "MD5", md5)
    calls = []

    def fake_download(url, dest):
        calls.append(url)
        dest.write_bytes(archive.read_bytes())

    monkeypatch.setattr(enst, "_download", fake_download)
    target = tmp_path / "data" / "enst"
    assert enst.fetch(target) == 1
    assert calls == [enst.URL]
    assert not list(target.rglob("*.mp4")) and not list(target.glob("*.tar.zst"))
    (track,) = enst.tracks(target)
    assert track.mix.exists()
    assert enst.fetch(target) == 1 and len(calls) == 1  # already there: no second download


def test_fetch_rejects_a_damaged_download(tmp_path, root, monkeypatch):
    archive, _ = _archive(tmp_path, root)
    monkeypatch.setattr(enst, "MD5", "0" * 32)
    monkeypatch.setattr(enst, "_download", lambda url, dest: dest.write_bytes(archive.read_bytes()))
    with pytest.raises(RuntimeError, match="checksum"):
        enst.fetch(tmp_path / "data" / "enst")
