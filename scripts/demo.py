"""Records the README's animated overview: the app opens a song, analyses it and follows the
sheet music through the song, captured frame by frame and turned into a GIF.

Run through `scripts/gtk.sh demo <song> [out.gif]`, which starts it on an invisible screen of its
own with private settings, cache and recent songs (the user's real ones are never touched). The
analysis is real (the checkout's models, Fast mode); its frames are kept at a lower rate, so it
plays faster than it ran. Playback is shown by stepping the position, not by playing sound.

For the website (SPEC.md "Website"): `--dark` records the app's dark style, `--video DIR` writes
the overview as a muted MP4, `--stills DIR` the sheet with a marked bar and the corrections
sidebar as PNG and WebP, `--no-gif` leaves the README's GIF alone. Dark files end in `-dark`.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

SIZE = (1000, 700)  # as the screenshots in docs/screenshots
FPS = 10
WIDTH = 800  # of the GIF
README_GIF = Path(__file__).resolve().parents[1] / "docs" / "screenshots" / "overview.gif"
STILL_AT = 8.0  # seconds into the song: the bar marked on the sheet still
NARROW = (400, 760)  # a phone-sized window for the narrow still


class Options(NamedTuple):
    song: Path
    gif: Path | None
    dark: bool
    video: Path | None
    stills: Path | None


class Names(NamedTuple):
    overview: str
    sheet: str
    corrections: str
    empty: str
    analysing: str
    narrow: str


def parse(argv: list[str]) -> Options:
    parser = argparse.ArgumentParser(prog="scripts/gtk.sh demo")
    parser.add_argument("song", type=Path)
    parser.add_argument("gif", type=Path, nargs="?", default=README_GIF)
    parser.add_argument("--no-gif", action="store_true", help="leave the README's GIF alone")
    parser.add_argument("--dark", action="store_true", help="the app's dark style")
    parser.add_argument("--video", type=Path, help="write the overview as MP4 into this folder")
    parser.add_argument("--stills", type=Path, help="write the sheet and corrections here")
    args = parser.parse_args(argv)
    return Options(
        song=args.song.resolve(),
        gif=None if args.no_gif else args.gif.resolve(),
        dark=args.dark,
        video=args.video,
        stills=args.stills,
    )


def names(*, dark: bool) -> Names:
    suffix = "-dark" if dark else ""
    return Names(*(name + suffix for name in Names._fields))


def video_command(frames: Path, out: Path) -> list[str]:
    """The overview without sound, even sides as yuv420p needs. `.webm` is AV1, for browsers
    without H.264 (open-source Chromium, some Linux Firefox builds); `.mp4` is H.264 with its
    index first (so it starts before it is loaded), for Safari and the rest."""
    codec = (
        ["-c:v", "libsvtav1", "-preset", "6", "-crf", "40"]
        if out.suffix == ".webm"
        else ["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-movflags", "+faststart"]
    )
    return (
        ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS)]
        + ["-i", str(frames / "frame%05d.png"), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        + codec
        + ["-pix_fmt", "yuv420p", "-an", str(out)]
    )


def webp_command(png: Path) -> list[str]:
    return ["ffmpeg", "-v", "error", "-y", "-i", str(png)] + [
        "-c:v",
        "libwebp",
        "-quality",
        "85",
        str(png.with_suffix(".webp")),
    ]


def _gtk():
    """GTK's modules, loaded on first use (versions fixed before the first import)."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Graphene", "1.0")
    from gi.repository import GLib, Graphene, Gtk

    return GLib, Graphene, Gtk


def _pump(seconds: float) -> None:
    """Runs the main loop for `seconds`, so the window draws and the worker reports."""
    GLib, _, _ = _gtk()
    context, end = GLib.MainContext.default(), time.monotonic() + seconds
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.005)


