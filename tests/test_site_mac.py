"""The Mac app's pictures for the website (SPEC.md "Website", "Change 2026-11-25"): the fixtures
scripts/site_mac.py recorded from the example song's real analysis, which the `mac` workflow
draws its window from."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("site_mac", ROOT / "scripts" / "site_mac.py")
assert _spec and _spec.loader
site_mac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site_mac)

PAGES = json.loads(site_mac.PAGES.read_text(encoding="utf-8"))
RESULT = json.loads(site_mac.RESULT.read_text(encoding="utf-8"))


def test_the_sheet_is_the_cores_pages_reply_at_the_windows_width():
    known = json.loads((site_mac.FIXTURES / "pages.json").read_text(encoding="utf-8"))
    assert PAGES.keys() == known.keys()
    assert PAGES["ok"] is True
    assert site_mac.SHEET_WIDTH == 976  # 1000 points less the desk's 12 on each side
    for page in PAGES["pages"]:
        assert page.keys() == known["pages"][0].keys()
        assert float(page["width"]) == site_mac.SHEET_WIDTH
        assert page["svg"].startswith("<svg")


def test_every_played_bar_is_written_on_the_sheet():
    written = {bar["bar"] for page in PAGES["pages"] for bar in page["bars"]}
    assert min(written) == 1  # numbers may skip: a rest of several bars is one written bar
    played = RESULT["bars"]
    assert {bar["bar"] for bar in played} <= written
    assert played[-1]["label"] == f"Bar {len(played)} of {len(played)}"
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(played, played[1:], strict=False))


def test_the_result_is_the_example_song_in_a_mac_users_folder():
    assert RESULT["kind"] == "result"
    assert RESULT["title"] == "Eyesplit"
    assert RESULT["artist"] == "Shane Ivers"
    assert RESULT["subtitle"] == f"Shane Ivers · ♩ = {RESULT['tempo']} · 4/4"
    assert RESULT["song"] == "/Users/me/Music/Eyesplit.mp3"
    assert RESULT["can_export"] and RESULT["clicks"]


def test_the_fixtures_name_no_folder_of_the_computer_they_were_made_on():
    for path in (site_mac.PAGES, site_mac.RESULT):
        text = path.read_text(encoding="utf-8")
        for local in ("/home/", "/var/", "/tmp/", str(Path.home())):
            assert local not in text, f"{path.name} names {local}"


def _png(path: Path, width: int, height: int) -> None:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\0" + b"\0" * 3 * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def test_a_pngs_size_is_read_from_its_header(tmp_path):
    _png(tmp_path / "a.png", 12, 7)
    assert site_mac.png_size(tmp_path / "a.png") == (12, 7)
    (tmp_path / "b.png").write_bytes(b"GIF89a" + b"\0" * 30)
    with pytest.raises(ValueError, match="not a PNG"):
        site_mac.png_size(tmp_path / "b.png")


def test_the_artifacts_pictures_become_the_sites_light_and_dark_pairs(tmp_path):
    artifact, images = tmp_path / "artifact", tmp_path / "images"
    artifact.mkdir()
    for name in site_mac.SHOTS:
        for look in ("light", "dark"):
            _png(artifact / f"site-{name}-{look}.png", 1000, 700)
    _png(artifact / "M6-sheet-light.png", 900, 672)  # the design screens stay out
    taken = site_mac.take(artifact, images)
    assert sorted(p.name for p in taken) == sorted(
        f"mac-{name}{dark}.png" for name in site_mac.SHOTS for dark in ("", "-dark")
    )
    assert sorted(p.name for p in images.iterdir()) == sorted(p.name for p in taken)


def test_a_missing_or_wrongly_sized_picture_stops_the_fetch(tmp_path):
    for name in site_mac.SHOTS:
        for look in ("light", "dark"):
            _png(tmp_path / f"site-{name}-{look}.png", 1000, 700)
    _png(tmp_path / "site-sheet-dark.png", 1000, 677)  # shortened to fit above a Dock
    with pytest.raises(ValueError, match="site-sheet-dark.png"):
        site_mac.take(tmp_path, tmp_path / "images")
    (tmp_path / "site-empty-light.png").unlink()
    with pytest.raises(FileNotFoundError, match="site-empty-light.png"):
        site_mac.take(tmp_path, tmp_path / "images")


def test_only_a_run_number_is_fetched():
    assert site_mac.main(["fetch", "--repo=elsewhere"]) == 2
    assert site_mac.main([]) == 2
