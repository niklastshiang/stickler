# Installing Stickler on a Mac

You need a Mac with Apple silicon and macOS 26, and about 4 GB free for the models. Nothing
else is installed: Stickler brings what it needs along.

The same steps on the website: <https://stickler.tshia.ng/install-mac.html> (online with
release 8).

macOS asks for one extra step at the first start, because Stickler does not come from the App
Store and is not registered with Apple, which costs developers a yearly fee. Stickler is free
and does without. The steps below are Apple's own way for such an app; Apple shows the
windows in its guide
[Open a Mac app from an unknown developer](https://support.apple.com/guide/mac-help/mh40616/mac).

## Step by step

1. **Download it**

   Take `Stickler-<version>.dmg` from the newest
   [release](https://github.com/niklastshiang/stickler/releases). The file, a disk image,
   lands in your Downloads folder.

2. **Drag Stickler to Applications**

   Open the downloaded file. A window shows Stickler next to the Applications folder: drag
   Stickler onto it. Then eject the disk image in the Finder's sidebar.

3. **Open it once**

   Open Stickler from Applications. macOS says it could not check the app and does not open
   it. Choose **Done**; nothing is wrong.

4. **Allow it in System Settings**

   Open **System Settings › Privacy & Security** and scroll down to **Security**. Next to the
   note that Stickler was blocked, choose **Open Anyway**. The button is there for about an
   hour after you tried to open Stickler.

5. **Confirm**

   macOS asks once more: choose **Open Anyway** and confirm with your password or Touch ID.
   Stickler opens. From now on it opens like any other app.

## The first start

Stickler needs trained models to hear the drums. It shows which ones, their licences and
their size, and downloads them only after you agree. After that it works without the
internet; your songs stay on your Mac. The first export of a drum track asks once more, for
one more model.

## No "Open Anyway" button?

Try to open Stickler again and look in System Settings within the hour. If the button still
does not show, open the Terminal app, paste this line, press Return, and open Stickler again:

```console
xattr -dr com.apple.quarantine /Applications/Stickler.app
```

The line removes the mark macOS puts on everything downloaded with a browser; it changes
nothing else.

## Removing it

Choose **Remove Downloaded Models…** in the Stickler menu with its box ticked, which removes
the models, the settings, the recent songs and the corrections. Then drag Stickler from
Applications to the Bin.

To free only the models' space and keep the app, leave the box unticked.

## Where Stickler keeps its files

| What | Where |
|---|---|
| The models, settings and recent songs | `~/Library/Application Support/Stickler` |
| The scores of analysed songs | `~/Library/Caches/Stickler` |

Nothing is written into the app itself. **Help › Licences** opens the licences of what the
app ships.

For work on the app: [Developing the Mac app](mac-development.md).
