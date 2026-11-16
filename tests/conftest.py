"""Shared test setup."""

import os
import time

import pytest


@pytest.fixture(autouse=True)
def _isolate_from_outer_git(monkeypatch):
    """Under `git commit` the pre-commit hook inherits GIT_DIR, GIT_INDEX_FILE and friends.
    Tests that create their own repositories must not operate on the outer one."""
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        monkeypatch.delenv(name)


def _states() -> list[tuple[int, str, int]]:
    """(pid, state, process group) of every process, read from /proc."""
    found = []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat") as f:
                stat = f.read()
        except OSError:
            continue
        # The command name may contain spaces and parentheses; the fields follow the last ")".
        fields = stat.rsplit(")", 1)[1].split()
        found.append((int(entry.name), fields[0], int(fields[2])))
    return found


class Processes:
    """Whether processes still run. A killed process whose parent has died is handed to PID 1;
    an init that does not reap (as in some containers) leaves it a zombie, which runs no code
    and holds no resources. Zombies therefore count as ended."""

    @staticmethod
    def running(pid: int) -> bool:
        return any(p == pid and s not in "ZX" for p, s, _ in _states())

    @staticmethod
    def group_gone(group: int, within: float = 1) -> bool:
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            if not any(g == group and s not in "ZX" for _, s, g in _states()):
                return True
            time.sleep(0.01)
        return False


@pytest.fixture
def processes() -> type[Processes]:
    return Processes
