# Developing the Mac app

The Mac app brings Stickler's core along (SPEC.md, module `mac-package`):
`Stickler.app/Contents/Resources/core` holds a Python with the core, `uv`, ffmpeg, ffprobe and
the models' sources, put there by `scripts/mac_bundle.sh`. The app starts that core and
nothing else; it asks for no folder and looks for no `uv` on the Mac.

What Xcode or `xcodebuild` builds has no core in it yet. Opened from the Finder, such an app
(the **Stickler.zip** of the workflow **mac** too) shows *Stickler Stopped Unexpectedly* and
lists the missing parts under Technical Details. There are two ways to run the app:

- **the image**, the app as a reader gets it (below), to check a build on a Mac;
- **a development build** over a copy of this repository, for work on the app with Xcode.

You need a Mac with Apple Silicon and macOS 26, and about 4 GB free for the models.

## The image: the app with its core

1. Open the repository's **Actions** tab. Until the release workflow builds the image (task
   136) it comes from the workflow **mac-spike**: **Run workflow**, choose the branch, wait
   for the run, download the artifact **Stickler-spike** (a zip with `Stickler-spike.dmg`).
   The workflow **mac** runs on every push; its artifact **screenshots** holds every screen
   in light and dark and a sample PDF.
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
