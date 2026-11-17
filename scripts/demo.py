"""Records the README's animated overview: the app opens a song, analyses it and follows the
sheet music through the song, captured frame by frame and turned into a GIF.

Run through `scripts/gtk.sh demo <song> [out.gif]`, which starts it on an invisible screen of its
own with private settings, cache and recent songs (the user's real ones are never touched). The
analysis is real (the checkout's models, Fast mode); its frames are kept at a lower rate, so it
plays faster than it ran. Playback is shown by stepping the position, not by playing sound.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SIZE = (1000, 700)  # as the screenshots in docs/screenshots
FPS = 10
WIDTH = 800  # of the GIF


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

    def hold(self, seconds: float) -> None:
        for _ in range(round(seconds * FPS)):
            _pump(1 / FPS)
            self.frame()


def record(song: Path, out: Path) -> None:
    from stickler_app import session
    from stickler_gtk.ui.window import Window

    window = Window()
    window.set_default_size(*SIZE)
    window.present()
    _pump(1.0)
    with tempfile.TemporaryDirectory() as tmp:
        rec = Recorder(window, Path(tmp))
        rec.hold(1.5)  # the empty window: "Drop a Song Here"
        window.open_song(song)
        started = time.monotonic()
        while not isinstance(window.state, session.Result):
            if time.monotonic() - started > 600:
                sys.exit(f"no result after 10 minutes (state: {type(window.state).__name__})")
            if not isinstance(window.state, session.Analysing):
                sys.exit(f"the analysis did not run: {type(window.state).__name__}")
            _pump(0.4)  # the analysis' frames at a quarter of the rate: it plays faster
            rec.frame()
        rec.hold(1.5)  # the sheet music
        for k in range(round(6 * FPS)):  # 12 s of the song in 6 s
            window.playbar.seek(k * 2 / FPS)
            _pump(1 / FPS)
            rec.frame()
        rec.hold(1.0)
        _gif(Path(tmp), out)
    print(f"{rec.count} frames → {out}")


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
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: scripts/gtk.sh demo <song> [out.gif]")
    target = Path(sys.argv[2]) if len(sys.argv) == 3 else Path("docs/screenshots/overview.gif")
    record(Path(sys.argv[1]).resolve(), target.resolve())
