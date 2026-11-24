# Intent: a Windows app for Stickler

Confirmed by the owner on 2026-11-24 (interview). The spec is SPEC.md, "Release 11 (proposed):
Windows app".

- **Outcome:** a native Windows app built like the Mac app: WinUI 3 and C#, talking to the same
  Python core through the existing bridge (`stickler-bridge`, JSON lines), the sheet music in
  WebView2, a C# counterpart of SticklerCore with its tests.
- **User:** drummers who find Stickler through the website and use Windows. Windows is the gap
  next to Linux and the Mac.
- **First version:** the Mac app's scope at release 8: the setup assistant with consent and the
  model download, open or drop a song, the Fast analysis on the CPU with progress and cancel,
  the sheet music, export of MusicXML, PDF and the drum track, recent songs, "Remove Downloaded
  Models…", in the languages of `po/`. (Corrected after the interview: the Mac app had no
  playback and no corrections at release 8, so neither does the first Windows version.)
- **Afterwards:** Windows catches up (backup and uninstall from release 10, then whatever the
  other apps have); from then on every new feature ships on all three systems in the same
  release. The goal is the same features everywhere, not the same start.
- **Distribution:** a per-user `.exe` built with Inno Setup (no administrator rights), Windows
  11 on x64 (owner, 2026-11-24, after the interview: Windows 11 only). Unsigned at first;
  the website's install guide explains SmartScreen's warning. In parallel, an application to the SignPath Foundation; signed from its approval on.
- **Success:** the owner downloads the installer from a release on their Windows computer,
  installs it and analyses a song through to an export; the website offers the download, in
  English and German.
- **Out of scope:** Qt, GTK or Electron on Windows; a paid certificate; `.msi`/WiX, winget and
  the Microsoft Store; Windows 10; CUDA and ARM64 in the first version; features only Windows has.
