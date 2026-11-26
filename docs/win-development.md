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
build has started at once so far, but not always: on 2026-11-26 several new builds were held
back for minutes to an hour, and one that had started was refused again later. If a program
is held back, nothing is switched off or excluded: note the message, let the runner take the
screenshots, and try again later.

## Screenshots

`scripts/win_screens.ps1` starts the built app with data of its own, captures the consent and
the empty window, and presses "Not Now" through UI Automation. Then (module `win-sheet`) it
sets up the stand-in models, opens their song as a recent one, captures the sheet (W6) and in
light saves the PDF through Export (`STICKLER_SAVE_AS` answers the save dialog), which
`scripts/check_pdf.py` checks. On this PC run it with `-Looks light -SheetOnly -Export
"Exportieren" -PdfEntry ("Noten (PDF) " + [char]0x2026)` (it would switch the desktop's theme
for "dark"; the consent does not come where the models are set up); the runner takes both
looks and everything.

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
5. While the models download, the running step's ring keeps turning (fixed 2026-11-26).

## At the checkpoint (SPEC.md, module `win-sheet`, success criteria)

1. An analysed song shows its sheet music; it fills the window's width after a resize (wait
   a moment: the width settles first) and scrolls only vertically; the tempo mark is drawn,
   not a box.
2. View › Zoom In, Zoom Out, Actual Size change the note size, and so do Ctrl+Plus,
   Ctrl+Minus, Ctrl+0, Ctrl+mouse wheel and a touchpad's pinch, also after a click into the
   sheet (unconfirmed until now: whether the keys arrive while the sheet has the focus, and
   whether the wheel script runs with the page's scripts off). The size is kept for the next
   song and the next start.
3. Export › Sheet Music (PDF)… with Windows' own save dialog: the PDF has every page in A4 and
   the song's title; "Show in Folder" shows it; saving over an older PDF replaces it, a
   cancelled dialog changes nothing.
4. Dark mode: the page is inverted on the dark desk. Narrator reads the sheet as "Sheet music
   of …, n pages".

## What to check for the playback (Checkpoint AK; SPEC.md, module `win-playback`)

1. A song plays with its clicks in time with the drums (by ear); Play, Pause, the position
   slider, Previous Bar and Next Bar work. Measured in a VM on 2026-11-26 from the recorded
   sound: the clicks and the song lie within one sample of each other, also after a pause, a
   bar step, a jump on the slider and with other volumes; the ear's check is for a real song
   and real loudspeakers.
2. Song · Hits · Both and the two volume sliders (the speaker button) change what is heard;
   the volumes are the same after a restart. A volume change may click softly (the gain
   changes at a buffer's edge): say so if it does.
3. The marker follows the sounding bar in the accent colour, light and dark, and stays in
   view; a click on a bar jumps there (inside repeat signs: to its next pass).
4. Playback › Play (Space), Previous Bar (Left), Next Bar (Right), Go to the Start (Home),
   and Song, Hits, Both with their dot; the keys also after a click into the sheet, and not
   while a slider, a switch or the menu bar has the focus. A held Space is one press.
5. An MP3, an M4A and an Ogg or Opus file (the last two play from a copy the core decodes
   first, a moment's wait at the first Play).
6. Headphones unplugged while playing: Windows moves the sound to the loudspeakers (it does
   not pause as the Mac does). No sound output at all: "The song cannot be played: No sound
   output was found."
7. Opening another song, Close Song and closing the window stop the sound at once.

## What to check for the corrections (Checkpoint AL; SPEC.md, module `win-corrections`)

1. The button right of Export and View › Corrections (Ctrl+Shift+C) open and close the pane;
   the entry has its check mark; the pane is open again after a restart when it was left open.
2. Half and Double change tempo and bars within about a second; Beats per bar and First “one”
   step by one and stop at their ends; Simplify and Repeat signs switch; the small ring turns
   after the subtitle meanwhile and Export is off.
3. "Back to Detected" clears everything and is off while nothing is corrected.
4. A song opened again shows its corrections; while playing, the marker and the bar's text
   follow a correction.

## Testing in a Windows VM (owner's Linux computer, 2026-11-26)

`~/VMs/stickler-win11/` holds a QEMU/KVM Windows 11 VM (its `README.md`: `start.sh`,
`stop.sh`, `ssh.sh`, `screenshot.sh`; tools in the Distrobox `stickler-vm`, nothing on the
host). The SDK, Git, uv and ffmpeg are under `C:\tools`, the checkout is `C:\src\stickler`;
`C:\tools\run-interactive.ps1` runs a command in the logged-on desktop session, which the
app's window and UI Automation need. QEMU writes what the VM plays to `logs/audio.wav`, so
the sound can be measured. The image is a stripped third-party Windows build with an old
WebView2 runtime: what it shows is a hint, GitHub's runner and a real PC count.

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
