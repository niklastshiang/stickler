#!/bin/sh
# Runs inside a clean container (scripts/linux_packages.py test; SPEC.md, module `linux-packages`):
# installs the package with the system's package manager, decodes an MP3 and an AAC clip with
# ffmpeg and with GStreamer (the analysis and the playback), checks the bundled uv, starts the
# app as a user on an invisible screen until its window is there, removes the package and looks
# for anything left of it.
#
#   sh container-test.sh deb|rpm <package file> <clips folder>
set -eu
family=$1
package=$2
clips=$3

echo "== install $(basename "$package")"
case $family in
deb)
	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y -qq "$package" xvfb xauth dbus-daemon x11-utils >/dev/null
	;;
rpm)
	dnf install -y -q "$package" xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon util-linux xwininfo >/dev/null
	;;
esac

if [ "$family" = deb ] && [ ! -f "$clips/clip.mp3" ]; then
	echo "== clips (made here, used by every container)"
	ffmpeg -v error -f lavfi -i "sine=frequency=440:duration=2" "$clips/clip.mp3"
	ffmpeg -v error -f lavfi -i "sine=frequency=440:duration=2" -c:a aac "$clips/clip.m4a"
fi

echo "== decode with ffmpeg"
for clip in "$clips/clip.mp3" "$clips/clip.m4a"; do
	ffmpeg -v error -i "$clip" -f null - || {
		echo "ffmpeg cannot decode $(basename "$clip")" >&2
		exit 1
	}
done

echo "== decode with GStreamer"
python3 -I - "$clips/clip.mp3" "$clips/clip.m4a" <<'EOF'
import sys

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

Gst.init(None)
for path in sys.argv[1:]:
    pipeline = Gst.parse_launch(f"uridecodebin uri=file://{path} ! audioconvert ! fakesink")
    pipeline.set_state(Gst.State.PLAYING)
    wanted = Gst.MessageType.EOS | Gst.MessageType.ERROR
    message = pipeline.get_bus().timed_pop_filtered(20 * Gst.SECOND, wanted)
    pipeline.set_state(Gst.State.NULL)
    if message is None or message.type != Gst.MessageType.EOS:
        error = message.parse_error()[0].message if message else "no end within 20 s"
        sys.exit(f"GStreamer cannot decode {path.rsplit('/', 1)[-1]}: {error}")
EOF

echo "== the bundled uv and the adapters' sources"
/usr/lib/stickler/bin/uv --version
test -f /usr/share/stickler/adapters/_common/pyproject.toml

echo "== start the app as a user, until its window is there"
useradd -m drummer
cat >/tmp/run-app.sh <<'RUN'
stickler-gtk &
app=$!
for _ in $(seq 30); do
	sleep 1
	kill -0 "$app" 2>/dev/null || break
	if xwininfo -root -tree | grep -q '"Stickler"'; then
		echo "window: open"
		break
	fi
done
kill "$app" 2>/dev/null
wait "$app" 2>/dev/null
exit 0
RUN
su - drummer -c 'dbus-run-session -- xvfb-run -a sh /tmp/run-app.sh' >/tmp/app.log 2>&1 || true
if ! grep -q "window: open" /tmp/app.log || grep -qE "Traceback|CRITICAL" /tmp/app.log; then
	cat /tmp/app.log >&2
	echo "the app's window did not open, or it reported an error" >&2
	exit 1
fi

echo "== remove"
case $family in
deb) apt-get remove -y -qq stickler >/dev/null ;;
rpm) dnf remove -y -q stickler >/dev/null ;;
esac
left=$(find /usr /etc /opt -xdev \( -iname '*stickler*' -o -name 'ng.tshia.*' \) 2>/dev/null || true)
if [ -n "$left" ]; then
	echo "left after removing: $left" >&2
	exit 1
fi
echo "== ok"
