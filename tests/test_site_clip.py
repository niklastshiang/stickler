"""scripts/site_clip.py: the website's example as the app plays it with "Both" (SPEC.md
"Website"): the song a little down, a click on every detected hit."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("site_clip", ROOT / "scripts" / "site_clip.py")
assert _spec and _spec.loader
site_clip = importlib.util.module_from_spec(_spec)
sys.modules["site_clip"] = site_clip
_spec.loader.exec_module(site_clip)


def test_the_clip_mixes_song_and_clicks_at_the_apps_volumes(tmp_path):
    from stickler_app import settings

    command = site_clip.mix_command(tmp_path / "s.mp3", tmp_path / "c.wav", tmp_path / "x.ogg")
    joined = " ".join(command)
    assert f"volume={settings.Settings.song_volume}" in joined
    assert f"volume={settings.Settings.hits_volume}" in joined
    assert "amix=inputs=2:normalize=0" in joined
    assert f"-t {site_clip.SECONDS}" in joined and "afade=t=out" in joined
    assert "-c:a libopus" in joined and command[-1] == str(tmp_path / "x.ogg")


def test_mp3_for_browsers_without_opus(tmp_path):
    joined = " ".join(site_clip.mix_command(tmp_path / "s", tmp_path / "c", tmp_path / "x.mp3"))
    assert "-c:a libmp3lame" in joined
