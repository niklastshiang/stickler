"""Which processes still run, for the tests around cancelling (Linux, macOS, Windows)."""

import os
import subprocess
import sys
import time


def _windows_parents() -> dict[int, int]:
    """Every running process's parent on Windows (a Toolhelp snapshot: no exited ones)."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = (
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    for walk in (kernel32.Process32FirstW, kernel32.Process32NextW):
        walk.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    parents = {}
    more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
    while more:
        parents[entry.th32ProcessID] = entry.th32ParentProcessID
        more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    kernel32.CloseHandle(snapshot)
    return parents


def _windows_states() -> list[tuple[int, str, int]]:
    """Windows has no process groups. What stands in for one here: the ancestor that this
    test process started (`uv`, which starts the environment's Python, which starts the model);
    a process whose parents are gone is its own group, so tests also look at the model's pid."""
    parents = _windows_parents()
    found = []
    for pid in parents:
        top, seen = pid, {pid}
        while parents.get(top) in parents and parents[top] != os.getpid():
            top = parents[top]
            if top in seen:  # a pid used again can close a circle
                break
            seen.add(top)
        found.append((pid, "R", top))
    return found


def _states() -> list[tuple[int, str, int]]:
    """(pid, state, process group) of every process: from /proc on Linux, from `ps` where
    there is none (macOS, 2026-11-17), from a snapshot on Windows (2026-11-24)."""
    if sys.platform == "win32":
        return _windows_states()
    if not os.path.isdir("/proc"):
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,stat=,pgid="],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        rows = (line.split() for line in out.splitlines() if line.strip())
        return [(int(pid), stat[0], int(pgid)) for pid, stat, pgid in rows]
    found = []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat", encoding="utf-8") as f:
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
    def group(pid: int) -> int:
        """The process group of a running process (on Windows what stands in for it)."""
        if sys.platform == "win32":
            return next(g for p, _, g in _states() if p == pid)
        return os.getpgid(pid)

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
