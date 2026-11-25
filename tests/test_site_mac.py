"""The Mac app's pictures for the website (SPEC.md "Website", "Change 2026-11-25"): the fixtures
scripts/site_mac.py recorded from the example song's real analysis, which the `mac` workflow
draws its window from."""

import importlib.util
import json
from pathlib import Path

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
