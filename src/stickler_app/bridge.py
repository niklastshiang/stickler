"""`stickler-bridge`: the core as one subprocess speaking JSON lines (SPEC.md, module
`core-bridge`). The Mac app starts it once, sends commands on stdin and draws the states it
gets on stdout; everything the reader sees is decided and translated here.

Lines: one JSON object each, UTF-8. The first is `hello`; then every command gets exactly one
reply (`{"id", "ok": true, ...}` or `{"id", "ok": false, "error": {"code", "message"}}`), and
every change of the controller is an event (`state`, `recent`, `notice`) with a `seq` that grows
by one. Only the writer thread touches stdout, so lines never interleave. Logs go to stderr.
`quit`, or stdin closing, cancels the running job, waits for its clean-up and exits 0."""

from __future__ import annotations

import collections
import dataclasses
import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any, TextIO

from stickler_app import (
    controller,
    engraving,
    i18n,
    paths,
    recent,
    session,
    settings,
    setup,
    steps,
    zoom,
)
from stickler_app.i18n import _

PROTOCOL = 1
QUIT_WAIT = 2.0  # seconds the running job gets to clean up, as the GTK window gives it
QUEUE_STATES = 64  # beyond this many unsent states only the newest are kept (each is whole)

log = logging.getLogger("stickler.bridge")

KINDS: dict[type, str] = {
    session.Empty: "empty",
    session.Consent: "consent",
    session.SettingUp: "setting_up",
    session.SetupFailed: "setup_failed",
    session.Analysing: "analysing",
    session.Result: "result",
    session.Exporting: "exporting",
    session.Failed: "failed",
}


# the state as JSON: one function per kind, the texts already translated


def _path(path: Path | None) -> str | None:
    return None if path is None else str(path)


def _rows(rows) -> list[dict[str, str]]:
    return [{"id": r.id, "label": r.label, "detail": r.detail, "state": r.state} for r in rows]


def _consent(state: session.Consent) -> dict[str, Any]:
    models = []
    for adapter in state.missing:
        does, licence = setup.model_text(adapter)
        models.append(
            {
                "id": adapter,
                "name": steps.model_name(adapter),
                "does": does,
                "licence": licence,
                "size": setup.model_size(adapter),
            }
        )
    return {
        "song": _path(state.song),
        "models": models,
        "total_size": setup.total_size(state.missing),
    }


def _setting_up(state: session.SettingUp) -> dict[str, Any]:
    """The running step says how much it has downloaded, as the GTK window shows it."""
    rows = []
    for row in state.steps:
        amount = setup.amount(row.id, state.grown) if row.state == "running" else ""
        rows.append(dataclasses.replace(row, detail=amount) if amount else row)
    return {"song": _path(state.song), "steps": _rows(rows)}


def _setup_failed(state: session.SetupFailed) -> dict[str, Any]:
    return {
        "song": _path(state.song),
        "steps": _rows(state.steps),
        "step": state.step,
        "server": setup.server(state.step),
        "details": setup.details(state.details),
    }


def _analysing(state: session.Analysing) -> dict[str, Any]:
    return {"song": str(state.song), "name": state.song.stem, "steps": _rows(state.steps)}


def _exporting(state: session.Exporting) -> dict[str, Any]:
    return {
        "song": str(state.song),
        "title": state.previous.title,
        "subtitle": state.previous.subtitle,
        "dest": str(state.dest),
        "steps": _rows(state.steps),
    }


def _result(state: session.Result) -> dict[str, Any]:
    num, den = state.notation.meter
    return {
        "song": str(state.song),
        "title": state.title,
        "subtitle": state.subtitle,
        "artist": state.info.artist,
        "seconds": state.info.seconds,
        "tempo": state.notation.tempo,
        "meter": [num, den],
        "musicxml": str(state.notation.musicxml),
        "corrections": dataclasses.asdict(state.wanted),
        "correcting": state.pending is not None,
    }


def _failed(state: session.Failed) -> dict[str, Any]:
    return {
        "song": str(state.song),
        "name": state.song.stem,
        "reason": state.kind,
        "title": state.title,
        "description": state.description,
        "details": state.details,
    }


