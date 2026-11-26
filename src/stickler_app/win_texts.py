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
    # Translators: Windows app, the menu bar (design screen W8); Windows says "Datei" in
    # German, "Archivo" in Spanish
    N_("File"),
    # Translators: Windows app, the menu bar (design screen W8); Windows says "Hilfe" in
    # German, "Ayuda" in Spanish
    N_("Help"),
    # Translators: Windows app, the menu bar (design screen W8) with the note size's entries;
    # Windows says "Ansicht" in German, "Ver" in Spanish
    N_("View"),
    # Translators: Windows app, the menu bar (design screen W10) with Play, Previous Bar and
    # what to hear; Windows' Media Player says "Wiedergabe" in German, "Reproducción" in Spanish
    N_("Playback"),
    # Translators: Windows app, corrections pane (design screen W11): what Narrator and the
    # tooltip call the two step buttons beside "Beats per bar"
    N_("One beat more"),
    N_("One beat fewer"),
    # Translators: Windows app, corrections pane (design screen W11): what Narrator and the
    # tooltip call the two step buttons beside "First “one”": the first "one" moves by a beat
    N_("One beat later"),
    N_("One beat earlier"),
    # Translators: Windows installer, shown on Windows 10 or a PC with an ARM processor, where
    # it installs nothing (SPEC.md, module `win-package`)
    N_("Stickler needs Windows 11 on a PC with an Intel or AMD processor (x64)."),
    # Translators: Windows uninstaller (Settings › Apps), below "Uninstall Stickler?"; "Yes"
    # uninstalls, "No" changes nothing
    N_("This removes Stickler, its models and the saved analyses. Your songs and exports stay."),
    # Translators: Windows uninstaller, the second question after "Uninstall Stickler?"; "No"
    # (the default) keeps them, so a new install picks up where the user left off
    N_("Also remove your settings, recent songs and corrections?"),
    # Translators: Windows uninstaller, when a file of Stickler's could not be deleted (it is
    # in use); {folder} is the folder under AppData
    N_("Not all of Stickler’s data could be removed. You can delete the folder yourself: {folder}"),
    # Translators: Windows app, after "Uninstall Stickler…" removed the data but Windows (or an
    # antivirus) did not let the uninstaller start; Settings › Apps is Windows' own page
    N_("Stickler’s data is removed. Remove the program later in Settings › Apps."),
)
