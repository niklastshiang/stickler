"""The Windows app's own texts reach its string tables (scripts/winstrings.py, from po/)."""

import json
from pathlib import Path

from stickler_app import win_texts

STRINGS = Path(__file__).resolve().parents[2] / "win" / "Stickler" / "Strings"


def test_every_windows_text_is_in_the_german_and_spanish_tables():
    assert len(set(win_texts.TEXTS)) == len(win_texts.TEXTS)
    for language in ("de", "es"):
        table = json.loads((STRINGS / f"{language}.json").read_text(encoding="utf-8"))
        for text in win_texts.TEXTS:
            assert table.get(text), (language, text)