ENCODERS: dict[type, Callable[[Any], dict[str, Any]]] = {
    session.Empty: lambda _state: {},
    session.Consent: _consent,
    session.SettingUp: _setting_up,
    session.SetupFailed: _setup_failed,
    session.Analysing: _analysing,
    session.Result: _result,
    session.Exporting: _exporting,
    session.Failed: _failed,
}


def can(state: session.State, *, remove_models: bool) -> dict[str, bool]:
    """Which commands fit now, so the Mac app enables its buttons and menu items from the
    state alone: `session.abilities`, the rule the GTK window uses too. `remove_models` is the
    controller's answer for this same state (`Controller.can_remove_models`, by that rule)."""
    found = session.abilities(state, installed=True, removing=False)
    sent = {f"can_{f.name}": getattr(found, f.name) for f in dataclasses.fields(found)}
    return {**sent, "can_remove_models": remove_models}


def encode(state: session.State, *, remove_models: bool = False) -> dict[str, Any]:
    kind = type(state)
    return {"kind": KINDS[kind], **ENCODERS[kind](state), **can(state, remove_models=remove_models)}


def recent_rows(songs: tuple[recent.Recent, ...]) -> list[dict[str, Any]]:
    return [
        {"path": str(r.path), "title": r.title, "detail": r.detail, "missing": r.missing}
        for r in recent.rows(list(songs))
    ]


# errors: a stable code for Swift, a translated message for the reader


class CommandError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def _not_now() -> CommandError:
    return CommandError("not_now", _("This is not possible right now."))


def _bad_argument(name: str) -> CommandError:
    return CommandError(
        "bad_argument", _("The value of “{argument}” is not valid.").format(argument=name)
    )


def _text(command: dict[str, Any], name: str) -> str:
    value = command.get(name)
    if not isinstance(value, str) or not value:
        raise _bad_argument(name)
    return value


def _number(command: dict[str, Any], name: str, default: float | None = None) -> float:
    """A positive, finite number; `default` when the argument is left out."""
    value = command.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _bad_argument(name)
    if not 0 < value < float("inf"):
        raise _bad_argument(name)
    return float(value)


def _flag(command: dict[str, Any], name: str) -> bool:
    value = command.get(name)
    if not isinstance(value, bool):
        raise _bad_argument(name)
    return value


def encode_page(page: engraving.Page) -> dict[str, Any]:
    """A page as SVG with its size in pixels and the written bars' rectangles, top to bottom
    (a click on one jumps there; the playing bar is marked on it)."""
    bars = [
        {
            "bar": number,
            "x": round(box.x, 2),
            "y": round(box.y, 2),
            "width": round(box.width, 2),
            "height": round(box.height, 2),
        }
        for number, box in sorted(page.bars.items())
    ]
    return {"svg": page.svg, "width": page.width, "height": page.height, "bars": bars}


def _zoom_reply(value: float) -> dict[str, Any]:
    return {"zoom": value, "percent": zoom.percent(value)}


# the outgoing lines


class Outbox:
    """What the writer sends, in order. A host that stops reading cannot block the core:
    beyond QUEUE_STATES unsent states the oldest are dropped (the newest is whole)."""

    def __init__(self) -> None:
        self._items: collections.deque[tuple[str, Any]] = collections.deque()
        self._ready = threading.Condition()
        self._states = 0
        self._closed = False

    def put(self, kind: str, item: Any) -> None:
        with self._ready:
            if kind == "state":
                self._states += 1
                if self._states > QUEUE_STATES:
                    oldest = next(i for i, (k, _item) in enumerate(self._items) if k == "state")
                    del self._items[oldest]
                    self._states -= 1
            self._items.append((kind, item))
            self._ready.notify()

    def close(self) -> None:
        with self._ready:
            self._closed = True
            self._ready.notify()

    def take(self) -> tuple[str, Any] | None:
        """The next item; None once closed and empty."""
        with self._ready:
            while not self._items and not self._closed:
                self._ready.wait()
            if not self._items:
                return None
            kind, item = self._items.popleft()
            if kind == "state":
                self._states -= 1
            return kind, item


