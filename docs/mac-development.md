# Developing the Mac app

The Mac app brings Stickler's core along (SPEC.md, module `mac-package`):
`Stickler.app/Contents/Resources/core` holds a Python with the core, `uv`, ffmpeg, ffprobe and
the models' sources, put there by `scripts/mac_bundle.sh`. The app starts that core and
nothing else; it asks for no folder and looks for no `uv` on the Mac.

What Xcode or `xcodebuild` builds has no core in it yet. Opened from the Finder, such an app
shows *Stickler Stopped Unexpectedly* and lists the missing parts under Technical Details
(that is why the workflow **mac** keeps no app to download). There are two ways to run the
app:

- **the image**, the app as a reader gets it (below), to check a build on a Mac; the
  reader's own guide is [Installing Stickler on a Mac](install-macos.md);
- **a development build** over a copy of this repository, for work on the app with Xcode.

You need a Mac with Apple Silicon and macOS 26, and about 4 GB free for the models.

## The image: the app with its core

1. A released image is on the repository's **Releases** page, next to the Flatpak and the
   AppImage. To check a build that is not released, open the **Actions** tab, choose the
   workflow **release**, **Run workflow**, choose the branch (for example `claude/mac-shell`)
   and wait for the run (about ten minutes; the Linux packages are built too). Its artifact
   **mac** is a zip with `Stickler-<version>.dmg`. The workflow **mac** runs on every push;
   its artifact **screenshots** holds every screen in light and dark and a sample PDF.
2. Open the image and drag Stickler to Applications.
3. Open it. macOS blocks the first start of an app that is not from the App Store or a known
   developer: open **System Settings › Privacy & Security**, scroll to the note about
   Stickler and click **Open Anyway**, then **Open**. This is needed once per downloaded app.

   If there is no **Open Anyway** button (seen on some macOS versions), run once in Terminal
   and open the app again:

   ```console
   xattr -dr com.apple.quarantine /Applications/Stickler.app
   ```

The models, settings and recent songs go to `~/Library/Application Support/Stickler`, the
scores to `~/Library/Caches/Stickler`. Nothing is written into the app. **Help › Licences**
opens the licences of what the app ships.

## A development build: the core from a checkout

