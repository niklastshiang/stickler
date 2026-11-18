"""scripts/demo.py's options: the README's GIF as before, and for the website the dark style,
the video and the stills (SPEC.md "Website", task 119)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("demo", ROOT / "scripts" / "demo.py")
assert _spec and _spec.loader
demo = importlib.util.module_from_spec(_spec)
sys.modules["demo"] = demo
_spec.loader.exec_module(demo)


def test_the_old_call_still_records_the_readme_gif():
    options = demo.parse(["song.mp3"])
    assert options.song == Path("song.mp3").resolve()
    assert options.gif == (ROOT / "docs" / "screenshots" / "overview.gif")
    assert not options.dark and options.video is None and options.stills is None
    assert demo.parse(["song.mp3", "out.gif"]).gif == Path("out.gif").resolve()


def test_the_website_takes_the_dark_style_a_video_and_stills_without_a_gif(tmp_path):
    options = demo.parse(
        ["song.mp3", "--dark", "--no-gif", "--video", str(tmp_path), "--stills", str(tmp_path)]
    )
    assert options.dark and options.gif is None
    assert options.video == options.stills == tmp_path


def test_each_scheme_has_its_own_file_names(tmp_path):
    assert demo.names(dark=False) == demo.Names("overview", "sheet", "corrections")
    assert demo.names(dark=True) == demo.Names("overview-dark", "sheet-dark", "corrections-dark")


def test_the_video_is_h264_without_sound_and_starts_at_once(tmp_path):
    command = demo.video_command(tmp_path, tmp_path / "overview.mp4")
    assert command[0] == "ffmpeg"
    joined = " ".join(command)
    for part in ("-c:v libx264", "-pix_fmt yuv420p", "-an", "-movflags +faststart"):
        assert part in joined
    assert command[-1] == str(tmp_path / "overview.mp4")


def test_a_picture_becomes_webp(tmp_path):
    command = demo.webp_command(tmp_path / "sheet.png")
    assert "-c:v" in command and "libwebp" in command
    assert command[-1] == str(tmp_path / "sheet.webp")
