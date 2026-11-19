#!/bin/bash
# Puts the core into the Mac app (SPEC.md, module `mac-package`, scope 2):
#
#   Stickler.app/Contents/Resources/core/
#     bin/uv, bin/ffmpeg, bin/ffprobe
#     python/                         a relocatable Python with the core's packages and sources
#     python/share/stickler/adapters  the adapters' sources (no environments, no weights)
#     python/share/locale             the translations (po/ → .mo)
#
#   scripts/mac_bundle.sh <Stickler.app> <folder with ffmpeg and ffprobe>
#
# then signs the app again ad hoc (its resources changed). Run from a clean checkout on macOS
# arm64, as CI does; every download is pinned by version and SHA-256. Bash 3.2.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

UV_VERSION=0.13.9 # 2026-11-17; the SHA-256 is the release's own (.sha256 next to the asset)
UV_SHA256=5aeca67f2283f75235de40d0bd9c0a5bbc5fce23b6d48b3bf9fa1b2db08382ca
# python-build-standalone, the Python uv itself installs (astral-sh, release 20261110)
PYTHON_VERSION=3.14.10
PYTHON_BUILD=20261110
PYTHON_SHA256=f15ec3d15460dd66c2eb88639b152cd9040e7d1ece11e38bf89e8f53f0171e02

app=${1:?usage: scripts/mac_bundle.sh <Stickler.app> <folder with ffmpeg and ffprobe>}
tools=${2:?usage: scripts/mac_bundle.sh <Stickler.app> <folder with ffmpeg and ffprobe>}
test -d "$app/Contents/Resources" || { echo "$app is not an app" >&2; exit 1; }
core="$app/Contents/Resources/core"
rm -rf "$core"
mkdir -p "$core/bin"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() { # url, file, sha256
  curl -fsSL --retry 3 -o "$2" "$1"
  echo "$3  $2" | shasum -a 256 -c - >/dev/null
}

echo "== uv $UV_VERSION"
fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-apple-darwin.tar.gz" \
  "$work/uv.tar.gz" "$UV_SHA256"
tar -xzf "$work/uv.tar.gz" -C "$work"
install -m 755 "$work/uv-aarch64-apple-darwin/uv" "$core/bin/uv"

echo "== ffmpeg and ffprobe"
install -m 755 "$tools/ffmpeg" "$tools/ffprobe" "$core/bin/"

echo "== Python $PYTHON_VERSION"
fetch "https://github.com/astral-sh/python-build-standalone/releases/download/$PYTHON_BUILD/cpython-$PYTHON_VERSION+$PYTHON_BUILD-aarch64-apple-darwin-install_only_stripped.tar.gz" \
  "$work/python.tar.gz" "$PYTHON_SHA256"
tar -xzf "$work/python.tar.gz" -C "$core" # unpacks to python/
py="$core/python/bin/python3"

echo "== the core's packages, as uv.lock pins them"
# the benchmark's and the command line's packages stay out (mir-eval with scipy; typer)
"$core/bin/uv" export --frozen --no-dev --no-emit-project --prune mir-eval --prune typer \
  --format requirements-txt --output-file "$work/requirements.txt" >/dev/null
"$py" -I -B -m pip install --quiet --disable-pip-version-check --no-deps --require-hashes \
  --only-binary :all: --no-compile -r "$work/requirements.txt"

echo "== the core"
site=$("$py" -I -B -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
version=$(sed -n 's/^version = "\([0-9]*\)".*/\1/p' pyproject.toml)
cp -R src/stickler src/stickler_app "$site/"
mkdir -p "$site/stickler-$version.dist-info"
printf 'Metadata-Version: 2.1\nName: stickler\nVersion: %s\n' "$version" \
  > "$site/stickler-$version.dist-info/METADATA"

echo "== the adapters' sources"
git ls-files adapters | while IFS= read -r file; do
  mkdir -p "$core/python/share/stickler/$(dirname "$file")"
  cp "$file" "$core/python/share/stickler/$file"
done

echo "== translations"
msgfmt=$(command -v msgfmt || echo "$(brew --prefix gettext)/bin/msgfmt")
for po in po/*.po; do
  dir="$core/python/share/locale/$(basename "$po" .po)/LC_MESSAGES"
  mkdir -p "$dir"
  "$msgfmt" --check --output-file="$dir/stickler.mo" "$po"
done

find "$core" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "== signature"
# the helpers keep their own signatures (uv: Astral's; Python, the wheels and ffmpeg: ad hoc
# from their builds); the app's is made again over the new resources
codesign --force --sign - --timestamp=none "$app"
codesign --verify --strict --verbose=2 "$app"

echo "== sizes"
du -sh "$core/bin/uv" "$core/bin/ffmpeg" "$core/bin/ffprobe" "$core/python" \
  "$core/python/share" "$core" "$app"
