"""Every text the app shows is translatable, extracted and translated into German."""

import ast
import gettext
import struct
from pathlib import Path

from stickler_gtk import i18n

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "stickler_gtk"
PO = ROOT / "po"

# Widget properties and setters that put text in front of the user
TEXT_KWARGS = {
    "label",
    "title",
    "subtitle",
    "description",
    "tooltip_text",
    "placeholder_text",
    "heading",
    "body",
}
TEXT_SETTERS = {f"set_{name}" for name in TEXT_KWARGS}
MARKERS = {"_", "N_"}


def _is_marked(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in MARKERS
    )


def _is_literal_text(node: ast.expr) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value != ""


def untranslated(source: str) -> list[int]:
    """Lines where a literal text reaches a widget without _() or N_()."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        values = [kw.value for kw in node.keywords if kw.arg in TEXT_KWARGS]
        if isinstance(node.func, ast.Attribute) and node.func.attr in TEXT_SETTERS:
            values += node.args[:1]
        lines += [v.lineno for v in values if _is_literal_text(v) and not _is_marked(v)]
    return lines


def marked_strings(source: str) -> set[str]:
    """The literal arguments of _() and N_()."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if _is_marked(node) and node.args and isinstance(node.args[0], ast.Constant):
            found.add(node.args[0].value)
    return found


def _po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """msgid → (msgstr, fuzzy) of a .po/.pot file (single forms, as the app uses)."""
    entries, fuzzy, key, msgid, msgstr = {}, False, None, [], []

    def flush() -> None:
        nonlocal fuzzy, key, msgid, msgstr
        if msgid:
            entries["".join(msgid)] = ("".join(msgstr), fuzzy)
        fuzzy, key, msgid, msgstr = False, None, [], []

    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("msgid "):
            key = msgid
            msgid.append(ast.literal_eval(line[6:]))
        elif line.startswith("msgstr "):
            key = msgstr
            msgstr.append(ast.literal_eval(line[7:]))
        elif line.startswith('"') and key is not None:
            key.append(ast.literal_eval(line))
    return entries


def _sources() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in sorted(APP.rglob("*.py"))}


def test_the_checker_finds_literal_texts_and_accepts_marked_ones():
    source = (
        'Gtk.Button(label="Open")\n'
        'Adw.StatusPage(title=_("Drop"), description=f"{n} songs")\n'
        'row.set_subtitle("x")\n'
        'Gtk.Label(label=name, css_classes=["dim"])\n'
    )
    assert untranslated(source) == [1, 2, 3]
    assert marked_strings('_("Drop")\nN_("Later")\nprint("no")') == {"Drop", "Later"}


def test_every_text_the_app_shows_is_marked_for_translation():
    found = {
        str(path.relative_to(ROOT)): lines
        for path, text in _sources().items()
        if (lines := untranslated(text))
    }
    assert found == {}, f"texts without _(): {found} (wrap them, then run scripts/i18n.sh)"


def test_the_template_holds_every_marked_string():
    marked = set().union(*(marked_strings(text) for text in _sources().values()))
    assert marked, "no string is marked for translation yet"
    template = set(_po_entries(PO / "stickler.pot")) - {""}
    assert marked - template == set(), "po/stickler.pot is out of date: run scripts/i18n.sh"


def test_german_translates_every_string_of_the_template():
    template = set(_po_entries(PO / "stickler.pot")) - {""}
    german = _po_entries(PO / "de.po")
    missing = sorted(m for m in template if m not in german or not german[m][0] or german[m][1])
    assert missing == [], f"po/de.po lacks or has fuzzy translations: {missing}"


def _write_mo(path: Path, messages: dict[str, str]) -> None:
    """A minimal GNU .mo file (the format msgfmt writes), with the UTF-8 header entry."""
    messages = {"": "Content-Type: text/plain; charset=UTF-8\n", **messages}
    keys = sorted(messages)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(messages[k].encode() + b"\0" for k in keys)
    start = 7 * 4 + 16 * len(keys)
    offsets, pos = [], 0
    for k in keys:
        offsets.append((len(k.encode()), start + pos))
        pos += len(k.encode()) + 1
    trans, pos = [], 0
    for k in keys:
        trans.append((len(messages[k].encode()), start + len(ids) + pos))
        pos += len(messages[k].encode()) + 1
    header = struct.pack("Iiiiiii", 0x950412DE, 0, len(keys), 28, 28 + 8 * len(keys), 0, 0)
    table = b"".join(struct.pack("ii", *o) for o in offsets + trans)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + table + ids + strs)


def test_the_app_speaks_the_language_it_finds(tmp_path, monkeypatch):
    _write_mo(tmp_path / "de" / "LC_MESSAGES" / "stickler.mo", {"Open a Song…": "Song öffnen …"})
    monkeypatch.setenv("LANGUAGE", "de")
    i18n.setup(tmp_path)
    assert i18n._("Open a Song…") == "Song öffnen …"
    assert i18n._("not translated") == "not translated"
    assert i18n.N_("Later") == "Later"  # only marks the string
    monkeypatch.setenv("LANGUAGE", "fr")
    i18n.setup(tmp_path)  # no French catalogue: English stays
    assert i18n._("Open a Song…") == "Open a Song…"
    i18n.setup(tmp_path / "missing")
    assert isinstance(i18n.translation(), gettext.NullTranslations)
