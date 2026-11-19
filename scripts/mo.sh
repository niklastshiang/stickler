#!/usr/bin/env bash
# Builds the core's translations into the checkout's environment:
# po/<lang>.po → .venv/share/locale/<lang>/LC_MESSAGES/stickler.mo, where `stickler_app.i18n`
# looks for them. For the Mac app's development build (docs/mac-development.md): run it after
# `uv sync` and after every `git pull`. The GTK app's environment is built by scripts/gtk.sh,
# the packages build their own.
# Needs gettext (msgfmt): `brew install gettext`.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if ! command -v msgfmt >/dev/null; then
  echo "msgfmt not found: brew install gettext" >&2
  exit 2
fi
if [[ ! -d .venv ]]; then
  echo ".venv not found: run uv sync first" >&2
  exit 2
fi

for po in po/*.po; do
  dir=".venv/share/locale/$(basename "$po" .po)/LC_MESSAGES"
  mkdir -p "$dir"
  msgfmt --check --output-file="$dir/stickler.mo" "$po"
done
echo "translations: $(basename -a -s .po po/*.po | tr '\n' ' ')→ .venv/share/locale"
