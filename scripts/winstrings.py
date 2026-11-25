"""Writes the Windows app's string tables from po/ (SPEC.md, module `win-shell`).

`po/*.po` stays the only place to translate; this turns it into one JSON table per language,
`win/Stickler/Strings/<lang>.json`, which the app's `Strings` class reads. A table maps the
English text to its translation; named placeholders (`{name}`, `{size:n}`) stay as they are,
and the app fills them by name. A text with a count maps its English singular to `one` and
`other`; `en.json` holds those English forms, since the English text alone names only one of
them. A language with a plural rule other than `n != 1` stops the script instead of guessing;
a translation that uses a placeholder its English text does not have stops it too. Missing and
fuzzy translations are left out (the app shows English, as gettext does).

    uv run python scripts/winstrings.py            # write win/Stickler/Strings/*.json
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


def render(table: dict) -> str:
    return json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--po", type=Path, default=PO)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true", help="exit 1 if the files are not current")
    args = parser.parse_args(argv)
    languages = [
        line.strip()
        for line in (args.po / "LINGUAS").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    wanted = {
        f"{lang}.json": render(table)
        for lang, table in tables(
            (args.po / "stickler.pot").read_text(encoding="utf-8"),
            {lang: (args.po / f"{lang}.po").read_text(encoding="utf-8") for lang in languages},
        ).items()
    }
    present = {p.name: p.read_text(encoding="utf-8") for p in sorted(args.out.glob("*.json"))}
    if args.check:
        if present != wanted:
            print(f"{args.out} is not current: run scripts/winstrings.py", file=sys.stderr)
            return 1
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name in set(present) - set(wanted):
        (args.out / name).unlink()
    for name, text in wanted.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"{args.out}: {', '.join(sorted(wanted))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
