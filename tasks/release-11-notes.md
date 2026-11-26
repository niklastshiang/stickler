# Release 11: the notes' draft

Stickler for Windows, and playback and corrections on the Mac ([how to install](https://github.com/niklastshiang/stickler#-install-the-app)).

### Added
- **Stickler for Windows 11**: a native app with the same sheet music, playback, corrections, exports, backup and uninstall as on Linux and the Mac. One installer, no administrator rights; it brings everything but the models, which the app downloads after asking. The installer is not signed yet: Windows asks before it starts, and [the guide](https://github.com/niklastshiang/stickler/blob/main/docs/install-windows.md) says what to click.
- **Playback on the Mac**: play the song, the detected hits as clicks, or both, with a volume for each; a marker follows the sounding bar, and a click on a bar jumps there.
- **Corrections on the Mac**: tempo half or double, beats per bar, the first "one", Simplify and Repeat signs in an inspector beside the sheet, applied at once and remembered per song.
- The website's "A look around" shows the Mac app next to the Linux app.

### Changed
- Downloads of the models trust the system's certificates, so they work behind a company's proxy.

**Full changelog:** https://github.com/niklastshiang/stickler/compare/v10...v11
