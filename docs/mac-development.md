# The Mac app before its package

Until release 8 ships a `.dmg` (module `mac-package`), the Mac app is built by GitHub on every
push and runs Stickler's core from a copy of this repository on your Mac. This guide sets that
up once and says what to check at a checkpoint (SPEC.md, module `mac-shell`).

You need a Mac with Apple Silicon and macOS 26, and about 4 GB free for the models.

## Once: the tools and the repository

1. Open **Terminal** (Applications › Utilities).
2. Install Homebrew if it is not there yet (the command on [brew.sh](https://brew.sh)), then:

   ```console
   brew install git ffmpeg gettext
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   `uv` lands in `~/.local/bin`, where the app looks for it (also `/opt/homebrew/bin`).
   `gettext` builds the German and Spanish texts of Stickler's core (step 3).
3. Get the repository and its Python environment:

   ```console
   git clone https://github.com/niklastshiang/stickler.git ~/stickler
   cd ~/stickler
   uv sync
   scripts/mo.sh
   ```

   `scripts/mo.sh` builds the core's translations; without them the app's own texts follow
   the Mac's language while everything the core says (the steps, the models' names and
   sizes, errors) stays English. The models are not downloaded here: the app's first start
   does that, as the packaged app will.

To update later: `cd ~/stickler && git pull && uv sync && scripts/mo.sh`.

## Each time: the app from GitHub

1. Open the repository's **Actions** tab, the newest green run of the workflow **mac**, and
   download the artifact **Stickler.zip** (it holds `Stickler.app`). The artifact **screenshots**
   holds every screen in light and dark and a sample PDF.
2. Unzip it and move `Stickler.app` wherever you like (Applications is fine).
3. Open it. macOS blocks the first start of an app that is not from the App Store or a known
   developer: open **System Settings › Privacy & Security**, scroll to the note about
   Stickler and click **Open Anyway**, then **Open**. This is needed once per downloaded app.

   If there is no **Open Anyway** button (seen on some macOS versions), run once in Terminal
   and open the app again:

   ```console
   xattr -dr com.apple.quarantine /Applications/Stickler.app
   ```

4. On the first start the app asks **Where Is Stickler?**: choose `~/stickler` (in the open
   panel, press ⇧⌘G and type `~/stickler`). It remembers the folder; File › Choose Stickler
   Folder… changes it.

The app runs the core as an installed app would: the models, settings and recent songs go to
`~/Library/Application Support/Stickler`, the scores to `~/Library/Caches/Stickler`. The
repository only provides the code.

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
   pkill -f stickler-bridge
   ```

5. **Languages:** System Settings › General › Language & Region, set Stickler to German or
   Spanish (or the whole Mac), open the app again.
6. **Light and dark:** System Settings › Appearance.
7. **Remove Downloaded Models…** in the Stickler menu: the sizes, the checkbox for
   everything, then the next start asks again.

## What to check for the sheet music (Checkpoint X)

Module `mac-sheet` (SPEC.md, its success criteria 1–3). Update first (`git pull`, `uv sync`,
`scripts/mo.sh`) and take the newest **Stickler.zip**.

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
