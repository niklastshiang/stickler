"""The window's flows without a window (SPEC.md, module `core-bridge`): one controller owns the
current `session.State`, runs long work in a thread and reports every change to its host.

The host passes `post`, which the controller calls with each `Event` in the order the changes
happen, from whichever thread made them; `post` must not block (GTK: at once on the main
thread, else `GLib.idle_add`; the bridge: a queue its writer drains). The flows are the GTK
window's of release 7, copied, not redesigned: one job at a time, a new song cancels the
running job, a correction waits for the changes to pause, the setup's download is measured
twice a second."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stickler import adapters, api
from stickler_app import (
    analysis,
    backup,
    corrections,
    exports,
    paths,
    recent,
    removal,
    session,
    settings,
    setup,
)
from stickler_app.i18n import _

CORRECT_AFTER = 0.25  # seconds a correction waits for the changes to pause
SAMPLE = 0.5  # seconds between two measurements of a download
BUSY = session.BUSY  # kept here for the controller's callers


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
    """A short message for the reader (a toast in GTK); the state stays as it is. `opens`: a
    file just saved, which the host may offer to open."""

    text: str
    opens: Path | None = None


@dataclass(frozen=True)
class DrumTrackCost:
    """What a drum track costs, said before it starts (design screen 8)."""

    minutes: int
    text: str
    download: bool  # Demucs is downloaded first


Event = Changed | RecentChanged | Notice


class Controller:
    def __init__(self, post: Callable[[Event], Any]) -> None:
        self._post = post
        self._lock = threading.RLock()
        self._state: session.State = session.Empty()
        self._recent_store = recent.store_path()
        self._recent = recent.load(self._recent_store)
        self._digests: dict[Path, str] = {}  # each opened song's content (paths.song_digest)
        self._token: api.CancelToken | None = None
        self._threads: set[threading.Thread] = set()  # jobs still running, replaced ones too
        self._closed = False  # after `shutdown` no job starts
        self._timer: threading.Timer | None = None  # a correction waiting for a pause
        self._sampling: threading.Event | None = None  # set to stop measuring a download
        self._grown: Callable[[], int] = lambda: 0  # what the running setup step has added
        self._removing = False  # models being removed

    @property
    def state(self) -> session.State:
        with self._lock:
            return self._state

    @property
    def recent(self) -> tuple[recent.Recent, ...]:
        with self._lock:
            return tuple(self._recent)

    @property
    def removing(self) -> bool:
        """The downloaded models are being removed."""
        with self._lock:
            return self._removing

    @property
    def can_remove_models(self) -> bool:
        """Only an installed app removes its models, and not while something runs."""
        with self._lock:
            return session.abilities(
                self._state, installed=paths.packaged() is not None, removing=self._removing
            ).remove_models

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

    # the setup assistant (SPEC.md, module `setup-assistant`)

    def start(self) -> None:
        """At start, in a thread: are the models there? (a few uv checks, under 0.1 s) A
        packaged app first copies its shipped adapters' sources into its models folder. Leads
        to the consent, the download (agreed before, interrupted) or stays empty."""
        root = paths.adapters_root()

        def check() -> list[str]:
            shipped = paths.adapter_sources()
            if shipped is not None:
                setup.sync_adapters(shipped, root)
            return api.mode_ready(adapters_root=root)

        def checked(missing: list[str]) -> None:
            if not isinstance(self._state, session.Empty):
                return  # the reader has started something meanwhile
            agreed = settings.load(settings.store_path()).setup_agreed
            page = setup.start_page(missing, agreed=agreed)
            if page == "consent":
                self._set(session.consent(tuple(missing)))
            elif page == "download":
                self._start_setup(tuple(missing), None)

        self._run(
            check,
            checked,
            lambda exc: self._notice(_("Could not check the models: {reason}").format(reason=exc)),
            job=False,
        )

    def agree(self) -> bool:
        """The models may be downloaded: remembered, and the download starts."""
        with self._lock:
            state = self._state
            if not isinstance(state, session.Consent):
                return False
            with contextlib.suppress(OSError):  # unsaved, the download still runs now
                settings.update(settings.store_path(), setup_agreed=True)
            self._start_setup(state.missing, state.song)
            return True

    def not_now(self) -> bool:
        """ "Not Now" on the consent, "Later" after a failed download: the empty window."""
        with self._lock:
            if not isinstance(self._state, session.Consent | session.SetupFailed):
                return False
            self._set(session.Empty())
            return True

    def retry_setup(self) -> bool:
        """Goes on from where it failed: steps already done are quick (api.setup_adapters)."""
        with self._lock:
            state = self._state
            if not isinstance(state, session.SetupFailed):
                return False
            self._start_setup(state.missing, state.song)
            return True

    # exports (design screen 8)

    def export_musicxml(self, dest: Path) -> bool:
        """Copies the result's MusicXML to `dest`; False without a result."""
        with self._lock:
            result = self._state
            if not isinstance(result, session.Result) or result.pending is not None:
                return False  # a correction's notes are still being written
            try:
                exports.save_musicxml(result.notation.musicxml, dest)
            except OSError as exc:
                self._notice(_("Could not save: {reason}").format(reason=exc.strerror))
            else:
                self._saved(dest)
            return True

    def drum_track_cost(self) -> DrumTrackCost | None:
        """What saving the drum track would cost now; None without a result."""
        with self._lock:
            result = self._state
            if not isinstance(result, session.Result):
                return None
            download = self._separator_missing()
            cost = exports.drum_track_cost(result.info.seconds, download=download)
            return DrumTrackCost(cost.minutes, cost.text, download)

    def export_drum_track(self, dest: Path) -> bool:
        """Separates the drums (Demucs downloaded first if missing) and saves them at `dest`,
        with steps and Cancel; back to the result after. False without a result."""
        with self._lock:
            result = self._state
            if not isinstance(result, session.Result) or result.pending is not None:
                return False  # the export would cancel the correction and keep it pending
            download = self._separator_missing()
            self._stop_job()
            self._token = token = api.CancelToken()
            state = session.export_drums(result, dest, setup=download)
            job = state.job
            self._set(state)

            def report(step: api.Step) -> None:
                with self._lock:
                    self._set(session.on_step(self._state, job, step))

            def done(saved: Path) -> None:
                state = session.exported(self._state, job)
                if state is not self._state:
                    self._set(state)
                    self._saved(saved)

            self._run(
                lambda: exports.drum_track(result.song, dest, report, token, setup=download),
                done,
                lambda exc: self._set(session.failed(self._state, job, exc)),
            )
            return True

    # removing the downloaded models (SPEC.md, module `polish`)

    @staticmethod
    def removal_sizes() -> tuple[int, int]:
        """Bytes that would go: the models alone, and everything (settings, recent songs and
        corrections too). Walks the folders: call it off the interface's thread."""
        return (
            removal.size(removal.targets(everything=False)),
            removal.size(removal.targets(everything=True)),
        )

    def remove_models(self, everything: bool) -> bool:
        """Removes the models in a thread; the next download is asked for again. With
        `everything`, the settings, recent songs and corrections go too. False when it cannot
        run now (see `can_remove_models`)."""
        with self._lock:
            if not self.can_remove_models:
                return False
            self._stop_job()
            self._removing = True
            self._set(session.Empty())
            chosen = removal.targets(everything=everything)

            def remove() -> None:
                removal.remove(chosen)
                shipped = paths.adapter_sources()
                if shipped is not None:  # the models' sources went too; without them no song runs
                    setup.sync_adapters(shipped, paths.adapters_root())

            def done(_result: None) -> None:
                self._removing = False
                if everything:
                    self._recent = []
                    self._post(RecentChanged(()))
                else:
                    with contextlib.suppress(OSError):  # asks again before the next download
                        settings.update(settings.store_path(), setup_agreed=False)
                self._set(session.Empty())
                self._notice(_("The downloaded models are removed"))

            def failed(exc: BaseException) -> None:
                self._removing = False
                self._set(session.Empty())
                self._notice(_("Could not remove everything: {reason}").format(reason=exc))

            self._run(remove, done, failed)
            return True

    # Uninstall Stickler… (SPEC.md "Release 10 (proposed): keep and remove", scope B)

    def begin_uninstall(self) -> bool:
        """Holds the app for an uninstall: nothing starts until `end_uninstall` (the system may
        ask for a password for minutes). False while something runs."""
        with self._lock:
            if not self.can_remove_models:
                return False
            self._stop_job()
            self._removing = True
            self._set(session.Empty())
            return True

    def end_uninstall(self) -> None:
        """The uninstall did not happen (a cancelled password prompt, an error): the app goes
        on."""
        with self._lock:
            self._removing = False
            self._set(self._state)

    # Back Up… and Restore Backup… (SPEC.md "Release 10 (proposed): keep and remove", scope A)

    def back_up(self, dest: Path) -> None:
        """Writes the backup in a thread and says when it is saved or why it is not."""

        def done(_summary: backup.Summary) -> None:
            self._notice(_("Backup saved"), dest)

        def failed(exc: BaseException) -> None:
            self._notice(_("The backup could not be saved: {reason}").format(reason=exc))

        self._run(lambda: backup.write(dest), done, failed, job=False)

    @staticmethod
    def backup_summary(src: Path) -> backup.Summary:
        """What a backup holds, for the question before the restore; raises
        backup.NotABackup. Reads the file: call it off the interface's thread."""
        return backup.read(src)

    def restore(self, src: Path) -> bool:
        """Restores a backup in a thread; the recent songs show at once. False while something
        runs (as for the removal: an analysis writes the same folders)."""
        with self._lock:
            if not self.can_remove_models:
                return False
            self._removing = True

            def done(_result: None) -> None:
                self._removing = False
                self._recent = recent.load(self._recent_store)
                self._post(RecentChanged(tuple(self._recent)))
                self._set(self._state)
                self._notice(_("Backup restored"))

            def failed(exc: BaseException) -> None:
                self._removing = False
                self._set(self._state)
                if isinstance(exc, backup.NotABackup):
                    text = _("This is no Stickler backup: {reason}")
                else:
                    text = _("The backup could not be restored: {reason}")
                self._notice(text.format(reason=exc))

            self._run(lambda: backup.restore(src), done, failed)
            return True

    def shutdown(self, seconds: float = 2.0) -> None:
        """Cancels the running job and waits until every job, a replaced one too, has cleaned
        up (its half-written cache folder removed), at most `seconds` in all, so that quitting
        leaves nothing behind. No job starts after it (a setup ending meanwhile opens no song)."""
        with self._lock:
            self._closed = True
            if self._timer is not None:
                self._timer.cancel()
            self._stop_sampling()
            self._stop_job()
            threads = list(self._threads)
        deadline = time.monotonic() + seconds
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))

    # the flows

    def _stored(self, song: Path) -> api.Corrections:
        """The song's remembered corrections (SPEC.md, module `corrections`), by its path or, when
        it moved, by its content (SPEC.md "Release 10", scope A3)."""
        digest = self._digests[song] = paths.song_digest(song)
        return corrections.lookup(corrections.store_path(), song.absolute(), digest)

    def _start(self, state: session.Analysing) -> None:
        if self._closed:
            return
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
                digest = self._digests.get(state.song, "")
                entry = recent.opened_now(state.song, info.title, info.artist, digest)
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
            if self._timer is not threading.current_thread():
                return  # replaced by a newer change while it waited for the lock
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
            digest = self._digests.get(song, "")
            corrections.remember(corrections.store_path(), song.absolute(), fix, digest)
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

    def _start_setup(self, missing: tuple[str, ...], song: Path | None) -> None:
        if self._closed:
            return
        root = paths.adapters_root()
        registry = adapters.discover(root)
        ids = setup.step_ids(list(missing), lambda a: adapters.needs_weights(registry[a]))
        self._stop_job()
        self._token = token = api.CancelToken()
        state = session.start_setup(ids, song, missing)
        job = state.job
        self._set(state)

        def step(reported: api.Step) -> None:
            with self._lock:
                if reported.state == "started" and reported.adapter in registry:
                    folder = registry[reported.adapter].path
                    self._grown = setup.meter(reported.id, root, folder)
                self._set(session.on_setup_step(self._state, job, reported))

        def run_setup() -> None:
            for adapter in missing:
                api.setup_adapters(adapter, "cpu", root, progress=step, cancel=token)

        def done(_result: None) -> None:
            state = session.setup_done(self._state, job)
            if state is not self._state:
                self._set(state)
                if song is not None:
                    self.open(song)

        self._sample(job)
        self._run(run_setup, done, lambda exc: self._set(session.failed(self._state, job, exc)))

    def _sample(self, job: int) -> None:
        """Measures the running download twice a second until its setup ends."""
        self._stop_sampling()
        self._sampling = stop = threading.Event()

        def sample() -> None:
            while not stop.wait(SAMPLE):
                with self._lock:
                    state = self._state
                    if not (isinstance(state, session.SettingUp) and state.job == job):
                        return
                    self._set(session.setup_grew(state, job, self._grown()))

        threading.Thread(target=sample, name="stickler-meter", daemon=True).start()

    def _stop_sampling(self) -> None:
        if self._sampling is not None:
            self._sampling.set()
            self._sampling = None

    def _separator_missing(self) -> bool:
        missing = api.mode_ready(drums=True, adapters_root=paths.adapters_root())
        return api.DRUM_TRACK_SEPARATOR in missing

    def _saved(self, dest: Path) -> None:
        self._notice(_("Saved “{name}”").format(name=dest.name), opens=dest)

    # plumbing; every change happens under the lock, so events reach `post` in order

    def _set(self, state: session.State) -> None:
        if state is not self._state:
            self._state = state
            self._post(Changed(state))

    def _notice(self, text: str, opens: Path | None = None) -> None:
        self._post(Notice(text, opens))

    def _stop_job(self) -> None:
        if self._token is not None:
            self._token.cancel()  # the job ends the model's processes within a second
            self._token = None

    def _run(
        self,
        work: Callable[[], Any],
        done: Callable[[Any], None],
        failed: Callable[[BaseException], None],
        *,
        job: bool = True,
    ) -> None:
        """Runs `work` in a daemon thread; its value or exception is handled under the lock.
        `job`: the one job `shutdown` waits for (the start's model check is none)."""

        if self._closed:
            return

        def run() -> None:
            try:
                try:
                    value = work()
                except Exception as exc:  # becomes a state or a notice, as in the window
                    with self._lock:
                        failed(exc)
                    return
                with self._lock:
                    done(value)
            finally:
                with self._lock:
                    self._threads.discard(thread)

        thread = threading.Thread(target=run, name="stickler-job", daemon=True)
        if job:
            self._threads.add(thread)
        thread.start()
