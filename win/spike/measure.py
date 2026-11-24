"""Measurements of the spike's job, as markdown for the job summary. Windows only; every file
operation uses the \\\\?\\ form so that a long path does not hide a result.

    measure.py exes <label=root>...     every .exe: size, SHA-256, signature, and which are equal
    measure.py paths <data adapters folder>   the longest path per model environment
    measure.py sizes <Stickler data root>     size per subfolder
    measure.py seconds <log file>...          setup and analysis seconds from the driver's logs
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def lp(path: str | Path) -> str:
    text = os.path.abspath(str(path))
    return text if text.startswith("\\\\?\\") else "\\\\?\\" + text


def walk(root: Path):
    for folder, dirs, files in os.walk(lp(root)):
        yield folder.removeprefix("\\\\?\\"), dirs, files


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(lp(path), "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def signatures(paths: list[str]) -> dict[str, str]:
    """Get-AuthenticodeSignature for each file, in one PowerShell call."""
    listing = Path(os.environ.get("TEMP", ".")) / "spike-exes.txt"
    listing.write_text("\n".join(paths), encoding="utf-8")
    script = (
        "$ErrorActionPreference='Continue';"
        f"Get-Content -LiteralPath '{listing}' -Encoding UTF8 | ForEach-Object {{"
        "try { $s = Get-AuthenticodeSignature -LiteralPath ('\\\\?\\' + $_) } catch { $s = $null };"
        'if ($s -and $s.SignerCertificate) { $r = "$($s.Status)|$($s.SignerCertificate.Subject)" }'
        "elseif ($s) { $r = \"$($s.Status)|\" } else { $r = 'error|' };"
        '[Console]::Out.WriteLine("$_`t$r") }'
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    result = {}
    for line in out.splitlines():
        if "\t" in line:
            path, rest = line.split("\t", 1)
            status, _bar, subject = rest.partition("|")
            result[path] = (
                "not signed"
                if status == "NotSigned"
                else (f"{status}: {subject}" if subject else status)
            )
    return result


def exes(specs: list[str]) -> None:
    found: list[tuple[str, str, str]] = []  # label, relative, absolute
    for spec in specs:
        label, _eq, root = spec.partition("=")
        for folder, _dirs, files in walk(Path(root)):
            for name in files:
                if name.lower().endswith(".exe"):
                    absolute = os.path.join(folder, name)
                    found.append((label, os.path.relpath(absolute, root), absolute))
    found.sort()
    signed = signatures([absolute for _l, _r, absolute in found])
    rows = []
    hashes: dict[str, str] = {}
    for label, relative, absolute in found:
        digest = sha256(absolute)
        hashes[absolute] = digest
        size = os.path.getsize(lp(absolute))
        rows.append((label, relative, size, digest, signed.get(absolute, "no result")))
    print("### Every .exe\n")
    print("| Where | Path | Bytes | SHA-256 | Signature |\n|---|---|---|---|---|")
    for label, relative, size, digest, signature in rows:
        print(f"| {label} | `{relative}` | {size} | `{digest}` | {signature} |")
    print(f"\n{len(rows)} files.\n")
    pythons = [
        (label, rel, hashes[a]) for label, rel, a in found if rel.lower().endswith("python.exe")
    ]
    venv = [p for p in pythons if "\\.venv\\Scripts\\" in p[1]]
    print("### Are the environments' launchers one file?\n")
    by_hash: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for label, rel, digest in pythons:
        by_hash[digest].append((label, rel))
    if venv:
        distinct = {h for _l, _r, h in venv}
        print(
            f"- {len(venv)} environment `.venv\\Scripts\\python.exe` files, "
            f"{len(distinct)} distinct SHA-256: "
            + ("byte-identical to each other." if len(distinct) == 1 else "NOT all identical.")
        )
        for label, rel, digest in venv:
            others = [f"{lb}:{r}" for lb, r in by_hash[digest] if (lb, r) != (label, rel)]
            same = "; ".join(f"`{o}`" for o in others) if others else "no other python.exe"
            print(f"- `{rel}` (`{digest[:16]}`) is identical to: {same}")
    else:
        print("- no environment launcher found")
    print("\n### Every python.exe by content\n")
    for digest, members in by_hash.items():
        print(f"- `{digest[:16]}`: " + "; ".join(f"`{lb}:{r}`" for lb, r in members))


def paths(adapters: str) -> None:
    root = Path(adapters)
    print("### Longest path per model environment\n")
    print("| Model folder | Full length | Length below `adapters\\` | Path below `adapters\\` |")
    print("|---|---|---|---|")
    for folder, dirs, _files in walk(root):
        if ".venv" not in dirs:
            continue
        longest = ""
        for sub, subdirs, files in walk(Path(folder)):
            for name in subdirs + files:
                full = os.path.join(sub, name)
                if len(full) > len(longest):
                    longest = full
        relative = os.path.relpath(longest, root)
        model = os.path.relpath(folder, root)
        print(f"| `{model}` | {len(longest)} | {len(relative)} | `{relative}` |")
    print(f"\nPrefix in front of `adapters\\`: `{root}` ({len(str(root))} characters).")


def size_of(folder: str) -> int:
    total = 0
    for sub, _dirs, files in walk(Path(folder)):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.path.getsize(lp(os.path.join(sub, name)))
    return total


def sizes(root: str) -> None:
    print("### Size of the data below Stickler's folder\n")
    print("| Folder | MB |\n|---|---|")
    base = Path(root)
    if not base.is_dir():
        print(f"| `{root}` | (missing) |")
        return
    print(f"| `{root}` (all) | {size_of(root) / 1e6:.0f} |")
    for top in sorted(p for p in base.iterdir() if p.is_dir()):
        print(f"| `{top.name}` | {size_of(str(top)) / 1e6:.0f} |")
        if top.name in ("data", "cache"):
            for sub in sorted(p for p in top.iterdir() if p.is_dir()):
                print(f"| `{top.name}\\{sub.name}` | {size_of(str(sub)) / 1e6:.0f} |")


def seconds(logs: list[str]) -> None:
    print("### Seconds, from the driver's logs\n")
    print("| Log | Line |\n|---|---|")
    for log in logs:
        for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
            if "seconds:" in line and "[" in line:
                print(f"| `{Path(log).name}` | `{line}` |")


if __name__ == "__main__":
    command, rest = sys.argv[1], sys.argv[2:]
    {
        "exes": exes,
        "paths": lambda a: paths(a[0]),
        "sizes": lambda a: sizes(a[0]),
        "seconds": seconds,
    }[command](rest)