class Recorder:
    def __init__(self, window, folder: Path) -> None:
        self.window, self.folder, self.count = window, folder, 0

    def frame(self) -> None:
        _, Graphene, Gtk = _gtk()
        w, h = self.window.get_width(), self.window.get_height()
        snapshot = Gtk.Snapshot.new()
        Gtk.WidgetPaintable.new(self.window).snapshot(snapshot, w, h)
        node = snapshot.to_node()
        if node is None:
            return
        rect = Graphene.Rect().init(0, 0, w, h)
        texture = self.window.get_renderer().render_texture(node, rect)
        texture.save_to_png(str(self.folder / f"frame{self.count:05d}.png"))
        self.count += 1

    def still(self, path: Path) -> None:
        """The window as it is now, as a PNG and a WebP next to it."""
        self.frame()
        # move, not rename: the frames' temporary folder may be on another file system
        shutil.move(self.folder / f"frame{self.count - 1:05d}.png", path)
        self.count -= 1
        _run(webp_command(path))

    def hold(self, seconds: float) -> None:
        for _ in range(round(seconds * FPS)):
            _pump(1 / FPS)
            self.frame()


def record(options: Options) -> None:
    from stickler_app import session
    from stickler_gtk.ui import menu
    from stickler_gtk.ui.window import Window

    menu.apply_appearance("dark" if options.dark else "light")
    window = Window()
    window.set_default_size(*SIZE)
    window.present()
    _pump(1.0)
    with tempfile.TemporaryDirectory() as tmp:
        rec = Recorder(window, Path(tmp))
        named = names(dark=options.dark)
        stills = options.stills
        if stills is not None:
            stills.mkdir(parents=True, exist_ok=True)
            rec.still(stills / f"{named.empty}.png")
        rec.hold(1.5)  # the empty window: "Drop a Song Here"
        window.open_song(options.song)
        started, analysing = time.monotonic(), stills is None
        while not isinstance(window.state, session.Result):
            if time.monotonic() - started > 600:
                sys.exit(f"no result after 10 minutes (state: {type(window.state).__name__})")
            if not isinstance(window.state, session.Analysing):
                sys.exit(f"the analysis did not run: {type(window.state).__name__}")
            _pump(0.4)  # the analysis' frames at a quarter of the rate: it plays faster
            if not analysing and any(s.state == "done" for s in window.state.steps):
                rec.still(stills / f"{named.analysing}.png")  # the first step done
                analysing = True
            rec.frame()
        rec.hold(1.5)  # the sheet music
        for k in range(round(6 * FPS)):  # 12 s of the song in 6 s
            window.playbar.seek(k * 2 / FPS)
            _pump(1 / FPS)
            rec.frame()
        rec.hold(1.0)
        if options.gif is not None:
            _gif(Path(tmp), options.gif)
        if options.video is not None:
            options.video.mkdir(parents=True, exist_ok=True)
            for kind in ("webm", "mp4"):
                _run(video_command(Path(tmp), options.video / f"{named.overview}.{kind}"))
        if stills is not None:
            window.playbar.seek(STILL_AT)  # marks the bar under it
            _pump(0.5)
            rec.still(stills / f"{named.sheet}.png")
            window.set_corrections_open(True)
            _pump(1.0)
            rec.still(stills / f"{named.corrections}.png")
            window.set_corrections_open(False)
            window.set_default_size(*NARROW)
            _pump(1.5)
            rec.still(stills / f"{named.narrow}.png")
    print(f"{rec.count} frames recorded")


def _run(command: list[str]) -> None:
    if shutil.which(command[0]) is None:
        sys.exit(f"{command[0]} is needed")
    subprocess.run(command, check=True)


def _gif(frames: Path, out: Path) -> None:
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg is needed to make the GIF")
    out.parent.mkdir(parents=True, exist_ok=True)
    graph = (
        f"scale={WIDTH}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS)]
        + ["-i", str(frames / "frame%05d.png"), "-vf", graph, "-loop", "0", str(out)],
        check=True,
    )


if __name__ == "__main__":
    record(parse(sys.argv[1:]))
