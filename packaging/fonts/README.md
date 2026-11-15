# Fonts shipped with the GTK application

| File | Source | Licence |
|---|---|---|
| `Leipzig.ttf` | Verovio, tag `version-6.4.1`, `fonts/Leipzig/Leipzig.ttf` (SHA-256 `77914189fbc8c2a74beb33a0098002a62524616caa45e9ddc27155fc5a373e6f`) | SIL Open Font License 1.1, see `OFL.txt` |
| `OFL.txt` | `rism-digital/leipzig`, commit `a8838c6fe6bf3aaf4bfb5d831436b4f7594dbf9c`, `LICENSE.txt` | – |

Leipzig is Verovio's default music font. The app needs it as a system font because librsvg,
which draws Verovio's SVG, finds fonts through fontconfig only; without it the tempo mark
("♩ = 109") is drawn with a wrong glyph (checked 2026-11-15, SPEC.md module `sheet-view`).
`scripts/gtk.sh` makes it visible in development; the Flatpak installs it to
`/app/share/fonts`. Change it only together with the Verovio version.
