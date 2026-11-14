#!/usr/bin/env bash
# Runs the GTK application in development (SPEC.md, module `app-shell`).
#
# GTK, libadwaita and PyGObject come from the system, not from PyPI, so the app gets its own
# environment `.venv-gtk` on the system Python with access to its site packages; the project
# and its locked dependencies are installed on top.
#
#   scripts/gtk.sh            start the app
#   scripts/gtk.sh test ...   widget smoke tests (pytest -m gtk), extra arguments go to pytest
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

if [[ "${1:-}" == "test" ]]; then
  shift
  exec .venv-gtk/bin/python -m pytest -q -m gtk -p no:cacheprovider tests/gtk "$@"
fi
exec .venv-gtk/bin/stickler-gtk "$@"
