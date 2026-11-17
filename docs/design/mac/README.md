# Design of the Mac app

Mockups of every screen of the Mac app's first version, approved by the owner on 2026-11-17
(module `mac-design` in [SPEC.md](../../../SPEC.md#module-mac-design), which lists the screens
and the decisions).

The files are the sources of the Mac design canvas: one `.dc.html` file per screen and
`canvas.json` for their layout. They are a record for the Mac modules, not code to run: they need
the canvas's runtime and render only there. The owner's canvas (separate from the GTK one) is the
live copy; when a screen changes there, the files here are replaced with the new export.

| File | Screen |
|---|---|
| `Setup-Consent.dc.html` | M1 · First start: consent (a sheet over the empty window) |
| `Setup-Download.dc.html` | M2 · First start: download |
| `Setup-Error.dc.html` | M3 · First start: a server is not answering |
| `Main.dc.html`, `Main-Dark.dc.html` | M4 · Empty window: drop or open a song, recent songs (light, dark) |
| `Analysing.dc.html` | M5 · Analysis with steps |
| `Sheet.dc.html`, `Sheet-Dark.dc.html` | M6 · Sheet music (light, dark; no bar marker: no playback yet) |
| `Export-Menu.dc.html` | M7 · Export menu |
| `Export-Saved.dc.html` | M7 · Saved, with "Show in Finder" |
| `Menu-App.dc.html`, `Menu-File.dc.html`, `Menu-View.dc.html` | M8 · Menu bar: Stickler, File, View |
| `Icon.dc.html` | The macOS app icon (default, dark, small sizes) |
| `SheetPage.dc.html` | The engraved page, shared with the GTK mockups (Mac accent, marker off) |

The dark boards import the light ones with `dark` on; `Menu-File` and `Menu-View` import
`Menu-App` with another menu open. Inter stands in for SF Pro on the canvas.
