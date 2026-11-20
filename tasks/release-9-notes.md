# Release 9: draft of the release notes

For `gh release create v9` (ADR 0006; style: Keep a Changelog, no "Next", no "Made with AI", no
Install section). Check every line against what ships before the release and delete this file
afterwards.

---

Stickler as a `.deb` for Ubuntu and an `.rpm` for Fedora, next to the Flatpak, the AppImage and the Mac app ([how to install](https://github.com/niklastshiang/stickler#-install-the-app)).

### Added
- `Stickler-9_amd64.deb` for Ubuntu 26.04 or newer and `Stickler-9.x86_64.rpm` for Fedora 44 or newer. Open one with the Software app, or install it with `sudo apt install ./…` or `sudo dnf install ./…`. Stickler then uses your system's GTK, libadwaita, GStreamer and ffmpeg, like any other GNOME app, and the package manager removes it again. Both are installed, started and removed in clean Ubuntu 26.04, Fedora 44 and Fedora 45 systems before every release.

### Changed
- The website's downloads: one card for the Mac and one for Linux, which says which file suits which system; the terminal lines are folded away.
- The Mac app's icon is orange, like the website. GNOME Software shows Stickler on the same orange.
- Stickler runs on Python 3.15 too (Fedora 45's).

**Full changelog:** https://github.com/niklastshiang/stickler/compare/v8...v9
