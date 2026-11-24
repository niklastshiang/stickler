"""Removing Stickler's own `.deb` or `.rpm` through PackageKit over D-Bus (SPEC.md "Release 10
(proposed): keep and remove", scope B2): the same call on Ubuntu 26.04 and Fedora 44/45, where
PackageKit is installed by default; the system asks for the password (polkit
`org.freedesktop.packagekit.package-remove`). Not dnf5daemon, which removes without asking an
administrator. Gio only, no PackageKit library: nothing to install besides the package.

Two transactions: `Resolve` finds the installed package's id, `RemovePackages` removes it.
`remove(name, done)` reports `done(None)` when it is removed, or `done(reason)`; a cancelled
password prompt is a reason too, and then nothing changed."""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Gio, GLib

from stickler_app import uninstall

NAME = "org.freedesktop.PackageKit"
PATH = "/org/freedesktop/PackageKit"
TRANSACTION = "org.freedesktop.PackageKit.Transaction"


class _Transaction:
    """One PackageKit transaction: its signals collected until Finished."""

    def __init__(self, bus: Gio.DBusConnection, finished: Callable[[_Transaction], None]):
        self.bus = bus
        self.finished = finished
        self.packages: list[str] = []
        self.error = ""
        self.exit = 0
        self.path = ""
        self._signal = 0

    def start(self, method: str, args: GLib.Variant) -> None:
        def created(bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                (self.path,) = bus.call_finish(result).unpack()
            except GLib.Error:  # PackageKit is not there or does not start
                self.error = uninstall.unreachable()
                self.finished(self)
                return
            self._signal = bus.signal_subscribe(
                NAME, TRANSACTION, None, self.path, None, Gio.DBusSignalFlags.NONE, self._on
            )

            def hinted(bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
                try:
                    bus.call_finish(result)
                except GLib.Error as exc:
                    self.error = exc.message
                    self._end()
                    return
                bus.call(
                    NAME,
                    self.path,
                    TRANSACTION,
                    method,
                    args,
                    None,
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                    self._called,
                )

            # first the hints (a person is there: polkit may ask for the password), then the
            # method itself
            bus.call(
                NAME,
                self.path,
                TRANSACTION,
                "SetHints",
                GLib.Variant("(as)", (uninstall.HINTS,)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                hinted,
            )

        self.bus.call(
            NAME,
            PATH,
            NAME,
            "CreateTransaction",
            None,
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            created,
        )

    def _called(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:  # refused before it ran: Finished never comes
            self.error = exc.message
            self._end()

    def _on(self, _bus, _sender, _path, _iface, signal: str, params: GLib.Variant) -> None:
        if signal == "Package":
            self.packages.append(params.unpack()[1])
        elif signal == "ErrorCode":
            self.error = params.unpack()[1]
        elif signal == "Finished":
            self.exit = params.unpack()[0]
            self._end()

    def _end(self) -> None:
        if self._signal:
            self.bus.signal_unsubscribe(self._signal)
            self._signal = 0
        self.finished(self)


def remove(name: str, done: Callable[[str | None], None]) -> None:
    """Removes the installed package `name`; `done(None)` once it is gone, else `done(reason)`."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except GLib.Error:  # no system bus (a Distrobox, a container)
        done(uninstall.unreachable())
        return

    def resolved(found: _Transaction) -> None:
        failed = uninstall.transaction_failed(found.exit, found.error)
        ours = uninstall.chosen_package(name, found.packages)
        if failed or ours is None:
            done(failed or f"{name} is not installed as a package")
            return
        args = GLib.Variant("(tasbb)", (0, [ours], False, False))
        _Transaction(bus, removed).start("RemovePackages", args)

    def removed(transaction: _Transaction) -> None:
        done(uninstall.transaction_failed(transaction.exit, transaction.error))

    args = GLib.Variant("(tas)", (uninstall.INSTALLED, [name]))
    _Transaction(bus, resolved).start("Resolve", args)


def remove_and_wait(name: str, seconds: float = 600) -> str | None:
    """`remove` with a main loop of its own: for the container test and a command line."""
    loop = GLib.MainLoop()
    outcome: list[str | None] = []

    def done(reason: str | None) -> None:
        outcome.append(reason)
        loop.quit()

    remove(name, done)
    GLib.timeout_add_seconds(int(seconds), lambda: loop.quit() or False)
    loop.run()
    return outcome[0] if outcome else "PackageKit did not answer in time"
