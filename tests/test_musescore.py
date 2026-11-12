"""Tests for the optional MuseScore PDF export (subprocess mocked)."""

import subprocess

import pytest

from stickler import musescore


def test_find_prefers_binary_then_flatpak():
    assert musescore.find(
        which=lambda n: "/usr/bin/mscore" if n == "mscore" else None, flatpak_ids=set
    ) == ["/usr/bin/mscore"]
    flat = musescore.find(which=lambda n: None, flatpak_ids=lambda: {musescore.FLATPAK_ID})
    assert flat == ["flatpak", "run", musescore.FLATPAK_ID]
    assert musescore.find(which=lambda n: None, flatpak_ids=set) is None


def test_export_pdf_runs_musescore_with_file_access(tmp_path, monkeypatch):
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        (tmp_path / "out.pdf").write_bytes(b"%PDF")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(musescore.subprocess, "run", fake_run)
    xml = tmp_path / "song.musicxml"
    pdf = musescore.export_pdf(xml, tmp_path / "out.pdf", ["flatpak", "run", musescore.FLATPAK_ID])
    assert pdf == tmp_path / "out.pdf"
    assert seen[0][:3] == ["flatpak", "run", f"--filesystem={tmp_path}"]
    assert seen[0][-3:] == ["-o", str(tmp_path / "out.pdf"), str(xml)]


def test_export_pdf_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(
        musescore.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "kaputt"),
    )
    with pytest.raises(RuntimeError, match="MuseScore"):
        musescore.export_pdf(tmp_path / "a.musicxml", tmp_path / "a.pdf", ["mscore"])
