"""Fetches Beat This!'s checkpoint: from JKU Linz, its only host, else from Stickler's copy of
the same MIT-licensed file (SPEC.md, module `setup-assistant`). The SHA-256 is checked either
way, so the copy can only ever be the same file. No torch here, so it is tested on its own."""

import hashlib
import urllib.error
import urllib.request
from pathlib import Path

SHA256 = "8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331"  # final0.ckpt
SOURCES = [
    (
        "JKU Linz (cloud.cp.jku.at)",
        "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt",
    ),
    (
        "Stickler's copy (github.com)",
        "https://github.com/niklastshiang/stickler/releases/download/beat-this-final0/final0.ckpt",
    ),
]
TIMEOUT = 60  # seconds without an answer
CHUNK = 1 << 20


class DownloadFailed(RuntimeError):
    """No source gave the right file; the message names each source and why."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def fetch(dest: Path, sha256: str = SHA256, sources=SOURCES) -> str:
    """Puts the file at `dest` (through `<dest>.partial`) and returns the source used."""
    if dest.exists() and _sha256(dest) == sha256:
        return "already here"
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    failures = []
    for name, url in sources:
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as answer, partial.open("wb") as f:
                while block := answer.read(CHUNK):
                    f.write(block)
        except (urllib.error.URLError, OSError) as exc:
            failures.append(f"{name}: {getattr(exc, 'code', None) or exc}")
            partial.unlink(missing_ok=True)
            continue
        if _sha256(partial) != sha256:
            failures.append(f"{name}: wrong file (checksum differs)")
            partial.unlink()
            continue
        partial.replace(dest)
        return name
    raise DownloadFailed("Beat This! model not downloaded. " + "; ".join(failures))
