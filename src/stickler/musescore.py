"""Optional MuseScore integration: render MusicXML to PDF via the MuseScore command line.

MuseScore is found on PATH or as the Flathub app. The Flatpak sandbox only sees the files
it is granted, so the export passes `--filesystem` for the folder of the output.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

FLATPAK_ID = "org.musescore.MuseScore"
BINARIES = ("mscore", "musescore", "mscore4portable", "musescore4")


def flatpak_ids() -> set[str]:
    if not shutil.which("flatpak"):
        return set()
    proc = subprocess.run(
        ["flatpak", "list", "--app", "--columns=application"], capture_output=True, text=True
    )
    return set(proc.stdout.split())


def find(
    which: Callable[[str], str | None] | None = None,
    flatpak_ids: Callable[[], set[str]] = flatpak_ids,
) -> list[str] | None:
    """Command prefix to run MuseScore, or None if it is not installed."""
    which = which or shutil.which
    for name in BINARIES:
        if path := which(name):
            return [path]
    if FLATPAK_ID in flatpak_ids():
        return ["flatpak", "run", FLATPAK_ID]
    return None


def export_pdf(musicxml: Path, pdf: Path, command: list[str]) -> Path:
    """Renders `musicxml` to `pdf`; raises RuntimeError if MuseScore fails."""
    cmd = list(command)
    if cmd[:2] == ["flatpak", "run"]:
        folders = sorted({str(musicxml.parent.resolve()), str(pdf.parent.resolve())})
        cmd = ["flatpak", "run", *(f"--filesystem={f}" for f in folders), *cmd[2:]]
    proc = subprocess.run([*cmd, "-o", str(pdf), str(musicxml)], capture_output=True, text=True)
    if proc.returncode != 0 or not pdf.exists():
        detail = (proc.stderr or proc.stdout).strip()[-300:] or f"exit code {proc.returncode}"
        raise RuntimeError(f"MuseScore: PDF export failed: {detail}")
    return pdf