A build for debugging (Xcode's Debug configuration) reads the environment variable
`STICKLER_CHECKOUT` and, when it names a copy of this repository, runs `uv run
stickler-bridge` there instead of the core in its bundle. A released build ignores the
variable. The app looks for no tools itself: `uv`, ffmpeg and ffprobe come from the `PATH`
the app was started with.

Once, the tools and the repository (Xcode 26 and [XcodeGen](https://github.com/yonaskolb/XcodeGen)
besides):

```console
brew install git ffmpeg gettext xcodegen
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/niklastshiang/stickler.git ~/stickler
cd ~/stickler
uv sync
scripts/mo.sh
```

`scripts/mo.sh` builds the core's German and Spanish texts into the checkout's environment;
without them everything the core says stays English. Run `uv sync` and `scripts/mo.sh` again
after every `git pull`.

Build and start it from Terminal, so that it gets Terminal's `PATH`:

```console
cd ~/stickler
xcodegen generate --spec mac/project.yml
xcodebuild build -project mac/Stickler.xcodeproj -scheme Stickler -configuration Debug \
  -derivedDataPath mac/build
STICKLER_CHECKOUT="$PWD" mac/build/Build/Products/Debug/Stickler.app/Contents/MacOS/Stickler
```

Started from Xcode instead, give the scheme both variables (Product › Scheme › Edit Scheme… ›
Run › Arguments › Environment Variables): `STICKLER_CHECKOUT` and a `PATH` that holds `uv` and
ffmpeg, for example `/Users/you/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin`.
The project is generated, so they are set again after `xcodegen generate`.

A checkout that is not there, or a `PATH` without `uv`, shows *Stickler Stopped
Unexpectedly* with the reason under Technical Details. The development build keeps its files
where the packaged app does (`~/Library/Application Support/Stickler`), so the two share
models and settings; do not run both at once.

Without Xcode: `swift test` in `mac/SticklerCore` runs the tests of everything below the
views, on Linux too; the app itself is compiled and tested only by the workflow **mac**.

## What to check (Checkpoint U)

1. **First start:** the consent sheet names ADTOF and Beat This! with their licences and
   sizes; **Download** shows the steps and the amount downloaded; **Cancel** during the
   download goes back to the empty window, and the next start goes on where it stopped.
2. **A song:** drop one on the window (or Open… ⌘O). The steps run, **Cancel** goes back; the
   result shows title, artist, tempo and time signature in the window's title bar.
3. **Exports:** Export › Sheet Music (PDF)…, MusicXML… and Drum Track… (the drum track asks
   first and downloads Demucs once). After saving, the bar at the bottom offers **Show in
   Finder**. Compare the PDF with the GTK app's for the same song.
4. **A stopped core:** while the app runs, end the core in Terminal and see the page
   *Stickler Stopped Unexpectedly*; **Start Again** brings it back:

   ```console
   pkill -f stickler_app.bridge
   ```

   (`pkill -f stickler-bridge` for a development build.)

5. **Languages:** System Settings › General › Language & Region, set Stickler to German or
   Spanish (or the whole Mac), open the app again.
6. **Light and dark:** System Settings › Appearance.
7. **Remove Downloaded Models…** in the Stickler menu: the sizes, the checkbox for
   everything, then the next start asks again.

## What to check for the sheet music (Checkpoint X)

Module `mac-sheet` (SPEC.md, its success criteria 1–3). Take the newest image.

1. **The sheet:** open Eye of the Tiger. Its sheet music is in the window, one page under the
   other on the grey desk; the tempo mark (♩ = 109) is drawn, not a box. Make the window about
   800 points wide, then about 1600: shortly after you let go, the notes are laid out anew
   over the whole width, and it scrolls up and down only.
2. **Note size:** View › Zoom In (⌘+), Zoom Out (⌘−), Actual Size (⌘0), and a pinch with two
   fingers on the trackpad over the sheet (the notes grow and shrink under the fingers; when
   they lift, the lines are laid out anew at that size, without a flash of an empty page). The
   three items are grey while no song is shown. Open another song, then quit and open the
   app again: the size is still the one you chose.
3. **Staying in place:** scroll to the middle of a long song, then zoom or resize: the same
   bars are still in view, not the top of the song.
4. **Dark mode:** System Settings › Appearance: light notes on a dark page. Compare both
   appearances with the canvas (M6) and the workflow's screenshots.
5. **VoiceOver** (⌘F5): on the sheet it reads one picture, "Sheet music of Eye of the Tiger,
   3 pages" (with the song's own page count), in the Mac's language; Tab does not stop in
   the sheet.

## What to check for the package (Checkpoint Z)

Module `mac-package` (SPEC.md, its success criteria 1–5), with `Stickler-8.dmg` from the draft
of release 8, downloaded with a browser so that macOS treats it as a reader's download.

1. **A Mac without the tools:** on a fresh user account, or with Homebrew's ffmpeg and `uv`
   moved away for the check, so that only the app's own are there:

   ```console
   which uv ffmpeg ffprobe
   ```

   prints nothing in a new Terminal window.
2. **Install and first start:** follow [the reader's guide](install-macos.md) and nothing
   else: drag, open once, **Open Anyway**, confirm. Stickler asks for no folder. Then the
   consent, the download, and a song to its sheet music; save the PDF, the MusicXML and the
   drum track. No Terminal is needed anywhere.
3. **Languages:** with the Mac (or Stickler alone) set to German, then Spanish, the app's
   texts and the core's (the steps, the models' names and sizes, an error) are in that
   language.
4. **Help › Licences** opens the licences of what the app ships.
5. **Removing:** **Remove Downloaded Models…** with its box ticked, quit, drag Stickler to the
   Bin. Then nothing of Stickler is left:

   ```console
   find ~/Library -iname '*stickler*' 2>/dev/null
   ```

6. **The release and the website:** the draft release holds the image beside the Flatpak and
   the AppImage; the website's Mac card shows the image's size (`install-mac.html` has no
   pictures of its own: it links Apple's guide).

## What to check for playback (Checkpoint AC)

Module `mac-playback` (SPEC.md "Mac playback", its success criteria 1–6), with the image a
`release.yml` run built from the branch (Actions › release › the run › the artifact `mac`).

1. **Playing:** open Eye of the Tiger. The glass capsule floats over the sheet at the
   window's bottom. Play: the song and its clicks sound together, the clicks in time with the
   drums (by ear). Pause and play again; drag the position slider; Previous Bar and Next Bar.
   The time, "Bar n of N" and the length follow.
2. **What you hear:** Song, Hits and Both change what you hear at once, without a gap. In the
   volume popover move both sliders while it plays. Quit and open the app again: the sliders
   are where you left them (one pair for every song, as on Linux).
3. **The marker:** the sounding bar is marked in your accent colour (System Settings ›
   Appearance › Theme colour changes it after a reopen), in light and dark mode; it keeps
   itself in view above the capsule. Click a bar inside repeat signs: playing goes to its
   next pass; stopped, the position moves there without playing.
4. **Controls menu and keys:** between View and Window. Space plays and pauses (the first
   item reads "Play" or "Pause"), ← and → go a bar back and on, ⌥← and Home go to the start,
   Song, Hits and Both carry the checkmark. Space should not press a focused button instead.
   With a song shown, open File › Open… and type "a b" and ← → in its search field, and in
   Export › MusicXML…'s name field: the space and the arrows edit the text and do not play
   or move the music (the menu's keys have no ⌘).
5. **Stopping:** open another song, Close Song (⌘W) and quit while it plays: the sound stops
   at once. Unplug headphones (or change the output in Control Centre) while it plays: it
   pauses where it was and plays on from there.
6. **A song in another format:** an `.ogg` or `.opus` song plays (macOS reads some itself;
   for the others the core makes a copy first, which takes a moment once).
7. **Screens:** compare the workflow's `M10-*` screenshots and the running app with the
   canvas (M10) in light and dark; VoiceOver names each control and reads the position
   slider's value as the time and the bar.

## What to check for the corrections (Checkpoint AG)

Module `mac-corrections` (SPEC.md "Mac corrections", its success criteria 1–5), with the image
a `release.yml` run built from the branch (Actions › release › the run › the artifact `mac`).

1. **Opening the corrections:** open Eye of the Tiger. The button at the toolbar's far right
   (and View › Show Corrections, ⌃⌘I) opens the inspector at the window's right edge; the
   sheet narrows beside it, the playback capsule stays over the sheet. The menu item then
   reads "Hide Corrections". Quit with it open and start again: it is open with the next
   song. Without a song the button and the item are grey.
2. **Tempo:** Half, then Double, then As Detected. Within about a second the sheet, the
   window's subtitle (♩ = …, the meter) and "Bar n of N" follow; a small spinner turns left
   of Open and Export while the notes are written. Play while you change it: the music goes
   on, the marker follows the new bars.
3. **Beats per bar and the first "one":** click the stepper up and down quickly a few times:
   each click counts. Move the first "one" to Beat 2: the beat before it becomes a pickup.
   The first "one" stops at Beat 1 and at the last beat of the bar.
4. **Easier to read:** Simplify and Repeat signs off and on, as in the GTK app (Simplify off
   writes every bar as detected).
5. **Back to Detected** undoes everything and is grey while nothing is corrected. Close the
   song and open it again: its corrections are back (also those made in the GTK app and
   brought over in a backup).
6. **Exports:** with a correction, export the PDF and the MusicXML: they show the corrected
   sheet.
7. **Screens:** compare the workflow's `M11-*` screenshots and the running app with the
   canvas (M11) in light and dark; VoiceOver reads each stepper with its value ("4",
   "Beat 2").
