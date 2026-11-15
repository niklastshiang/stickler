# Design of the GTK application

Mockups of every screen of the GTK application, approved by the owner on 2026-11-14 (module
`design` in [SPEC.md](../../SPEC.md#module-design), which lists the screens and the decisions).

`mockups/` holds the sources of the design canvas the screens were drawn on: one `.dc.html`
file per screen and `canvas.json` for their layout. They are a record for the GTK modules, not
code to run: the files need the canvas's runtime and render only there. The owner's canvas is
the live copy; when a screen changes there, the files here are replaced with the new export.

| File | Screen |
|---|---|
| `Setup-Consent.dc.html` | 1 · First start: consent |
| `Setup-Download.dc.html` | 2 · First start: download |
| `Setup-Error.dc.html` | 3 · First start: a server is not answering |
| `Main.dc.html` | 4 · Empty window: drop or open a song |
| `Analysing.dc.html` | 5 · Analysis with steps |
| `Sheet.dc.html` | 6 · Sheet music, playing, volume |
| `Corrections.dc.html` | 7 · Corrections sidebar |
| `Export.dc.html` | 8 · Export menu |
| `Menu.dc.html` | 9 · Main menu with the appearance switch |
| `Narrow-Sheet.dc.html` | 10 · Narrow window: sheet music |
| `Narrow-Corrections.dc.html` | 11 · Narrow window: corrections as a bottom sheet |
| `SheetPage.dc.html` | The engraved page, a stand-in for Verovio's SVG (used by 6–11) |
| `Icon-A.dc.html` … `Icon-D.dc.html` | App icon drafts A–D; B was chosen (`packaging/icons/`) |

Each screen has light and dark variants (the canvas's `dark` switch); the page is inverted in
dark mode. Fonts in the mockups: Inter stands in for Adwaita Sans.
