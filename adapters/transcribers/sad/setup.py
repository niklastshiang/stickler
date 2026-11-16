"""Downloads the pinned Separate-and-Detect code, its checkpoint and the CLIP vocabulary into
weights/, each checked by commit or SHA-256. An interrupted download stays a `.partial` file,
which the harness removes before the next setup."""

import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path

from common import (
    CHECKPOINT,
    CHECKPOINT_SHA256,
    CHECKPOINT_URL,
    COMMIT,
    REPO,
    SOURCE,
    VOCAB,
    VOCAB_SHA256,
    VOCAB_URL,
)


def _sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _download(url: str, dest: Path, sha256: str) -> None:
    if dest.exists() and _sha256(dest) == sha256:
        return
    partial = dest.with_name(dest.name + ".partial")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    if _sha256(partial) != sha256:
        partial.unlink()
        raise RuntimeError(f"{url}: checksum mismatch")
    partial.replace(dest)


def _source() -> None:
    head = SOURCE / ".git" / "HEAD"
    if head.exists():
        current = subprocess.run(
            ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        if current == COMMIT:
            return
        shutil.rmtree(SOURCE)
    SOURCE.mkdir(parents=True)
    for args in (["init", "-q"], ["fetch", "-q", "--depth", "1", REPO, COMMIT]):
        subprocess.run(["git", "-C", str(SOURCE), *args], check=True)
    subprocess.run(["git", "-C", str(SOURCE), "checkout", "-q", "FETCH_HEAD"], check=True)


if __name__ == "__main__":
    _source()
    _download(VOCAB_URL, VOCAB, VOCAB_SHA256)
    _download(CHECKPOINT_URL, CHECKPOINT, CHECKPOINT_SHA256)
    print(f"Separate-and-Detect {COMMIT[:7]} and {CHECKPOINT.name} in {CHECKPOINT.parent}")
