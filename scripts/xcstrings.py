"""Writes the Mac app's String Catalog from po/ (SPEC.md, module `shared-core`).

`po/*.po` stays the only place to translate; this turns it into `Localizable.xcstrings`, the
JSON file Xcode reads. Named placeholders become positional ones in order of first appearance
(`{reason}` → `%1$@`, the count of a plural → `%1$lld`), so a translation that reorders them
stays right; a literal `%` in such a text becomes `%%`. Plurals become `one`/`other`; a language
with another plural rule stops the script instead of guessing. Missing and fuzzy translations
are left out (the app shows English, as gettext does).

    uv run python scripts/xcstrings.py            # write mac/Stickler/Localizable.xcstrings
    uv run python scripts/xcstrings.py --check    # exit 1 when that file is not current
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PO = ROOT / "po"
OUT = ROOT / "mac" / "Stickler" / "Localizable.xcstrings"
PLACEHOLDER = re.compile(r"\{(\w+)(?::[^}]*)?\}")
SUPPORTED_PLURALS = "nplurals=2; plural=(n != 1);"


@dataclass
class Entry:
    msgid: str = ""
    msgid_plural: str | None = None
    msgstr: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)


def _unquote(line: str) -> str:
    return ast.literal_eval(line.strip())


def read_po(text: str) -> tuple[dict[str, str], list[Entry]]:
    """The header's fields and the entries (without the header) of a .po or .pot file."""
    entries, current, target = [], Entry(), None
    for raw in [*text.splitlines(), ""]:
        line = raw.strip()
        if not line:
            if target is not None:
                entries.append(current)
            current, target = Entry(), None
        elif line.startswith("#."):
            current.comments.append(line[2:].strip())
        elif line.startswith("#,"):
            current.flags.update(f.strip() for f in line[2:].split(","))
        elif line.startswith("#"):
            continue
        elif line.startswith('"'):
            value = _unquote(line)
            if target == "msgid":
                current.msgid += value
            elif target == "msgid_plural":
                current.msgid_plural = (current.msgid_plural or "") + value
            else:
                current.msgstr[-1] += value
        else:
            keyword, _, rest = line.partition(" ")
            value = _unquote(rest)
            if keyword == "msgid":
                target, current.msgid = "msgid", value
            elif keyword == "msgid_plural":
                target, current.msgid_plural = "msgid_plural", value
            else:  # msgstr or msgstr[n]
                target = "msgstr"
                current.msgstr.append(value)
    header: dict[str, str] = {}
    if entries and entries[0].msgid == "":
        for row in entries.pop(0).msgstr[0].splitlines():
            name, _, value = row.partition(":")
            header[name.strip()] = value.strip()
    return header, entries


def _order(entry: Entry) -> list[str]:
    """Placeholder names in order of first appearance, singular then plural."""
    names: list[str] = []
    for text in (entry.msgid, entry.msgid_plural or ""):
        for name in PLACEHOLDER.findall(text):
            if name not in names:
                names.append(name)
    return names


def _convert(text: str, order: list[str], count: str | None) -> str:
    if not order:
        return text

    def positional(match: re.Match) -> str:
        name = match.group(1)
        return f"%{order.index(name) + 1}${'lld' if name == count else '@'}"

    parts = PLACEHOLDER.split(text)  # text, name, text, name, …
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(positional(re.match(r"(\w+)", part)))
        else:
            out.append(part.replace("%", "%%"))
    return "".join(out)


def _unit(value: str) -> dict:
    return {"stringUnit": {"state": "translated", "value": value}}


def _plural(one: str, other: str) -> dict:
    return {"variations": {"plural": {"one": _unit(one), "other": _unit(other)}}}


def catalog(pot: str, translations: dict[str, str]) -> dict:
    """The String Catalog for the template `pot` and each language's .po text."""
    read = {}
    for lang, text in sorted(translations.items()):
        header, entries = read_po(text)
        if header.get("Plural-Forms", SUPPORTED_PLURALS) != SUPPORTED_PLURALS:
            raise ValueError(f"{lang}: plural rule {header['Plural-Forms']!r} is not supported")
        read[lang] = {(e.msgid, e.msgid_plural): e for e in entries}
    strings = {}
    for entry in read_po(pot)[1]:
        order = _order(entry)
        count = None
        if entry.msgid_plural is not None:
            if len(order) != 1:
                raise ValueError(f"{entry.msgid!r}: a plural needs exactly one placeholder")
            count = order[0]
        source = entry.msgid_plural if count else entry.msgid
        key = _convert(source, order, count)
        localizations = {}
        if count:
            localizations["en"] = _plural(
                _convert(entry.msgid, order, count), _convert(entry.msgid_plural, order, count)
            )
        for lang, found in read.items():
            done = found.get((entry.msgid, entry.msgid_plural))
            if done is None or "fuzzy" in done.flags or not all(done.msgstr):
                continue
            texts = [_convert(t, order, count) for t in done.msgstr]
            localizations[lang] = _plural(texts[0], texts[1]) if count else _unit(texts[0])
        value = {"extractionState": "manual", "localizations": localizations}
        if entry.comments:
            value["comment"] = " ".join(entry.comments)
        strings[key] = value
    return {"sourceLanguage": "en", "strings": strings, "version": "1.0"}


def render(data: dict) -> str:
    """JSON as Xcode writes it, so a later save in Xcode changes little."""
    return (
        json.dumps(data, indent=2, separators=(",", " : "), sort_keys=True, ensure_ascii=False)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--po", type=Path, default=PO)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is not current")
    args = parser.parse_args(argv)
    languages = [
        line.strip()
        for line in (args.po / "LINGUAS").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    text = render(
        catalog(
            (args.po / "stickler.pot").read_text(encoding="utf-8"),
            {lang: (args.po / f"{lang}.po").read_text(encoding="utf-8") for lang in languages},
        )
    )
    current = args.out.read_text(encoding="utf-8") if args.out.exists() else None
    if args.check:
        if current != text:
            print(f"{args.out} is not current: run scripts/xcstrings.py", file=sys.stderr)
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(json.loads(text)['strings'])} texts, {', '.join(languages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