class Bridge:
    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self._stdin, self._stdout = stdin, stdout
        self._outbox = Outbox()
        self._seq = 0
        self.controller: controller.Controller | None = None
        self._commands: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "start": self._start,
            "agree": lambda _c: self._fits(self._ctl.agree()),
            "not_now": lambda _c: self._fits(self._ctl.not_now()),
            "retry_setup": lambda _c: self._fits(self._ctl.retry_setup()),
            "open": self._open,
            "cancel": lambda _c: self._fits(self._ctl.cancel()),
            "retry": lambda _c: self._fits(self._ctl.retry()),
            "close": self._close,
            "pages": self._pages,
            "a4_pages": self._a4_pages,
            "export_musicxml": lambda c: self._fits(
                self._ctl.export_musicxml(Path(_text(c, "dest")))
            ),
            "drum_track_cost": self._drum_track_cost,
            "export_drum_track": lambda c: self._fits(
                self._ctl.export_drum_track(Path(_text(c, "dest")))
            ),
            "forget_recent": self._forget_recent,
            "settings": self._settings,
            "set_zoom": lambda c: self._zoom(lambda _now: zoom.clamp(_number(c, "zoom"))),
            "zoom_in": lambda _c: self._zoom(zoom.zoom_in),
            "zoom_out": lambda _c: self._zoom(zoom.zoom_out),
            "actual_size": lambda _c: self._zoom(lambda _now: 1.0),
            "removal_sizes": self._removal_sizes,
            "remove_models": lambda c: self._fits(self._ctl.remove_models(_flag(c, "everything"))),
            "quit": lambda _c: {},
        }

    @property
    def commands(self) -> frozenset[str]:
        return frozenset(self._commands)

    @property
    def _ctl(self) -> controller.Controller:
        assert self.controller is not None
        return self.controller

    def run(self) -> int:
        """Reads commands until `quit` or the end of stdin; returns the exit status."""
        writer = threading.Thread(target=self._write, name="stickler-writer", daemon=True)
        writer.start()
        self._outbox.put("line", hello())
        self.controller = ctl = controller.Controller(post=self._post)
        self._outbox.put("state", (ctl.state, ctl.can_remove_models))
        self._outbox.put("recent", ctl.recent)
        for line in self._stdin:
            if not line.strip():
                continue
            if self._handle(line) == "quit":
                break
        ctl.shutdown(QUIT_WAIT)
        self._outbox.close()
        writer.join()
        return 0

    def _handle(self, line: str) -> str | None:
        ident: Any = None
        try:
            command = json.loads(line)
            if not isinstance(command, dict):
                raise ValueError("not an object")
            ident = command.get("id")
            if not isinstance(ident, int) or isinstance(ident, bool):
                ident = None
                raise ValueError("no id")
            name = command.get("cmd")
            if not isinstance(name, str):
                raise ValueError("no cmd")
        except ValueError as exc:
            log.warning("bad request: %s", exc)
            self._reply_error(ident, "bad_request", _("The request could not be read."))
            return None
        handler = self._commands.get(name)
        if handler is None:
            message = _("Stickler does not know the command “{name}”.").format(name=name)
            self._reply_error(ident, "unknown_command", message)
            return None
        try:
            extra = handler(command)
        except CommandError as exc:
            self._reply_error(ident, exc.code, exc.message)
            return None
        except Exception:  # a bug: the reader gets an answer, the bridge goes on
            log.exception("command %s failed", name)
            self._reply_error(ident, "internal", _("Something went wrong inside Stickler."))
            return None
        self._outbox.put("line", {"id": ident, "ok": True, **extra})
        return name

    def _reply_error(self, ident: int | None, code: str, message: str) -> None:
        error = {"code": code, "message": message}
        self._outbox.put("line", {"id": ident, "ok": False, "error": error})

    # the commands

    @staticmethod
    def _fits(done: bool) -> dict[str, Any]:
        if not done:
            raise _not_now()
        return {}

    def _start(self, _command: dict[str, Any]) -> dict[str, Any]:
        self._ctl.start()
        return {}

    def _open(self, command: dict[str, Any]) -> dict[str, Any]:
        self._ctl.open(Path(_text(command, "path")))
        return {}

    def _close(self, _command: dict[str, Any]) -> dict[str, Any]:
        self._ctl.close()
        return {}

    def _result(self) -> session.Result:
        state = self._ctl.state
        if not isinstance(state, session.Result):
            raise _not_now()
        return state

    def _musicxml(self) -> str:
        return self._result().notation.musicxml.read_text(encoding="utf-8")

    def _pages(self, command: dict[str, Any]) -> dict[str, Any]:
        """The sheet `width` pixels wide at `zoom` (the stored note size when left out)."""
        width = _number(command, "width")
        stored = settings.load(settings.store_path()).zoom
        size = zoom.clamp(_number(command, "zoom", stored))
        pages = engraving.engrave(self._musicxml(), width, size)
        return {"zoom": size, "pages": [encode_page(p) for p in pages]}

    def _a4_pages(self, _command: dict[str, Any]) -> dict[str, Any]:
        """The A4 pages for the PDF, which the app writes (SPEC point 3). The legend (module
        `legend`) is deferred, as in the GTK app."""
        result = self._result()
        pages = engraving.a4_pages(self._musicxml())
        return {"title": result.title, "pages": [encode_page(p) for p in pages]}

    def _drum_track_cost(self, _command: dict[str, Any]) -> dict[str, Any]:
        cost = self._ctl.drum_track_cost()
        if cost is None:
            raise _not_now()
        return {"minutes": cost.minutes, "text": cost.text, "download": cost.download}

    def _forget_recent(self, command: dict[str, Any]) -> dict[str, Any]:
        self._ctl.forget_recent(Path(_text(command, "path")))
        return {}

    @staticmethod
    def _settings(_command: dict[str, Any]) -> dict[str, Any]:
        chosen = settings.load(settings.store_path())
        return {**dataclasses.asdict(chosen), "percent": zoom.percent(chosen.zoom)}

    @staticmethod
    def _zoom(change: Callable[[float], float]) -> dict[str, Any]:
        """The note size for every song, remembered; unsaved it still holds for this run (the
        app keeps the value it is sent)."""
        new = change(settings.load(settings.store_path()).zoom)
        try:
            settings.update(settings.store_path(), zoom=new)
        except OSError:
            log.warning("the note size could not be saved")
        return _zoom_reply(new)

    def _removal_sizes(self, _command: dict[str, Any]) -> dict[str, Any]:
        """What "Remove Downloaded Models…" would free, with the dialog's text for each
        choice. Walks the folders: the reply can take a moment."""
        models, everything = self._ctl.removal_sizes()

        def text(size: int) -> str:
            return _(
                "This frees {size}. Stickler asks before it downloads the models again."
            ).format(size=setup.size_text(size))

        return {
            "models": models,
            "everything": everything,
            "models_text": text(models),
            "everything_text": text(everything),
        }

    # the writer side

    def _post(self, event: controller.Event) -> None:
        """Called by the controller under its lock, in order; never blocks."""
        if isinstance(event, controller.Changed):
            self._outbox.put("state", (event.state, self._ctl.can_remove_models))
        elif isinstance(event, controller.RecentChanged):
            self._outbox.put("recent", event.songs)
        else:
            self._outbox.put("notice", event)

    def _write(self) -> None:
        while (item := self._outbox.take()) is not None:
            kind, payload = item
            try:
                line = payload if kind == "line" else self._event(kind, payload)
                self._stdout.write(json.dumps(line, ensure_ascii=False) + "\n")
                self._stdout.flush()
            except (OSError, ValueError):  # the app has gone; the reader ends with stdin
                log.exception("could not write a line")

    def _event(self, kind: str, payload: Any) -> dict[str, Any]:
        self._seq += 1
        line: dict[str, Any] = {"event": kind, "seq": self._seq}
        if kind == "state":
            state, remove_models = payload
            line["state"] = encode(state, remove_models=remove_models)
        elif kind == "recent":
            line["rows"] = recent_rows(payload)
        else:
            line["text"], line["opens"] = payload.text, _path(payload.opens)
        return line


def hello() -> dict[str, Any]:
    info = i18n.translation().info()
    return {
        "event": "hello",
        "protocol": PROTOCOL,
        "version": metadata.version("stickler"),
        "language": info.get("language") or "en",
    }


def main() -> int:
    """Entry point `stickler-bridge`. The protocol keeps the real stdout; everything else
    written to file descriptor 1 (a library's print, a model's output) goes to stderr."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="bridge: %(message)s")
    os.environ.update(paths.packaged_env())
    i18n.setup()
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    sys.stdin.reconfigure(encoding="utf-8")
    return Bridge(sys.stdin, protocol).run()


if __name__ == "__main__":
    sys.exit(main())
