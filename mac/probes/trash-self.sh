#!/bin/sh
# Builds mac/probes/TrashSelf.swift into a bare app in a folder of the home (as /Applications or
# Downloads would be), starts it and checks that the running app moved itself to the Bin.
set -eu
work="$HOME/StickProbe"
rm -rf "$work"
mkdir -p "$work/TrashSelf.app/Contents/MacOS"
swiftc -O -o "$work/TrashSelf.app/Contents/MacOS/TrashSelf" "$(dirname "$0")/TrashSelf.swift"
cat >"$work/TrashSelf.app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>TrashSelf</string>
<key>CFBundleIdentifier</key><string>ng.tshia.StickProbe</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
codesign --force --sign - "$work/TrashSelf.app"
"$work/TrashSelf.app/Contents/MacOS/TrashSelf"
test ! -e "$work/TrashSelf.app" || { echo "the bundle is still in its folder" >&2; exit 1; }
ls -d "$HOME"/.Trash/TrashSelf* && echo "the running app moved itself to the Bin"
rm -rf "$HOME"/.Trash/TrashSelf* "$work"
