"""The window's flows without a window (SPEC.md, module `core-bridge`): one controller owns the
current `session.State`, runs long work in a thread and reports every change to its host.

The host passes `post`, which the controller calls with each `Event` in the order the changes
happen, from whichever thread made them; `post` must not block (GTK: `GLib.idle_add`, the
bridge: a queue its writer drains). The flows are the GTK window's of release 7, copied, not
redesigned: one job at a time, a new song cancels the running job, a correction waits for the
changes to pause."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stickler import api
from stickler_app import analysis, corrections, paths, recent, session
from stickler_app.i18n import _

CORRECT_AFTER = 0.25  # seconds a correction waits for the changes to pause
BUSY = session.Analysing | session.Exporting | session.SettingUp


@dataclass(frozen=True)
class Changed:
    """The state the window shows now."""

    state: session.State


@dataclass(frozen=True)
class RecentChanged:
    """The recent songs changed (newest first)."""

    songs: tuple[recent.Recent, ...]


@dataclass(frozen=True)
class Notice:
    """A short message for the reader (a toast in GTK); the state stays as it is."""

    text: str


Event = Changed | RecentChanged | Notice


class Controller:
    def __init__(self, post: Callable[[Event], Any]) -> None:
        self._post = post
        self._lock = threading.RLock()
        self._state: session.State = session.Empty()
        self._recent_store = recent.store_path()
        self._recent = recent.load(self._recent_store)
        self._token: api.CancelToken | None = None
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None  # a correction waiting for a pause

    @property
    def state(self) -> session.State:
        with self._lock:
            return self._state

    @property
    def recent(self) -> tuple[recent.Recent, ...]:
        with self._lock:
            return tuple(self._recent)

    # what the reader does

    def open(self, song: Path) -> None:
        """Analyses `song` with its stored corrections; a running job is cancelled."""
        with self._lock:
            self._start(session.open_song(song, self._state, self._stored(song)))

    def retry(self) -> bool:
        """Analyses a failed song again; False when the state has nothing to retry."""
        with self._lock:
            state = self._state
            if not (isinstance(state, session.Failed) and state.can_retry):
                return False
            self._start(session.open_song(state.song, state.previous, self._stored(state.song)))
            return True

    def cancel(self) -> bool:
        """Stops the running job and goes back to where it started; False when nothing runs."""
        with self._lock:
            if not isinstance(self._state, BUSY):
                return False
            self._stop_job()
            self._set(session.cancel(self._state))
            return True

    def close(self) -> None:
        """Back to the empty window; a running job is cancelled."""
        with self._lock:
            self._stop_job()
            self._set(session.Empty())

    def forget_recent(self, song: Path) -> None:
        with self._lock:
            self._set_recent(recent.remove(self._recent, song))

    def correct(self, fix: api.Corrections) -> bool:
        """A change of the beat: shown at once (`Result.wanted`), notated once the changes
        pause, so a few quick changes make one run; the newest wins and is stored for the
        song. False without a result."""
        with self._lock:
            if not isinstance(self._state, session.Result):
                return False
            self._set(session.correct(self._state, fix))
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(CORRECT_AFTER, self._start_correction)
            self._timer.daemon = True
            self._timer.start()
            return True

    def shutdown(self, seconds: float = 2.0) -> None:
        """Cancels the running job and waits until it has cleaned up (its half-written cache
        folder removed), at most `seconds`, so that quitting leaves nothing behind."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._stop_job()
            thread = self._thread
        if thread is not None:
            thread.join(seconds)

    # the flows

    @staticmethod
    def _stored(song: Path) -> api.Corrections:
        """The song's remembered corrections (SPEC.md, module `corrections`)."""
        stored = corrections.load(corrections.store_path())
        return stored.get(song.absolute(), corrections.DETECTED)

    def _start(self, state: session.Analysing) -> None:
        self._stop_job()
        self._token = token = api.CancelToken()
        job, song = state.job, state.song
        self._set(state)

        def report(step: api.Step) -> None:
            with self._lock:
                self._set(session.on_step(self._state, job, step))

        def done(finished: tuple[api.SongInfo, api.Notation]) -> None:
            info, notation = finished
            state = session.finished(self._state, job, info, notation)
            if isinstance(state, session.Result):
                entry = recent.opened_now(state.song, info.title, info.artist)
                self._set_recent(recent.add(self._recent, entry))
            self._set(state)

        self._run(
            lambda: analysis.analyse(
                song,
                paths.score_path(song),
                report,
                token,
                paths.hits_path(song),
                state.corrections,
            ),
            done,
            lambda exc: self._set(session.failed(self._state, job, exc)),
        )

    def _start_correction(self) -> None:
        with self._lock:
            self._timer = None
            result = self._state
            if not isinstance(result, session.Result) or result.pending is None:
                return
            job, fix, song = result.pending.job, result.pending.corrections, result.song
            self._stop_job()
            self._token = token = api.CancelToken()

            def done(finished: tuple[api.SongInfo, api.Notation]) -> None:
                state = session.corrected(self._state, job, finished[1])
                if state is not self._state:
                    self._set(state)
                    self._remember(song, fix)

            def failed(exc: BaseException) -> None:
                state = session.correction_failed(self._state, job)
                if state is not self._state:
                    self._set(state)
                    self._notice(_("The correction did not work: {reason}").format(reason=exc))

            self._run(
                lambda: analysis.analyse(
                    song, paths.score_path(song), lambda _step: None, token, corrections=fix
                ),
                done,
                failed,
            )

    def _remember(self, song: Path, fix: api.Corrections) -> None:
        try:
            corrections.remember(corrections.store_path(), song.absolute(), fix)
        except OSError as exc:  # the correction still shows for this session
            self._notice(
                _("The correction could not be saved: {reason}").format(reason=exc.strerror)
            )

    def _set_recent(self, songs: list[recent.Recent]) -> None:
        self._recent = songs
        try:
            recent.save(self._recent_store, songs)
        except OSError as exc:  # the list still works for this session
            self._notice(_("Recent songs could not be saved: {reason}").format(reason=exc.strerror))
        self._post(RecentChanged(tuple(songs)))

    # plumbing; every change happens under the lock, so events reach `post` in order

    def _set(self, state: session.State) -> None:
        if state is not self._state:
            self._state = state
            self._post(Changed(state))

    def _notice(self, text: str) -> None:
        self._post(Notice(text))

    def _stop_job(self) -> None:
        if self._token is not None:
            self._token.cancel()  # the job ends the model's processes within a second
            self._token = None

    def _run(
        self,
        job: Callable[[], Any],
        done: Callable[[Any], None],
        failed: Callable[[BaseException], None],
    ) -> None:
        """Runs `job` in a daemon thread; its value or exception is handled under the lock."""

        def work() -> None:
            try:
                value = job()
            except Exception as exc:  # becomes a state or a notice, as in the window
                with self._lock:
                    failed(exc)
                return
            with self._lock:
                done(value)

        self._thread = threading.Thread(target=work, name="stickler-job", daemon=True)
        self._thread.start()
