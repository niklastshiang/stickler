#!/usr/bin/env python3
"""The parts of the Mac app's bundle that need no Mac (SPEC.md, module `mac-package`, scope 2;
`scripts/mac_bundle.sh` calls them with the Python it has just put into the app):

    mac_bundle_tools.py mo <po> <mo>                 a gettext catalogue, without msgfmt
    mac_bundle_tools.py prune <python>               drop what the core never runs
    mac_bundle_tools.py licenses <core> name=file…   collect the licences of what is shipped
    mac_bundle_tools.py check <core>                 exit 1 when something is missing or too much

Standard library only, Python 3.12 or newer.
"""

from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

APP_ADAPTERS = ("transcribers/adtof", "beats/beat_this", "separators/demucs")
PROGRAMS = ("bin/uv", "bin/ffmpeg", "bin/ffprobe", "python/bin/python3")
OWN = ("uv", "ffmpeg", "stickler")  # licences handed over by the build, not found in a wheel
NEVER = (".venv", "weights", "__pycache__", ".pytest_cache", ".setup-done")
NEVER_SUFFIXES = (".pyc", ".ckpt", ".pth", ".safetensors")


def compile_mo(po: str) -> bytes:
    """A .po file as the .mo gettext reads (GNU's format, little endian): translated entries
    only, a fuzzy one is a guess and stays out, as with msgfmt."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import xcstrings  # the po reader next to this file

    header, entries = xcstrings.read_po(po)
    table = {"": "".join(f"{name}: {value}\n" for name, value in header.items())}
    for entry in entries:
        if "fuzzy" in entry.flags or not entry.msgstr or not all(entry.msgstr):
            continue
        key = entry.msgid
        if entry.msgid_plural is not None:
            key += "\0" + entry.msgid_plural
        table[key] = "\0".join(entry.msgstr)
    keys = sorted(table, key=lambda k: k.encode("utf-8"))
    originals = [k.encode("utf-8") for k in keys]
    translations = [table[k].encode("utf-8") for k in keys]
    count = len(keys)
    start = 7 * 4 + 2 * 8 * count  # the header, then both tables of (length, offset)
    index, data = [], b""
    for texts in (originals, translations):
        for text in texts:
            index.append((len(text), start + len(data)))
            data += text + b"\0"
    out = struct.pack("<Iiiiiii", 0x950412DE, 0, count, 7 * 4, 7 * 4 + 8 * count, 0, 0)
    out += b"".join(struct.pack("<ii", length, offset) for length, offset in index)
    return out + data


def _site(core: Path) -> Path | None:
    found = sorted((core / "python" / "lib").glob("python3.*/site-packages"))
    return found[0] if found else None


def _distributions(site: Path) -> list[tuple[str, str, Path]]:
    """(name, version, its dist-info) of every package installed in `site`."""
    rows = []
    for info in sorted(site.glob("*.dist-info")):
        fields = {}
        for line in (info / "METADATA").read_text(encoding="utf-8").splitlines():
            name, colon, value = line.partition(":")
            if not colon:
                break  # the description follows the first blank line
            fields.setdefault(name.strip().lower(), value.strip())
        rows.append((fields.get("name", info.name).lower(), fields.get("version", ""), info))
    return rows


def _licence_files(info: Path) -> list[tuple[Path, Path]]:
    """A package's licence files, each with the place it keeps below the package's folder:
    a wheel has files of the same name in folders of its own (numpy's `LICENSE.txt` and
    those of what it bundles)."""
    inside = info / "licenses"
    found = [(p, p.relative_to(inside)) for p in sorted(inside.rglob("*")) if p.is_file()]
    marks = ("LICENSE", "LICENCE", "COPYING", "NOTICE")
    found += [
        (p, Path(p.name))
        for p in sorted(info.iterdir())
        if p.is_file() and p.name.upper().startswith(marks)
    ]
    return found


def collect_licenses(core: Path, extra: dict[str, list[Path]]) -> None:
    """Copies the licence of every shipped part into `core/licenses/<name>/` with an index:
    each wheel's own files, Python's, and `extra` (uv, ffmpeg, Stickler itself)."""
    site = _site(core)
    if site is None:
        raise ValueError(f"no Python packages in {core}")
    parts: dict[str, tuple[str, list[tuple[Path, Path]]]] = {
        name: ("", [(file, Path(file.name)) for file in files]) for name, files in extra.items()
    }
    for name, version, info in _distributions(site):
        if name in parts:
            continue
        files = _licence_files(info)
        if not files:
            raise ValueError(f"{name} {version} ships no licence file ({info.name})")
        parts[name] = (version, files)
    parts["python"] = ("", [(p, Path(p.name)) for p in sorted(site.parent.glob("LICENSE*"))])
    out = core / "licenses"
    shutil.rmtree(out, ignore_errors=True)
    for name, (_version, files) in parts.items():
        (out / name).mkdir(parents=True)
        for file, place in files:
            if (out / name / place).exists():
                raise ValueError(f"{name} has two licence files at {place}")
            (out / name / place).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, out / name / place)
    lines = ["Stickler ships these parts; each folder here holds that part's licence.", ""]
    lines += sorted(f"{name} {version}".strip() for name, (version, _files) in parts.items())
    (out / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prune(python: Path) -> None:
    """Removes from a python-build-standalone tree what the core never runs: the test suites,
    IDLE, Tk, pip, headers, manuals and bytecode."""
    patterns = (
        "lib/python3.*/test",
        "lib/python3.*/idlelib",
        "lib/python3.*/tkinter",
        "lib/python3.*/turtledemo",
        "lib/python3.*/ensurepip",
        "lib/python3.*/lib-dynload/_tkinter*",
        "lib/python3.*/site-packages/pip",
        "lib/python3.*/site-packages/pip-*.dist-info",
        "lib/python3.*/site-packages/numpy/**/tests",
        "lib/tcl*",
        "lib/tk*",
        "lib/itcl*",
        "lib/thread*",
        "lib/libtcl*",
        "lib/libtk*",
        "include",
        "share/man",
        "bin/pip*",
        "bin/idle*",
        "bin/pydoc*",
        "bin/python*-config",
        "**/__pycache__",
    )
    for pattern in patterns:
        for path in sorted(python.glob(pattern), reverse=True):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists() or path.is_symlink():
                path.unlink()


def problems(core: Path, languages: list[str]) -> list[str]:
    """What is wrong with a bundle: a part that is missing or cannot run, and anything that
    must not ship (environments, weights, caches, pip)."""
    found = []
    for program in PROGRAMS:
        path = core / program
        if not path.is_file():
            found.append(f"missing: {program}")
        elif not path.stat().st_mode & 0o111:
            found.append(f"cannot run: {program}")
    site = _site(core)
    wanted = [f"python/share/locale/{lang}/LC_MESSAGES/stickler.mo" for lang in languages]
    wanted += [f"python/share/stickler/adapters/{a}/pyproject.toml" for a in APP_ADAPTERS]
    wanted += [f"python/share/stickler/adapters/{a}/uv.lock" for a in APP_ADAPTERS]
    wanted.append("python/share/stickler/adapters/_common/pyproject.toml")
    found += [f"missing: {rel}" for rel in wanted if not (core / rel).is_file()]
    if site is None:
        return [*found, "missing: python/lib/python3.*/site-packages"]
    for package in ("stickler", "stickler_app"):
        if not (site / package / "__init__.py").is_file():
            found.append(f"missing: {(site / package / '__init__.py').relative_to(core)}")
    licensed = [name for name, _v, _i in _distributions(site) if name not in OWN]
    for name in sorted({*licensed, *OWN, "python"}):
        folder = core / "licenses" / name
        if not folder.is_dir() or not any(folder.iterdir()):
            found.append(f"missing: licenses/{name} (no licence file)")
    for path in sorted(core.rglob("*")):
        rel = path.relative_to(core)
        if any(part in NEVER for part in rel.parts[:-1]):
            continue  # its folder is named already
        if (
            path.name in NEVER
            or path.suffix in NEVER_SUFFIXES
            or path.name == "pip"
            and path.parent == site
        ):
            found.append(f"must not ship: {rel}")
    return found


def main(argv: list[str]) -> int:
    match argv:
        case ["mo", po, mo]:
            Path(mo).parent.mkdir(parents=True, exist_ok=True)
            Path(mo).write_bytes(compile_mo(Path(po).read_text(encoding="utf-8")))
        case ["prune", python]:
            prune(Path(python))
        case ["licenses", core, *pairs]:
            extra: dict[str, list[Path]] = {}
            for pair in pairs:
                name, _, file = pair.partition("=")
                extra.setdefault(name, []).append(Path(file))
            collect_licenses(Path(core), extra)
        case ["check", core]:
            languages = (
                (Path(__file__).resolve().parents[1] / "po" / "LINGUAS")
                .read_text(encoding="utf-8")
                .split()
            )
            found = problems(Path(core), languages)
            for line in found:
                print(f"mac-bundle: {line}", file=sys.stderr)
            return 1 if found else 0
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
