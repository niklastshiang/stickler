#!/bin/bash
# Assembles the folder the Windows installer installs (SPEC.md, module `win-package`, scope 1):
#
#   <layout>/Stickler.exe …             the app, built self-contained for the installer
#   <layout>/core/bin/uv.exe, ffmpeg.exe, ffprobe.exe
#   <layout>/core/python/               a relocatable Python with the core's packages and sources
#   <layout>/core/python/share/stickler/adapters   the adapters' sources (no environments, no weights)
#   <layout>/core/python/share/locale   the translations (po/ → .mo)
#   <layout>/core/licenses/             the licence of every part of the core that is shipped
#
#   scripts/win_bundle.sh <layout>
#
# Run with Git's bash on Windows x64 (the release workflow's runner, or the owner's PC) from a
# clean checkout; `dotnet` is taken from DOTNET or the PATH. Every download is pinned by version
# and SHA-256 and checked before it is used. The installer is made from the folder afterwards:
#   ISCC /DLayout=<layout> /DAppVersion=<n> /DOutDir=<folder> win\installer\Stickler.iss
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# one uv and one Python in every package (tests/test_mac_bundle.py)
UV_VERSION=0.13.9 # 2026-11-17; the SHA-256 is the release's own (.sha256 next to the asset)
UV_SHA256=edd61f7f5728a56cc62455386661860bdfc7bab65872f39b0c25bdcc1d8e1beb
# python-build-standalone, the Python uv itself installs (astral-sh, release 20261110; SHA256SUMS)
PYTHON_VERSION=3.14.10
PYTHON_BUILD=20261110
PYTHON_SHA256=32b6cf90a03e2bc15fda8d2ab7ff78c4870f138887d612932650ce764efaab8f
# gyan.dev's essentials build of ffmpeg 9.1 (static, GPLv3; the .sha256 next to the archive)
FFMPEG_VERSION=9.1
FFMPEG_SHA256=b9bbbb3acece000cbeec994f856649354e52c773807841e78908374b24d658fd
# uv's licence texts at that version (it is under either of them)
UV_MIT_SHA256=860e3d7a86b84e6a7012c7a635fc64df475cebc6cce34dfeb73a5982ec58176c
UV_APACHE_SHA256=c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4

layout=${1:?usage: scripts/win_bundle.sh <layout folder>}
rm -rf "$layout"
mkdir -p "$layout"
# mixed paths (D:/a/...) work for Git's bash and for the Windows programs it starts (dotnet,
# curl, Python) alike, whether or not MSYS converts arguments (the release job sets
# MSYS_NO_PATHCONV=1, and /d/a/... then reached dotnet as D:\d\a\..., run 45804848973)
native() { if command -v cygpath >/dev/null; then cygpath -m "$1"; else echo "$1"; fi; }
layout=$(native "$(cd "$layout" && pwd)")
core="$layout/core"
mkdir -p "$core/bin"
work=$(native "$(mktemp -d)")
trap 'rm -rf "$work"' EXIT

fetch() { # url, file, sha256
  # best effort for revocation: a company proxy that inspects TLS hides the lists (owner's PC)
  curl -fsSL --retry 3 --ssl-revoke-best-effort -o "$2" "$1"
  echo "$3  $2" | sha256sum -c - >/dev/null
}

echo "== the app"
# built, not published: `dotnet publish` of the unpackaged WinUI app leaves out its own
# resources (Stickler.pri and the compiled XAML), and the installed app ended at once on the
# runner (run 45807640975); the self-contained build's folder is the one win.yml starts
"${DOTNET:-dotnet}" build win/Stickler/Stickler.csproj -c Release -p:Platform=x64 \
  -p:SticklerInstalled=true -o "$layout" --nologo
