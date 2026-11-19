"""The Mac app's own texts reach its String Catalog (scripts/xcstrings.py, from po/)."""

import json
import re
from pathlib import Path

from stickler_app import mac_texts

CATALOG = Path(__file__).resolve().parents[2] / "mac" / "Stickler" / "Localizable.xcstrings"
PLACEHOLDER = re.compile(r"\{\w+\}")


def _strings() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["strings"]


def _key(text: str, count: bool = False) -> str:
    """The catalog's key for a text with one placeholder at most: `%1$@`, a count `%1$lld`."""
    return PLACEHOLDER.sub("%1$lld" if count else "%1$@", text)


def test_every_mac_text_is_in_the_catalog_in_german_and_spanish():
    strings = _strings()
    assert len(set(mac_texts.TEXTS)) == len(mac_texts.TEXTS)
    for text in mac_texts.TEXTS:
        assert len(PLACEHOLDER.findall(text)) <= 1, text
        key = _key(text)
        assert key in strings, text
        assert {"de", "es"} <= set(strings[key]["localizations"]), text


def test_a_text_with_a_count_has_both_forms_in_every_language():
    strings = _strings()
    assert mac_texts.PLURALS == ("{count} pages",)  # the plural form names the entry
    for text in mac_texts.PLURALS:
        localizations = strings[_key(text, count=True)]["localizations"]
        assert {"en", "de", "es"} <= set(localizations), text
        for language in ("en", "de", "es"):
            forms = localizations[language]["variations"]["plural"]
            assert set(forms) == {"one", "other"}, (text, language)
    english = strings["%1$lld pages"]["localizations"]["en"]["variations"]["plural"]
    assert english["one"]["stringUnit"]["value"] == "%1$lld page"
    assert english["other"]["stringUnit"]["value"] == "%1$lld pages"
