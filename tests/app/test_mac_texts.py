"""The Mac app's own texts reach its String Catalog (scripts/xcstrings.py, from po/)."""

import json
from pathlib import Path

from stickler_app import mac_texts

CATALOG = Path(__file__).resolve().parents[2] / "mac" / "Stickler" / "Localizable.xcstrings"


def test_every_mac_text_is_in_the_catalog_in_german_and_spanish():
    strings = json.loads(CATALOG.read_text(encoding="utf-8"))["strings"]
    assert len(set(mac_texts.TEXTS)) == len(mac_texts.TEXTS)
    for text in mac_texts.TEXTS:
        assert text in strings, text
        assert {"de", "es"} <= set(strings[text]["localizations"]), text
