"""Texts only the Mac app shows (SPEC.md, module `mac-shell`). They live here so that
`scripts/i18n.sh` collects them into `po/` with every other text and `scripts/xcstrings.py`
puts them into the Mac app's String Catalog: `po/` stays the one place to translate. Python
never shows them; everything the core says arrives translated already."""

from stickler_app.i18n import N_, ngettext

TEXTS = (
    # Translators: Mac app, what VoiceOver reads for the sheet music, which is one picture
    # to it; the page count follows ("Sheet music of Eye of the Tiger, 3 pages")
    N_("Sheet music of {title}"),
    # Translators: Mac app, File menu
    N_("Open Recent"),
    # Translators: Mac app, File › Open Recent: forget every recent song
    N_("Clear Menu"),
    # Translators: Mac app, Help menu
    N_("Stickler Help"),
    # Translators: Mac app, Help menu: opens the folder with the licences of the programs
    # that come inside the app (Python, uv, ffmpeg and others)
    N_("Licences"),
    # Translators: Mac app, under "Writing the Drum Part" (design screen M5)
    N_("Takes about 15 seconds"),
    # Translators: Mac app, a step that is running now (next to "Done" and "Waiting")
    N_("Running"),
    # Translators: Mac app, the page shown when the app's Python core has ended
    N_("Stickler Stopped Unexpectedly"),
    N_(
        "The part of Stickler that listens to the songs has ended. A song it was writing has "
        "to be opened again; finished ones are kept."
    ),
    N_("Start Again"),
    # Translators: Mac app, the bar after saving a file (design screen M7)
    N_("Show in Finder"),
    # Translators: Mac app, File menu (⌘W) on the empty window
    N_("Close Window"),
    # Translators: Mac app, View menu (⌘0): the note size back to 100 %, next to "Zoom In"
    # and "Zoom Out"; macOS calls it "Originalgröße" in German, "Tamaño real" in Spanish
    N_("Actual Size"),
)

# Texts with a count: the String Catalog holds both forms under the plural one, and Swift
# picks by the count. `ngettext` only marks them for `scripts/i18n.sh`.
PLURALS = (
    # Translators: Mac app, VoiceOver, after "Sheet music of …": how many pages it has
    ngettext("{count} page", "{count} pages", 2),
)
