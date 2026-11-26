# The Windows app on the owner's PC

How the Windows app (`win/`, SPEC.md "Release 11 (proposed): Windows app", module `win-shell`)
is built and run on the owner's company laptop before the installer exists (`win-package`).
Until then the app starts the core from this checkout.

## Once

1. **uv** (`winget install astral-sh.uv`) and **Git for Windows**, with this repository cloned.
2. **ffmpeg** for your user, without administrator rights:

   ```powershell
   winget install --id Gyan.FFmpeg.Essentials --exact --source winget --scope user
   ```

   `--source winget`: the Microsoft Store's catalogue fails behind the company network's TLS
   inspection. Open a new terminal afterwards, so `ffmpeg` is on the `PATH`.
3. **The .NET 10 SDK** for your user (no Visual Studio needed; `dotnet build` compiles the
   WinUI XAML by itself): download Microsoft's signed `https://dot.net/v1/dotnet-install.ps1`
   and run it with `-Channel 10.0 -InstallDir "$env:LOCALAPPDATA\Microsoft\dotnet"`. The SDK is
   then at `%LOCALAPPDATA%\Microsoft\dotnet\dotnet.exe`.
4. **The company network inspects TLS.** uv trusts only its own certificates unless told
   otherwise: set `UV_SYSTEM_CERTS=1` for your user (System › Environment variables) or in
   every terminal. The app sets it for its own core.
5. **No telemetry** from .NET and its test platform: set `DOTNET_CLI_TELEMETRY_OPTOUT=1` and
   `TESTINGPLATFORM_TELEMETRY_OPTOUT=1` the same way.

## After every pull

```powershell
uv sync
```

The core's translations (`.venv\share\locale`) need gettext's `msgfmt`, which Windows does not
have: run `scripts/mo.sh` from WSL (Ubuntu with `gettext`) in this checkout. Without them the
window is translated and the core's own texts (model descriptions, errors) stay English.

## Build, test, start

```powershell
dotnet build win/Stickler.sln -c Release
```

```powershell
dotnet run --project win/SticklerCore.Tests -c Release --no-build
```

The app is `win\Stickler\bin\x64\Release\net10.0-windows10.0.26100.0\win-x64\Stickler.exe`. Started
from there it finds this checkout by itself (the first folder above it with `pyproject.toml`
and `adapters`). The CI's artifact `stickler-windows-app` (workflow `win`) is the same folder:
unpacked elsewhere, set `STICKLER_CHECKOUT` to this checkout first.

It keeps its data where the installed app will: `%LOCALAPPDATA%\Stickler`. The spike
(`win-spike`) uses the same folders; to try the app without touching them, start it with
`XDG_DATA_HOME`, `XDG_CACHE_HOME` and `XDG_CONFIG_HOME` pointing elsewhere.

## Panda

Panda Adaptive Defense holds back a program it has not seen before, for about half an hour
(task 179): the spike's installer helper, uv's launcher of a new environment
(`.venv\Scripts\python.exe` of a new uv release), uv's `stickler-bridge.exe`. The app
therefore starts the core as `python -m stickler_app.bridge`. A new `Stickler.exe` after a
build has started at once so far. If a program is held back, nothing is switched off or
excluded: note the message and try again later.

## Screenshots

`scripts/win_screens.ps1` starts the built app with data of its own, captures the consent and
the empty window, and presses "Not Now" through UI Automation. On this PC run it with
`-Looks light -NotNow "Nicht jetzt"` (it would switch the desktop's theme for "dark"); the
runner takes both looks.

## At the checkpoint (SPEC.md, module `win-shell`, success criteria)

1. A development build finds the checkout, asks for consent, downloads the Fast models into
   `%LOCALAPPDATA%\Stickler`, and a dropped song becomes a result; Cancel works during the
   analysis and the download.
2. MusicXML and the drum track are saved; "Show in Folder" shows the file; a backup made here
   restores in the GTK app and the other way round.
3. Ending the core in Task Manager (the `python.exe` running `stickler_app.bridge`) shows
   "Stickler Stopped Unexpectedly"; "Start Again" works.
4. Light and dark, English and German, match the canvas (`docs/design/win/`); once with the
   keyboard only (Tab, Alt for the menu bar) and once in high contrast.

## The installer (SPEC.md, module `win-package`)

The installer is made by `release.yml`'s `windows` job: `scripts/win_bundle.sh` assembles the
installed folder (the app built with `-p:SticklerInstalled=true`, so it never looks for a
checkout; uv, Python and ffmpeg pinned by SHA-256; the pruned core and the licences), and Inno
Setup 7.1.1 makes `Stickler-<version>-setup.exe` from it. A manual run of `release.yml` on a
branch gives it as the artifact `windows`; the job installs it on the runner, starts the app,
runs the core's removal and uninstalls silently. The folder alone can be made here too, with
Git's bash (`DOTNET` pointing at the SDK, `UV_SYSTEM_CERTS=1` on this network):

```bash
DOTNET="$LOCALAPPDATA/Microsoft/dotnet/dotnet.exe" scripts/win_bundle.sh /tmp/layout
```

Its texts beyond Inno's own (the Windows 10 message, the uninstaller's two questions) come from
`po/` into `win/installer/Messages.iss` with `scripts/winstrings.py`, as the app's tables do.

### What to check for the installer (Checkpoint AJ)

1. Download the installer from the run's artifact `windows` with the browser and start it; note
   what the browser, Windows and Panda say. It installs without a password into
   `%LOCALAPPDATA%\Programs\Stickler`, in German, and ends with "Stickler starten" ticked.
2. Stickler is in the Start menu and on the desktop; it starts without a checkout (no
   `STICKLER_CHECKOUT`, no `uv` of its own on the PATH needed), asks for the models and turns a
   song into sheet music.
3. Settings › Apps lists "Stickler" with its icon, version and publisher "Stickler". Its
   **Uninstall** asks "Stickler deinstallieren?" and then about the settings (No by default):
   with No, `%LOCALAPPDATA%\Stickler` keeps only `config` and the recent songs and corrections;
   after a second install and Yes, nothing of `%LOCALAPPDATA%\Stickler` is left. (The spike's
   `spike-log.txt` and `spike-out` there are no Stickler files: delete them by hand first.)
4. **File › Stickler deinstallieren …** in the app does the same with its box; the app ends,
   and the program goes a moment later (if Panda holds the uninstaller back, the app says
   where to remove it later).
5. Help › Licences opens the installed licences folder.
