#!/usr/bin/env bash
# Runs the GTK application in development (SPEC.md, module `app-shell`).
#
# GTK, libadwaita and PyGObject come from the system, not from PyPI, so the app gets its own
# environment `.venv-gtk` on the system Python with access to its site packages; the project
# and its locked dependencies are installed on top.
#
#   scripts/gtk.sh            start the app
#   scripts/gtk.sh test ...   widget smoke tests (pytest -m gtk), extra arguments go to pytest
#   scripts/gtk.sh demo <song> [out.gif]   records the README's animated overview (scripts/demo.py);
#     --dark, --video DIR, --stills DIR and --no-gif record the website's pictures (docs/website.md)
#
# STICKLER_GTK_PYTHON overrides the interpreter (default: /usr/bin/python3).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

python="${STICKLER_GTK_PYTHON:-/usr/bin/python3}"
export UV_PROJECT_ENVIRONMENT=.venv-gtk UV_PYTHON="$python"

if [[ ! -x .venv-gtk/bin/python ]]; then
  uv venv --quiet --system-site-packages .venv-gtk
fi
uv sync --quiet --frozen

# translations: po/<lang>.po → .venv-gtk/share/locale/<lang>/LC_MESSAGES/stickler.mo
for po in po/*.po; do
  dir=".venv-gtk/share/locale/$(basename "$po" .po)/LC_MESSAGES"
  mkdir -p "$dir"
  msgfmt --check --output-file="$dir/stickler.mo" "$po"
done

# the app icon and its symbolic variant, in the app environment's icon theme
mkdir -p .venv-gtk/share/icons/hicolor/scalable/apps .venv-gtk/share/icons/hicolor/symbolic/apps
cp -u packaging/icons/ng.tshia.Stickler.svg .venv-gtk/share/icons/hicolor/scalable/apps/
cp -u packaging/icons/ng.tshia.Stickler-symbolic.svg .venv-gtk/share/icons/hicolor/symbolic/apps/

# the Leipzig music font for librsvg, which finds fonts through fontconfig only (packaging/fonts)
mkdir -p .venv-gtk/share/fonts
cp -u packaging/fonts/Leipzig.ttf .venv-gtk/share/fonts/
cat > .venv-gtk/fonts.conf <<CONF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>$PWD/.venv-gtk/share/fonts</dir>
</fontconfig>
CONF
export FONTCONFIG_FILE="$PWD/.venv-gtk/fonts.conf"

.venv-gtk/bin/python - <<'EOF'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
import sys
gtk = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
adw = f"{Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}"
print(f"Python {sys.version.split()[0]}, PyGObject {gi.__version__}, GTK {gtk}, libadwaita {adw}")
EOF

if [[ "${1:-}" == "test" || "${1:-}" == "demo" ]]; then
  mode="$1"
  shift
  # The widget tests and the demo recording open real windows. They run on an invisible screen of
  # their own (a headless mutter on a D-Bus session of its own), so they never pop up on the
  # desktop; STICKLER_TEST_VISIBLE=1 shows them, which is also the fallback when mutter or a way
  # to start that bus is missing. The bus comes from dbus-run-session or, where that is gone
  # (Fedora 45 ships no dbus-daemon), from dbus-broker as a transient user service whose config
  # names no service folders, so nothing (no portal) can be started on it.
  runtime="${XDG_RUNTIME_DIR:-/run/user/$UID}"
  pidfile="" compositor="" unit="" private=""
  cleanup() {
    [[ -n "$pidfile" ]] && kill "$(cat "$pidfile")" 2>/dev/null
    [[ -n "$compositor" ]] && wait "$compositor" 2>/dev/null
    [[ -n "$unit" ]] && systemctl --user stop "$unit.service" "$unit.socket" 2>/dev/null
    [[ -n "$unit" ]] && rm -f "$runtime/$unit.conf" "$runtime/$unit.sock"
    [[ -n "$pidfile" ]] && rm -f "$pidfile"
    [[ -n "$private" ]] && rm -rf "$private"
    return 0
  }
  trap cleanup EXIT
  bus=""
  if command -v dbus-run-session >/dev/null; then
    bus=dbus-run-session
  elif command -v dbus-broker-launch >/dev/null && command -v systemd-run >/dev/null; then
    bus=dbus-broker
  fi
  if command -v mutter >/dev/null && [[ -n "$bus" && -z "${STICKLER_TEST_VISIBLE:-}" ]]; then
    screen="stickler-test-$$"
    headless=(mutter --headless --wayland --no-x11 --virtual-monitor 1280x800 --wayland-display "$screen")
    pidfile=$(mktemp)
    if [[ "$bus" == dbus-run-session ]]; then
      # mutter writes its own PID: ending dbus-run-session alone would leave it running
      dbus-run-session -- sh -c 'echo $$ > "$1"; shift; exec "$@"' sh "$pidfile" \
        "${headless[@]}" >/dev/null 2>&1 &
      compositor=$!
    else
      unit="$screen-bus"
      cat > "$runtime/$unit.conf" <<'CONF'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <policy context="default">
    <allow send_destination="*"/>
    <allow own="*"/>
  </policy>
</busconfig>
CONF
      systemd-run --user --quiet --unit="$unit" --socket-property=ListenStream="$runtime/$unit.sock" \
        -p Type=notify dbus-broker-launch --scope user --config-file "$runtime/$unit.conf"
      DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/$unit.sock" "${headless[@]}" >/dev/null 2>&1 &
      compositor=$!
      echo "$compositor" > "$pidfile"
    fi
    for _ in $(seq 200); do
      [[ -S "$runtime/$screen" ]] && break
      sleep 0.05
    done
    [[ -S "$runtime/$screen" ]] || { echo "headless mutter did not start" >&2; exit 1; }
    export WAYLAND_DISPLAY="$screen" GDK_BACKEND=wayland
    unset DISPLAY
  fi
  if [[ "$mode" == "demo" ]]; then
    # private settings, cache and recent songs, in English, as for the screenshots
    private=$(mktemp -d)
    # an empty results cache too, so the analysis really runs and is seen in the recording
    XDG_CONFIG_HOME="$private/config" XDG_CACHE_HOME="$private/cache" \
      XDG_DATA_HOME="$private/data" STICKLER_RESULTS_CACHE="$private/results" LANGUAGE=en \
      .venv-gtk/bin/python scripts/demo.py "$@"
    exit
  fi
  .venv-gtk/bin/python -m pytest -q -m gtk -p no:cacheprovider tests/gtk "$@"
  exit
fi
exec .venv-gtk/bin/stickler-gtk "$@"
