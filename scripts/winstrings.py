"""Writes the Windows app's string tables from po/ (SPEC.md, module `win-shell`).

`po/*.po` stays the only place to translate; this turns it into one JSON table per language,
`win/Stickler/Strings/<lang>.json`, which the app's `Strings` class reads. A table maps the
English text to its translation; named placeholders (`{name}`, `{size:n}`) stay as they are,
and the app fills them by name. A text with a count maps its English singular to `one` and
`other`; `en.json` holds those English forms, since the English text alone names only one of
them. A language with a plural rule other than `n != 1` stops the script instead of guessing;
a translation that uses a placeholder its English text does not have stops it too. Missing and
fuzzy translations are left out (the app shows English, as gettext does).

The installer's and the uninstaller's own texts (SPEC.md, module `win-package`, scopes 3 and
4) come from po/ the same way: `win/installer/Messages.iss`, included by the Inno Setup
script, sets Inno's messages and Stickler's custom messages for each language Inno knows.

    uv run python scripts/winstrings.py            # write the tables and Messages.iss
    uv run python scripts/winstrings.py --check    # exit 1 when those files are not current
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PO = ROOT / "po"
OUT = ROOT / "win" / "Stickler" / "Strings"
INSTALLER = ROOT / "win" / "installer" / "Messages.iss"
# the name of each language of po/LINGUAS in the installer script's [Languages]
INNO_LANGUAGES = {"en": "english", "de": "german", "es": "spanish"}
WINDOWS_11 = "Stickler needs Windows 11 on a PC with an Intel or AMD processor (x64)."
# (section, Inno's or Stickler's message name, the texts it is made of, joined by a blank line)
INSTALLER_TEXTS = (
    # Windows 10 (MinVersion) and ARM64 (ArchitecturesAllowed) both stop with it
    ("Messages", "WindowsVersionNotSupported", (WINDOWS_11,)),
    ("Messages", "OnlyOnTheseArchitectures", (WINDOWS_11,)),
    # the uninstaller's own Yes/No question, asked unless it runs silently
    (
        "Messages",
        "ConfirmUninstall",
        (
            "Uninstall Stickler?",
            "This removes Stickler, its models and the saved analyses. Your songs and exports "
            "stay.",
        ),
    ),
    (
        "CustomMessages",
        "RemoveSettings",
        ("Also remove your settings, recent songs and corrections?",),
    ),
    (
        "CustomMessages",
        "DataNotRemoved",
        (
            "Not all of Stickler’s data could be removed. You can delete the folder yourself: "
            "{folder}",
        ),
    ),
)


def _xcstrings():
    """The .po reader of scripts/xcstrings.py, so both apps read po/ the same way."""
    if "xcstrings" not in sys.modules:
        spec = importlib.util.spec_from_file_location("xcstrings", ROOT / "scripts/xcstrings.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["xcstrings"] = module  # needed for @dataclass
        spec.loader.exec_module(module)
    return sys.modules["xcstrings"]


def _names(text: str) -> set[str]:
    return set(_xcstrings().PLACEHOLDER.findall(text))


def tables(pot: str, translations: dict[str, str]) -> dict[str, dict]:
    """Each language's table, `en` included, for the template `pot` and each .po text."""
    xc = _xcstrings()
    source = [e for e in xc.read_po(pot)[1] if e.msgid]
    out: dict[str, dict] = {
        "en": {e.msgid: {"one": e.msgid, "other": e.msgid_plural} for e in source if e.msgid_plural}
    }
    for lang, text in sorted(translations.items()):
        header, entries = xc.read_po(text)
        if header.get("Plural-Forms", xc.SUPPORTED_PLURALS) != xc.SUPPORTED_PLURALS:
            raise ValueError(f"{lang}: plural rule {header['Plural-Forms']!r} is not supported")
        found = {(e.msgid, e.msgid_plural): e for e in entries}
        table: dict = {}
        for entry in source:
            done = found.get((entry.msgid, entry.msgid_plural))
            if done is None or "fuzzy" in done.flags or not all(done.msgstr):
                continue
            allowed = _names(entry.msgid) | _names(entry.msgid_plural or "")
            for translated in done.msgstr:
                if not _names(translated) <= allowed:
                    raise ValueError(
                        f"{lang}: {translated!r} names a placeholder {entry.msgid!r} lacks"
                    )
            if entry.msgid_plural is None:
                table[entry.msgid] = done.msgstr[0]
            else:
                table[entry.msgid] = {"one": done.msgstr[0], "other": done.msgstr[1]}
        out[lang] = table
    return out


def inno_text(text: str, english: str) -> str:
    """A text as an Inno Setup message: one line, each placeholder as `%1`, `%2`… numbered in
    the order of the English text, which is the order the script passes the values in."""
    pattern = _xcstrings().PLACEHOLDER
    order = list(dict.fromkeys(pattern.findall(english)))
    return pattern.sub(lambda m: f"%{order.index(m.group(1)) + 1}", text).replace("\n", "%n")


def installer_messages(languages: dict[str, dict]) -> str:
    """`Messages.iss` from the tables: each text in each language Inno has a name for, English
    where a translation is missing (as gettext does)."""
    unknown = sorted(set(languages) - set(INNO_LANGUAGES))
    if unknown:
        raise ValueError(f"no Inno Setup language for {', '.join(unknown)}: add it to the script")
    lines = ["; Generated by scripts/winstrings.py from po/ (SPEC.md, `win-package`): do not edit."]
    for section in ("Messages", "CustomMessages"):
        lines += ["", f"[{section}]"]
        for kind, name, texts in INSTALLER_TEXTS:
            if kind != section:
                continue
            for lang in sorted(languages, key=lambda code: (code != "en", code)):
                table = languages[lang]
                parts = [inno_text(table.get(text) or text, text) for text in texts]
                lines.append(f"{INNO_LANGUAGES[lang]}.{name}={'%n%n'.join(parts)}")
    return "﻿" + "\n".join(lines) + "\n"  # Inno reads UTF-8 by its byte order mark


def render(table: dict) -> str:
    return json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--po", type=Path, default=PO)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--installer", type=Path, default=INSTALLER)
    parser.add_argument("--check", action="store_true", help="exit 1 if the files are not current")
    args = parser.parse_args(argv)
    languages = [
        line.strip()
        for line in (args.po / "LINGUAS").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    made = tables(
        (args.po / "stickler.pot").read_text(encoding="utf-8"),
        {lang: (args.po / f"{lang}.po").read_text(encoding="utf-8") for lang in languages},
    )
    wanted = {f"{lang}.json": render(table) for lang, table in made.items()}
    messages = installer_messages(made)
    present = {p.name: p.read_text(encoding="utf-8") for p in sorted(args.out.glob("*.json"))}
    if args.check:
        stale = [args.out] if present != wanted else []
        if not args.installer.is_file() or args.installer.read_text(encoding="utf-8") != messages:
            stale.append(args.installer)
        for path in stale:
            print(f"{path} is not current: run scripts/winstrings.py", file=sys.stderr)
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name in set(present) - set(wanted):
        (args.out / name).unlink()
    for name, text in wanted.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
    args.installer.parent.mkdir(parents=True, exist_ok=True)
    args.installer.write_bytes(messages.encode())
    print(f"{args.out}: {', '.join(sorted(wanted))}; {args.installer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