rm -f "$layout"/*.pdb

echo "== Python $PYTHON_VERSION"
fetch "https://github.com/astral-sh/python-build-standalone/releases/download/$PYTHON_BUILD/cpython-$PYTHON_VERSION+$PYTHON_BUILD-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" \
  "$work/python.tar.gz" "$PYTHON_SHA256"
tar --force-local -xzf "$work/python.tar.gz" -C "$core" # unpacks to python/ (a D: path is no host)
py="$core/python/python.exe"
unzip_to() { "$py" -I -B -m zipfile -e "$1" "$2"; } # archive, folder

echo "== uv $UV_VERSION"
fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-pc-windows-msvc.zip" \
  "$work/uv.zip" "$UV_SHA256"
unzip_to "$work/uv.zip" "$work/uv"
cp "$work/uv/uv.exe" "$core/bin/uv.exe"
fetch "https://raw.githubusercontent.com/astral-sh/uv/$UV_VERSION/LICENSE-MIT" \
  "$work/uv-LICENSE-MIT" "$UV_MIT_SHA256"
fetch "https://raw.githubusercontent.com/astral-sh/uv/$UV_VERSION/LICENSE-APACHE" \
  "$work/uv-LICENSE-APACHE" "$UV_APACHE_SHA256"

echo "== ffmpeg $FFMPEG_VERSION"
fetch "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-$FFMPEG_VERSION-essentials_build.zip" \
  "$work/ffmpeg.zip" "$FFMPEG_SHA256"
unzip_to "$work/ffmpeg.zip" "$work/ffmpeg"
ff="$work/ffmpeg/ffmpeg-$FFMPEG_VERSION-essentials_build"
cp "$ff/bin/ffmpeg.exe" "$ff/bin/ffprobe.exe" "$core/bin/"
cp "$ff/LICENSE" "$work/ffmpeg-LICENSE.txt"
cp "$ff/README.txt" "$work/ffmpeg-README.txt" # the build's configuration and its libraries

echo "== the core's packages, as uv.lock pins them"
# the benchmark's and the command line's packages stay out (mir-eval with scipy; typer)
"$core/bin/uv.exe" export --frozen --no-dev --no-emit-project --prune mir-eval --prune typer \
  --format requirements-txt --output-file "$work/requirements.txt" >/dev/null
"$py" -I -B -m pip install --quiet --disable-pip-version-check --no-deps --require-hashes \
  --only-binary :all: --no-compile -r "$work/requirements.txt"

echo "== the core"
site=$(cygpath -u "$("$py" -I -B -c 'import sysconfig; print(sysconfig.get_path("purelib"))')")
version=$(sed -n 's/^version = "\([0-9]*\)".*/\1/p' pyproject.toml)
cp -R src/stickler src/stickler_app "$site/"
mkdir -p "$site/stickler-$version.dist-info"
printf 'Metadata-Version: 2.1\nName: stickler\nVersion: %s\n' "$version" \
  >"$site/stickler-$version.dist-info/METADATA"

echo "== the adapters' sources"
git ls-files adapters | while IFS= read -r file; do
  mkdir -p "$core/python/share/stickler/$(dirname "$file")"
  cp "$file" "$core/python/share/stickler/$file"
done

echo "== translations"
tool() { "$py" -I -B scripts/mac_bundle_tools.py "$@"; }
for po in po/*.po; do
  tool mo "$po" "$core/python/share/locale/$(basename "$po" .po)/LC_MESSAGES/stickler.mo"
done

echo "== without what the core never runs"
before=$(du -sm "$core/python" | cut -f1)
tool prune "$core/python"
echo "Python: $before MB → $(du -sm "$core/python" | cut -f1) MB"

echo "== licences"
# the app's runtimes too: .NET, the Windows App SDK (Microsoft's own terms), WebView2's loader
packages=$("${DOTNET:-dotnet}" nuget locals global-packages --list | sed -n 's/^global-packages: //p' | tr -d '\r')
mapfile -t runtimes < <(tool app-licences "$layout/Stickler.deps.json" "$packages" "$work/notes" | tr -d '\r')
tool licenses "$core" "uv=$work/uv-LICENSE-MIT" "uv=$work/uv-LICENSE-APACHE" \
  "ffmpeg=$work/ffmpeg-LICENSE.txt" "ffmpeg=$work/ffmpeg-README.txt" "stickler=LICENSE" \
  "${runtimes[@]}"

echo "== nothing missing, nothing too much"
tool check "$core"
# the pruned Python still runs the core's entry points (a pattern too wide once took threading)
"$py" -I -B -c 'import stickler_app.bridge, stickler_app.uninstall'
for part in Stickler.exe Stickler.ico Stickler.pri App.xbf MainWindow.xbf Strings/en.json Leipzig.ttf; do
  test -f "$layout/$part" || { echo "missing: $part" >&2; exit 1; }
done

echo "== sizes"
du -sh "$core/bin/uv.exe" "$core/bin/ffmpeg.exe" "$core/bin/ffprobe.exe" "$core/python" \
  "$core/python/share" "$core" "$layout"
