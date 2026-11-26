# Applying to the SignPath Foundation

Stickler's Windows installer is unsigned (SPEC.md, release 11, "Distribution without paying").
The SignPath Foundation signs open-source projects for free. This page holds what the
application needs, written for the owner to submit (SPEC.md, module `win-package`, question 6:
**after release 11 is out**, because the foundation signs only projects already released in
the form to be signed).

Conditions read on <https://signpath.org/terms> on 2026-11-26; the form is at
<https://signpath.org/apply> (it is drawn by a script, so its exact fields were not read; the
answers below cover what the terms ask).

## Before submitting

- [ ] Release 11 is published with `Stickler-11-setup.exe` (the form to be signed).
- [ ] The website's home page and download section have the **code signing policy** below
      (the terms ask for it on the home and the download page).
- [ ] Multi-factor authentication is on for the owner's GitHub account (the repository) and
      will be for the SignPath account.
- [ ] Every component Stickler ships is under an OSI-approved licence (checked below).

## The answers

**Project name:** Stickler

**Repository:** <https://github.com/niklastshiang/stickler>

**Website:** <https://stickler.tshia.ng/> (download: <https://stickler.tshia.ng/#get>)

**Licence:** GPL-3.0-or-later (OSI-approved), the whole repository.

**What it does (one paragraph):** Stickler turns drum recordings into sheet music. A drummer
opens a song; open-source models transcribe the drums and find the beats, and Stickler writes
the result as engraved sheet music, MusicXML and PDF. It runs on Linux, macOS and Windows; the
Windows app is a WinUI 3 interface over a Python core that it brings along.

**What is to be signed:** the Windows installer `Stickler-<version>-setup.exe` (Inno Setup),
its uninstaller `unins000.exe`, and the app's own `Stickler.exe`. Built only on GitHub-hosted
runners, by the workflow `.github/workflows/release.yml` (job `windows`), from a release tag.

**Components shipped in the installer and their licences:**

| Component | Licence | Source |
|---|---|---|
| Stickler (app and Python core) | GPL-3.0-or-later | this repository |
| .NET runtime (self-contained) | MIT | Microsoft, NuGet |
| Windows App SDK runtime (self-contained: WinUI, its resources) | **Microsoft Software License Terms** (not OSI) | Microsoft, NuGet `Microsoft.WindowsAppSDK` 2.7.0 |
| Windows ML runtime (`onnxruntime.dll`, `DirectML.dll`, pulled in by the SDK, unused) | **Microsoft Software License Terms** (not OSI) | Microsoft, NuGet `Microsoft.Windows.AI.MachineLearning` |
| WebView2 loader | BSD-3-Clause | Microsoft, NuGet `Microsoft.Web.WebView2` |
| Windows SDK projection (`Microsoft.Windows.SDK.NET.dll`, `WinRT.Runtime.dll`) | Windows SDK licence (a link only, <https://aka.ms/WinSDKLicenseURL>) | Microsoft, NuGet `Microsoft.Windows.SDK.NET.Ref` |
| CPython (python-build-standalone) | PSF-2.0 | astral-sh/python-build-standalone |
| uv | MIT or Apache-2.0 | astral-sh/uv (signed by its makers) |
| ffmpeg, ffprobe (gyan.dev essentials build) | GPL-3.0 | gyan.dev, a static build |
| The core's Python packages from `uv.lock` | each an OSI licence (numpy BSD-3-Clause, Verovio LGPL-3.0, …) | PyPI; collected in `core\licenses` at build time |

The model weights are **not** shipped: the app downloads them only after the user agrees, each
with its own licence, which the app names (some are for non-commercial use only). ffmpeg and
the Python packages are unsigned upstream programs, which the terms allow to be bundled.

**Open before submitting (found 2026-11-26, the owner's decision):** the terms ask for no
proprietary components, and the self-contained Windows App SDK (and the Windows ML runtime it
pulls in) is Microsoft's proprietary, redistributable runtime. Whether SignPath counts a
platform runtime like it as a proprietary component is not stated in the terms. Ways out, each
a change of its own: ask SignPath before applying; ship the app framework-dependent (the
Windows App SDK runtime then comes from Microsoft's own installer, not from Stickler's), which
also drops the 41 MB of the ML runtime; or reference the SDK's component packages instead of
its metapackage, which drops the ML runtime only.

**Team and roles** (the terms ask for authors, reviewers and approvers):

- Author, reviewer and approver: the project owner (GitHub `niklastshiang`). Stickler has one
  maintainer; changes are written with an AI assistant and reviewed by the owner before they
  are merged.

**Privacy:** Stickler sends nothing about its users anywhere. It goes online only to download
the models, after asking, from the models' own servers (GitHub, Hugging Face, JKU Linz,
download.pytorch.org). Privacy page: <https://stickler.tshia.ng/privacy.html>.

**Uninstallation:** provided: Settings › Apps and File › Uninstall Stickler…, both asking
whether the user's settings go too.

**Metadata:** the installer's product name is `Stickler` and its version the release number
(`AppVersion`, `VersionInfoVersion`), as the terms ask the signed files' metadata to match the
project.

## The code signing policy (for the website)

To go on the home page (a line in the footer) and in the download section, in English and
German, once the foundation approves; until then the page stays unpublished.

> **Code signing policy.** Free code signing provided by SignPath.io, certificate by SignPath
> Foundation. Windows releases are built on GitHub-hosted runners from this repository's
> release tags and signed only after the project's approver has approved the release.
> Team: the project owner is the author, reviewer and approver. Privacy: this program will not
> transfer any information to other networked systems unless specifically requested by the
> user or the person installing or operating it; the models are downloaded only after the user
> agrees (see the privacy page).

(The privacy sentence follows the statement the terms suggest; compare it word for word with
<https://signpath.org/terms> before publishing.)

> **Richtlinie zur Code-Signatur.** Kostenlose Code-Signatur von SignPath.io, Zertifikat der
> SignPath Foundation. Windows-Versionen werden auf GitHub-eigenen Runnern aus den
> Release-Tags dieses Repositorys gebaut und erst signiert, wenn der Freigebende des Projekts
> die Version freigegeben hat. Team: Der Inhaber des Projekts ist Autor, Prüfer und
> Freigebender. Datenschutz: Dieses Programm überträgt keine Informationen an andere Systeme im
> Netz, außer der Nutzer oder die Person, die es installiert oder betreibt, verlangt es
> ausdrücklich; die Modelle werden erst heruntergeladen, wenn du zustimmst (siehe
> Datenschutz).

## After approval (not part of `win-package`)

- The `windows` job uploads the unsigned installer and the app as an artifact and submits it
  with `signpath/github-action-submit-signing-request` (pinned by commit), then waits for the
  signed files. How Inno Setup's uninstaller gets signed through SignPath is open: there is no
  official guide; other projects call SignPath from Inno's `SignTool` during the compile, and
  Inno 7.1.1 notes that a Setup signed only afterwards leaves its uninstaller unsigned.
- Windows' prompts then name "SignPath Foundation" as the publisher; Settings › Apps keeps
  "Stickler".
