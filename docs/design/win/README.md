# Design of the Windows app

Mockups of every screen of the Windows app's first version, approved by the owner on 2026-11-24
(module `win-design` in [SPEC.md](../../../SPEC.md#module-win-design), which lists the screens
and the decisions).

The files are the sources of the Windows design canvas: one `.dc.html` file per screen and
`canvas.json` for their layout. They are a record for the Windows modules, not code to run: they
need the canvas's runtime and render only there. The owner's canvas (separate from the GTK and
Mac ones) is the live copy; when a screen changes there, the files here are replaced with the new
export.

| File | Screen |
|---|---|
| `Setup-Consent.dc.html` | W1 · First start: consent (a dialog over the empty window) |
| `Setup-Download.dc.html` | W2 · First start: download |
| `Setup-Error.dc.html` | W3 · First start: a server is not answering |
| `Main.dc.html`, `Main-Dark.dc.html` | W4 · Empty window: drop or open a song, recent songs (light, dark) |
| `Analysing.dc.html` | W5 · Analysis with steps |
| `Sheet.dc.html`, `Sheet-Dark.dc.html` | W6 · Sheet music (light, dark; no bar marker: no playback yet) |
| `Export-Menu.dc.html` | W7 · Export menu |
| `Export-Saved.dc.html` | W7 · Saved, with "Show in Folder" |
| `Menu-File.dc.html`, `Menu-View.dc.html`, `Menu-Help.dc.html` | W8 · Menu bar: File, View, Help |
| `About.dc.html` | W8 · About Stickler |
| `SheetPage.dc.html` | The engraved page, shared with the GTK and Mac mockups (Windows accent, marker off) |

The dark boards import the light ones with `dark` on; the menu boards import `Sheet` with one
menu's title marked. Inter stands in for Segoe UI Variable on the canvas where it is missing, and
the icon in the title bar and in About is a simplified stand-in for the app icon.
