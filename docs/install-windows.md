# Installing Stickler on Windows

You need Windows 11 on a PC with an Intel or AMD processor (x64), and about 4 GB free for the
models. No administrator rights are needed, and nothing else is installed: Stickler brings what
it needs along.

The same steps on the website: <https://stickler.tshia.ng/install-windows.html> (online with
release 11).

Windows warns before the first start, because Stickler's installer is not signed yet: signing
costs developers a yearly fee, and Stickler is free. A free signature for open-source projects
is applied for (SignPath Foundation); until then, the steps below are Windows' own way to start
a program it does not know yet. Microsoft describes the warning on its page
[SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

## Step by step

1. **Download it**

   Take `Stickler-<version>-setup.exe` from the newest
   [release](https://github.com/niklastshiang/stickler/releases). If the browser says the file
   is not commonly downloaded, choose to keep it (in Edge, through the **…** menu next to the
   download).

2. **Start the installer**

   Open the downloaded file. Windows shows **Windows protected your PC**. Choose **More info**,
   then **Run anyway**. Nothing is wrong: Windows has not seen this new file often enough yet.

3. **Install**

   The installer is in the language of Windows. Choose **Install**; it asks for no folder and
   no password, and puts Stickler under your own user only
   (`%LOCALAPPDATA%\Programs\Stickler`). At the end, **Start Stickler** is ticked: choose
   **Finish**.

Stickler is now in the Start menu and on the desktop.

## The first start

Stickler needs trained models to hear the drums. It shows which ones, their licences and
their size, and downloads them only after you agree. After that it works without the
internet; your songs stay on your PC. The first export of a drum track asks once more, for one
more model.

## When Windows or the antivirus says no

- **No "Run anyway" button, only "Don't run":** Smart App Control is on. It runs only signed
  programs, so it does not start Stickler until Stickler is signed. Microsoft explains it in
  [Smart App Control: frequently asked questions](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions).
- **A company PC:** its antivirus may hold back a new program the first time it starts
  ("Access is denied", or the installer says it is "unable to execute file in the temporary
  directory"). On the PC Stickler was tried on, the same start went through about half an hour
  later; the uninstaller once waited a day. Try again later, or ask your IT department to allow
  Stickler.
- **Windows 10 or a PC with an ARM processor:** the installer says that Stickler needs Windows 11
  with an Intel or AMD processor, and installs nothing.

## Updating

Download the new release's installer and run it as above, with Stickler closed (the installer
asks if it is open). Your models, settings, recent songs and corrections stay.

## Removing it

Two ways, the same question:

- In Stickler, choose **File › Uninstall Stickler…**.
- Or in Windows, **Settings › Apps › Installed apps**, then **…** next to Stickler, then
  **Uninstall**.

Both remove the program, the models with their programs and downloads, and the saved analyses.
Your songs and your exports are never touched. Your settings, recent songs and corrections stay
unless you say otherwise: in the app with the box **Also remove my settings, recent songs and
corrections**, in Settings with **Yes** to the second question. A new install then picks up
where you left off.

To free only the models' space and keep the app, choose **File › Remove Downloaded Models…**.

If Windows or the antivirus does not let the uninstaller start, the app says so after removing
Stickler's data; remove the program later in **Settings › Apps**.

## Where Stickler keeps its files

| What | Where |
|---|---|
| The program | `%LOCALAPPDATA%\Programs\Stickler` |
| The models, recent songs and corrections | `%LOCALAPPDATA%\Stickler\data` |
| The scores of analysed songs, downloads | `%LOCALAPPDATA%\Stickler\cache` |
| The settings | `%LOCALAPPDATA%\Stickler\config` |

**Help › Licences** opens the licences of what the app ships.

For work on the app: [Developing the Windows app](win-development.md).
