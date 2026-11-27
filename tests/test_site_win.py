"""The website's Windows pictures (SPEC.md "Website", "Change 2026-11-27"): scripts/site_win.py
takes only a complete set of the right size."""

import importlib.util
import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))  # site_win imports site_mac from its own folder
_spec = importlib.util.spec_from_file_location("site_win", ROOT / "scripts" / "site_win.py")
assert _spec and _spec.loader
site_win = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site_win)
sys.path.remove(str(ROOT / "scripts"))


def _png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b""))


def test_the_eight_pictures_are_named_for_the_site():
    assert site_win.names() == [
        "win-empty.png",
        "win-empty-dark.png",
        "win-analysing.png",
        "win-analysing-dark.png",
        "win-sheet.png",
        "win-sheet-dark.png",
        "win-corrections.png",
        "win-corrections-dark.png",
    ]


def test_a_complete_set_is_copied(tmp_path):
    source, images = tmp_path / "taken", tmp_path / "images"
    source.mkdir()
    for name in site_win.names():
        _png(source / name, 1000, 700)
    taken = site_win.take(source, images)
    assert [p.name for p in taken] == site_win.names()
    assert all(p.is_file() for p in taken)


def test_a_missing_picture_or_a_wrong_size_takes_nothing(tmp_path):
    source, images = tmp_path / "taken", tmp_path / "images"
    source.mkdir()
    for name in site_win.names()[:-1]:
        _png(source / name, 1000, 700)
    with pytest.raises(FileNotFoundError, match="win-corrections-dark.png"):
        site_win.take(source, images)
    _png(source / site_win.names()[-1], 1014, 707)
    with pytest.raises(ValueError, match="1014"):
        site_win.take(source, images)
    assert not images.exists()


def test_without_a_folder_it_explains_itself(capsys):
    assert site_win.main([]) == 2
    assert "site_win.py take" in capsys.readouterr().err
