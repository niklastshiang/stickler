"""Tests for scripts/xcstrings.py: po/ → the Mac app's String Catalog (SPEC.md, module
`shared-core`, scope 5)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("xcstrings", ROOT / "scripts" / "xcstrings.py")
assert _spec and _spec.loader
xcstrings = importlib.util.module_from_spec(_spec)
sys.modules["xcstrings"] = xcstrings  # needed for @dataclass
_spec.loader.exec_module(xcstrings)

HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
PLURAL_HEADER = HEADER + '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n'


def _catalog(pot_entries: str, de_entries: str = "") -> dict:
    pot = HEADER + "\n" + pot_entries
    de = PLURAL_HEADER + "\n" + de_entries
    return xcstrings.catalog(pot, {"de": de})


def _unit(catalog: dict, key: str, lang: str) -> str:
    return catalog["strings"][key]["localizations"][lang]["stringUnit"]["value"]


def test_a_plain_text_keeps_its_english_key_and_gets_its_translation():
    c = _catalog('msgid "Open a Song"\nmsgstr ""\n', 'msgid "Open a Song"\nmsgstr "Song öffnen"\n')
    assert _unit(c, "Open a Song", "de") == "Song öffnen"
    assert c["strings"]["Open a Song"]["extractionState"] == "manual"
    assert c["sourceLanguage"] == "en" and c["version"] == "1.0"


def test_named_placeholders_become_positional_and_a_reordered_translation_stays_right():
    c = _catalog(
        'msgid "{done} of {total}"\nmsgstr ""\n',
        'msgid "{done} of {total}"\nmsgstr "von {total}: {done}"\n',
    )
    assert _unit(c, "%1$@ of %2$@", "de") == "von %2$@: %1$@"


def test_a_format_spec_is_dropped_since_the_core_formats_the_value():
    c = _catalog('msgid "{size:n} MB"\nmsgstr ""\n', 'msgid "{size:n} MB"\nmsgstr "{size:n} MB"\n')
    assert _unit(c, "%1$@ MB", "de") == "%1$@ MB"


def test_a_literal_percent_is_escaped_only_where_the_text_is_a_format():
    c = _catalog(
        'msgid "{percent}%"\nmsgstr ""\n\nmsgid "%-d %B"\nmsgstr ""\n',
        'msgid "{percent}%"\nmsgstr "{percent}\u00a0%"\n\nmsgid "%-d %B"\nmsgstr "%-d. %B"\n',
    )
    assert _unit(c, "%1$@%%", "de") == "%1$@\u00a0%%"
    assert _unit(c, "%-d %B", "de") == "%-d. %B"


def test_a_plural_is_keyed_by_its_plural_form_with_the_count_as_a_number():
    pot = 'msgid "one model"\nmsgid_plural "{count} models"\nmsgstr[0] ""\nmsgstr[1] ""\n'
    de = (
        'msgid "one model"\nmsgid_plural "{count} models"\n'
        'msgstr[0] "ein Modell"\nmsgstr[1] "{count} Modelle"\n'
    )
    c = _catalog(pot, de)
    entry = c["strings"]["%1$lld models"]["localizations"]
    plural = entry["de"]["variations"]["plural"]
    assert plural["one"]["stringUnit"]["value"] == "ein Modell"
    assert plural["other"]["stringUnit"]["value"] == "%1$lld Modelle"
    english = entry["en"]["variations"]["plural"]
    assert english["one"]["stringUnit"]["value"] == "one model"
    assert english["other"]["stringUnit"]["value"] == "%1$lld models"


def test_a_plural_needs_exactly_one_placeholder_the_count():
    pot = 'msgid "{a} of {b}"\nmsgid_plural "{a} of {b}s"\nmsgstr[0] ""\nmsgstr[1] ""\n'
    with pytest.raises(ValueError, match="one placeholder"):
        _catalog(pot)


def test_a_language_with_another_plural_rule_stops_the_script():
    pot = HEADER + '\nmsgid "x"\nmsgstr ""\n'
    pl = HEADER + '"Plural-Forms: nplurals=3; plural=(n==1 ? 0 : 1);\\n"\n'
    with pytest.raises(ValueError, match="pl: plural rule"):
        xcstrings.catalog(pot, {"pl": pl})


def test_translators_comments_go_with_the_entry():
    pot = '#. Translators: a percentage\n#: src/x.py:3\nmsgid "{p}%"\nmsgstr ""\n'
    c = _catalog(pot)
    assert c["strings"]["%1$@%%"]["comment"] == "Translators: a percentage"


def test_missing_and_fuzzy_translations_are_left_out():
    pot = 'msgid "A"\nmsgstr ""\n\nmsgid "B"\nmsgstr ""\n'
    de = 'msgid "A"\nmsgstr ""\n\n#, fuzzy\nmsgid "B"\nmsgstr "Be"\n'
    c = _catalog(pot, de)
    assert c["strings"]["A"].get("localizations", {}) == {}
    assert c["strings"]["B"].get("localizations", {}) == {}


def test_texts_over_several_lines_and_escapes_are_read_whole():
    pot = 'msgid ""\n"Say \\"hi\\"\\n"\n"twice"\nmsgstr ""\n'
    c = _catalog(pot)
    assert 'Say "hi"\ntwice' in c["strings"]


def test_the_output_is_stable_and_shaped_like_xcodes():
    c = _catalog('msgid "B"\nmsgstr ""\n\nmsgid "A"\nmsgstr ""\n')
    text = xcstrings.render(c)
    assert text == xcstrings.render(json.loads(text))
    assert text.endswith("}\n")
    assert '"sourceLanguage" : "en"' in text
    assert text.index('"A"') < text.index('"B"')


def test_check_reports_a_stale_catalog_and_writing_fixes_it(tmp_path):
    out = tmp_path / "Localizable.xcstrings"
    po = ROOT / "po"
    assert xcstrings.main(["--po", str(po), "--out", str(out), "--check"]) == 1
    assert xcstrings.main(["--po", str(po), "--out", str(out)]) == 0
    assert xcstrings.main(["--po", str(po), "--out", str(out), "--check"]) == 0


def test_the_projects_po_files_convert_with_every_text_and_language():
    po = ROOT / "po"
    pot = (po / "stickler.pot").read_text(encoding="utf-8")
    languages = [x for x in (po / "LINGUAS").read_text().split() if not x.startswith("#")]
    c = xcstrings.catalog(
        pot, {lang: (po / f"{lang}.po").read_text(encoding="utf-8") for lang in languages}
    )
    entries = [e for e in xcstrings.read_po(pot)[1] if e.msgid]
    assert len(c["strings"]) == len(entries)
    for key, value in c["strings"].items():
        assert set(value["localizations"]) >= set(languages), key


def test_the_committed_catalog_is_current():
    assert xcstrings.main(["--check"]) == 0
