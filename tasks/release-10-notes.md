# Release 10: draft of the release notes

For `gh release create v10` (ADR 0006; style: Keep a Changelog, no "Next", no "Made with AI", no
Install section). Check every line against what ships before the release and delete this file
afterwards. The MetaInfo's `<release version="10">` is written at the release, from this.

---

Take Stickler to another computer, and remove it from the app ([how to install](https://github.com/niklastshiang/stickler#-install-the-app)).

### Added
- **Back Up…** and **Restore Backup…** in the menu: your settings, recent songs, corrections and analyses in one file, restored on Linux or a Mac. Songs open with their corrections without a new analysis, even from another folder.
- **Uninstall Stickler…** in the menu: removes the app with its models and analyses; a box removes your settings, recent songs and corrections too. The AppImage and the Mac app move themselves to the Bin, the `.deb` and `.rpm` ask for your password, the Flatpak opens the Software app on Stickler's page.

### Changed
- A song you moved to another folder keeps its corrections.

**Full changelog:** https://github.com/niklastshiang/stickler/compare/v9...v10
