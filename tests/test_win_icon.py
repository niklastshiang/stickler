"""The Windows app's icon (SPEC.md, `win-design`: the free-standing GNOME icon; module
`win-package`, scope 7): `win/Stickler/Stickler.ico` as `scripts/win_icon.py` writes it."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("win_icon", ROOT / "scripts" / "win_icon.py")
assert _spec and _spec.loader
win_icon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(win_icon)

ICO = ROOT / "win" / "Stickler" / "Stickler.ico"


def _png(size: int) -> bytes:
    """The start of a PNG of `size` pixels: enough for the packer and `png_size`."""
    return win_icon.PNG + b"\x00\x00\x00\x0dIHDR" + size.to_bytes(4, "big") * 2 + b"\x08\x06"


def test_the_committed_icon_has_a_png_frame_for_every_size_windows_asks_for():
    frames = win_icon.read(ICO.read_bytes())
    assert [w for w, _h, _png in frames] == list(win_icon.SIZES)
    for width, height, png in frames:
        assert width == height == win_icon.png_size(png)[0] == win_icon.png_size(png)[1]
    assert {16, 24, 32, 48, 256} <= set(win_icon.SIZES)  # win-design's list


def test_packing_writes_256_as_zero_and_reads_back_in_order():
    data = win_icon.pack([(256, _png(256)), (16, _png(16))])
    assert data[:6] == b"\x00\x00\x01\x00\x02\x00"
    assert data[6] == 16 and data[6 + 16] == 0  # 256 is written as 0
    assert [(w, h) for w, h, _png in win_icon.read(data)] == [(16, 16), (256, 256)]


def test_a_frame_that_is_no_png_or_too_large_is_refused():
    with pytest.raises(ValueError):
        win_icon.pack([(16, b"BM...")])
    with pytest.raises(ValueError):
        win_icon.pack([(512, _png(512))])
    with pytest.raises(ValueError):
        win_icon.read(b"\x00\x00\x02\x00\x00\x00")  # a cursor file
    with pytest.raises(ValueError):
        win_icon.png_size(b"GIF89a")


def test_the_app_the_window_and_the_installer_use_it():
    project = (ROOT / "win" / "Stickler" / "Stickler.csproj").read_text(encoding="utf-8")
    assert "<ApplicationIcon>Stickler.ico</ApplicationIcon>" in project
    assert re.search(r'Content Include="Stickler\.ico"', project)
    assert "Stickler.ico" in (ROOT / "win" / "Stickler" / "App.xaml.cs").read_text(encoding="utf-8")
