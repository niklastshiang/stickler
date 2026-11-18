"""Long work (an analysis, an export) runs in a thread; everything it reports reaches the
widgets on the main loop through GLib.idle_add. Workers never touch a widget."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from gi.repository import GLib


def on_main_loop(fn: Callable[..., Any]) -> Callable[..., None]:
    """A function callable from any thread that runs `fn` on the main loop."""

    def call(*args: Any) -> None:
        def once() -> bool:
            fn(*args)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(once)

    return call


def to_main_loop(fn: Callable[..., Any]) -> Callable[..., None]:
    """As `on_main_loop`, but on the main loop's own thread `fn` runs at once, so a click's
    change is drawn before its handler returns (the controller's `post` for the window)."""
    later = on_main_loop(fn)

    def call(*args: Any) -> None:
        if threading.current_thread() is threading.main_thread():
            fn(*args)
        else:
            later(*args)

    return call


def run(
    job: Callable[[], Any],
    on_done: Callable[[Any], None],
    on_error: Callable[[BaseException], None],
) -> threading.Thread:
    """Runs `job` in a daemon thread; its value or exception goes to the main loop."""
    done, error = on_main_loop(on_done), on_main_loop(on_error)

    def work() -> None:
        try:
            value = job()
        except Exception as exc:  # reported to the window, which shows it
            error(exc)
            return
        done(value)

    thread = threading.Thread(target=work, name="stickler-job", daemon=True)
    thread.start()
    return thread
