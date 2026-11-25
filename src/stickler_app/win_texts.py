"""Texts only the Windows app shows (SPEC.md, module `win-shell`). They live here so that
`scripts/i18n.sh` collects them into `po/` with every other text and `scripts/winstrings.py`
puts them into the Windows app's string tables: `po/` stays the one place to translate. Python
never shows them; everything the core says arrives translated already. Texts the Mac app
already brought into `po/` (`mac_texts.py`) are used by the Windows app as they are."""

from stickler_app.i18n import N_

TEXTS = (
    # Translators: Windows app, the note after saving a file (design screen W7): opens Explorer
    # with the file selected; Chrome says "In Ordner anzeigen" in German, "Mostrar en carpeta"
    # in Spanish
    N_("Show in Folder"),
    # Translators: Windows app, the last entry of the File menu (design screen W8): ends the app
    N_("Exit"),
)
