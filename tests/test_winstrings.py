"""Tests for scripts/winstrings.py: po/ → the Windows app's string tables (SPEC.md, module
`win-shell`, scope 1)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("winstrings", ROOT / "scripts" / "winstrings.py")
assert _spec and _spec.loader
winstrings = importlib.util.module_from_spec(_spec)
sys.modules["winstrings"] = winstrings
_spec.loader.exec_module(winstrings)

HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
PLURAL_HEADER = HEADER + '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n'
PAGES = 'msgid "{count} page"\nmsgid_plural "{count} pages"\nmsgstr[0] ""\nmsgstr[1] ""\n'


def _tables(pot_entries: str, de_entries: str = "") -> dict:
    return winstrings.tables(HEADER + "\n" + pot_entries, {"de": PLURAL_HEADER + "\n" + de_entries})


def test_a_text_maps_its_english_to_the_translation_with_named_placeholders_kept():
    pot = 'msgid "Saved “{name}”"\nmsgstr ""\n\nmsgid "{a} of {b}"\nmsgstr ""\n'
    de = (
        'msgid "Saved “{name}”"\nmsgstr "„{name}“ gesichert"\n\n'
        'msgid "{a} of {b}"\nmsgstr "{b}: {a}"\n'
    )
    t = _tables(pot, de)
    assert t["de"] == {"Saved “{name}”": "„{name}“ gesichert", "{a} of {b}": "{b}: {a}"}
    assert t["en"] == {}  # English needs no table but for plurals


def test_a_text_with_a_count_has_both_forms_and_english_names_its_own():
    de = (
        'msgid "{count} page"\nmsgid_plural "{count} pages"\n'
        'msgstr[0] "{count} Seite"\nmsgstr[1] "{count} Seiten"\n'
    )
    t = _tables(PAGES, de)
    assert t["de"]["{count} page"] == {"one": "{count} Seite", "other": "{count} Seiten"}
    assert t["en"]["{count} page"] == {"one": "{count} page", "other": "{count} pages"}


def test_missing_and_fuzzy_translations_are_left_out():
    pot = 'msgid "A"\nmsgstr ""\n\nmsgid "B"\nmsgstr ""\n'
    de = 'msgid "A"\nmsgstr ""\n\n#, fuzzy\nmsgid "B"\nmsgstr "Be"\n'
    assert _tables(pot, de)["de"] == {}


def test_another_plural_rule_or_a_foreign_placeholder_stops_the_script():
    pl = HEADER + '"Plural-Forms: nplurals=3; plural=(n==1 ? 0 : 1);\\n"\n'
    with pytest.raises(ValueError, match="plural rule"):
        winstrings.tables(HEADER + "\n" + PAGES, {"pl": pl})
    with pytest.raises(ValueError, match="placeholder"):
        _tables(
            'msgid "Open {name}"\nmsgstr ""\n', 'msgid "Open {name}"\nmsgstr "{title} öffnen"\n'
        )


def test_the_tables_are_stable_json_ending_in_a_newline():
    text = winstrings.render({"b": "B", "a": {"other": "x", "one": "y"}})
    assert text == winstrings.render(json.loads(text))
    assert text.endswith("}\n") and text.index('"a"') < text.index('"b"')


def test_check_reports_stale_tables_and_writing_fixes_them(tmp_path):
    out = tmp_path / "Strings"
    po = ROOT / "po"
    assert winstrings.main(["--po", str(po), "--out", str(out), "--check"]) == 1
    (out / "old.json").parent.mkdir(parents=True)
    (out / "old.json").write_text("{}\n", encoding="utf-8")
    assert winstrings.main(["--po", str(po), "--out", str(out)]) == 0
    assert not (out / "old.json").exists()  # a language no longer in po/LINGUAS goes
    assert winstrings.main(["--po", str(po), "--out", str(out), "--check"]) == 0


def test_the_committed_tables_are_current():
    """po/ changed without running scripts/i18n.sh (which writes the tables) fails here."""
    assert winstrings.main(["--check"]) == 0


def test_the_projects_po_files_give_every_language_every_text():
    po = ROOT / "po"
    languages = [
        x for x in (po / "LINGUAS").read_text(encoding="utf-8").split() if not x.startswith("#")
    ]
    pot = (po / "stickler.pot").read_text(encoding="utf-8")
    t = winstrings.tables(
        pot, {lang: (po / f"{lang}.po").read_text(encoding="utf-8") for lang in languages}
    )
    keys = {e.msgid for e in winstrings._xcstrings().read_po(pot)[1] if e.msgid}
    for lang in languages:
        assert set(t[lang]) == keys, lang
