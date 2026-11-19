#!/bin/sh
# Builds Stickler-<version>-x86_64.AppImage with quick-sharun (SPEC.md, module `packaging`).
# It runs inside the Arch Linux image of the Anylinux AppImages project, as their examples do:
#
#   podman run --rm -v "$PWD":/src:Z -w /src ghcr.io/pkgforge-dev/archlinux:latest \
#     sh scripts/appimage.sh                    # the AppImage lands in dist/
#
# Run it on a copy of the repository's files (as CI's checkout is), not on a working tree with
# the adapters' environments: `git ls-files -co --exclude-standard | tar -cf - -T - | tar -x ...`.
# The app is installed into /usr first (quick-sharun collects what /usr/bin/stickler-gtk needs);
# the adapters' environments and weights never go in.
set -eu

QUICK_SHARUN_COMMIT=6f09e6efc7f370f51f57b9d60b98745d3080de80 # pinned: it changes almost daily
UV_VERSION=0.13.9 # one version in every package (tests/test_mac_bundle.py)
UV_SHA256=58ccf5f1792b8a5a88d01bc910ea131a8b3db4a319a17ad5fad75e0845a3e271
VERSION=$(sed -n 's/^version = "\([0-9]*\)".*/\1/p' pyproject.toml)

echo "== packages"
pacman -Syu --noconfirm --needed \
	base-devel git wget zsync patchelf 7zip jq xorg-server-xvfb \
	python python-pip python-gobject python-cairo \
	gtk4 libadwaita librsvg gdk-pixbuf2 hicolor-icon-theme \
	gstreamer gst-plugins-base gst-plugins-good gst-libav \
	ffmpeg gettext

echo "== quick-sharun and the debloated packages, $QUICK_SHARUN_COMMIT"
tools="https://raw.githubusercontent.com/pkgforge-dev/Anylinux-AppImages/$QUICK_SHARUN_COMMIT/useful-tools"
wget -q -O /usr/local/bin/quick-sharun "$tools/quick-sharun.sh"
wget -q -O /usr/local/bin/get-debloated-pkgs "$tools/get-debloated-pkgs.sh"
chmod +x /usr/local/bin/quick-sharun /usr/local/bin/get-debloated-pkgs
# Arch's mesa pulls in LLVM (100+ MB) and needs new kernels; the project's builds do not
get-debloated-pkgs --add-common --prefer-nano

echo "== the app's Python packages: the wheels of uv.lock (packaging/flatpak/python-deps.json)"
python3 - <<'EOF' > /tmp/requirements.txt
import json
for source in json.load(open("packaging/flatpak/python-deps.json"))["sources"]:
    print(f"{source['url']} --hash=sha256:{source['sha256']}")
EOF
pip install --break-system-packages --no-deps --require-hashes -r /tmp/requirements.txt

echo "== uv $UV_VERSION"
wget -q -O /tmp/uv.tar.gz \
	"https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-musl.tar.gz"
echo "$UV_SHA256  /tmp/uv.tar.gz" | sha256sum -c -
tar -xzf /tmp/uv.tar.gz -C /tmp
install -Dm755 /tmp/uv-x86_64-unknown-linux-musl/uv /usr/bin/uv

echo "== Stickler into /usr"
site=$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
cp -r src/stickler src/stickler_app src/stickler_gtk "$site/"
install -Dm755 packaging/flatpak/stickler-gtk /usr/bin/stickler-gtk
find adapters -type f \
	-not -path '*/.venv*' -not -path '*/weights/*' -not -path '*/__pycache__/*' |
	while read -r file; do
		install -Dm644 "$file" "/usr/share/stickler/$file"
	done
install -Dm644 packaging/fonts/Leipzig.ttf /usr/share/fonts/stickler/Leipzig.ttf
install -Dm644 packaging/icons/ng.tshia.Stickler.svg \
	/usr/share/icons/hicolor/scalable/apps/ng.tshia.Stickler.svg
install -Dm644 packaging/icons/ng.tshia.Stickler-symbolic.svg \
	/usr/share/icons/hicolor/symbolic/apps/ng.tshia.Stickler-symbolic.svg
install -Dm644 packaging/ng.tshia.Stickler.desktop /usr/share/applications/ng.tshia.Stickler.desktop
install -Dm644 packaging/ng.tshia.Stickler.metainfo.xml \
	/usr/share/metainfo/ng.tshia.Stickler.metainfo.xml
install -Dm644 LICENSE /usr/share/licenses/stickler/LICENSE
for po in po/*.po; do
	lang=$(basename "$po" .po)
	install -d "/usr/share/locale/$lang/LC_MESSAGES"
	msgfmt --check -o "/usr/share/locale/$lang/LC_MESSAGES/stickler.mo" "$po"
done

echo "== AppImage"
export ARCH=x86_64
export OUTPATH=./dist
export VERSION
export ICON=/usr/share/icons/hicolor/scalable/apps/ng.tshia.Stickler.svg
export DESKTOP=/usr/share/applications/ng.tshia.Stickler.desktop
export UPINFO="gh-releases-zsync|niklastshiang|stickler|latest|Stickler-*-x86_64.AppImage.zsync"
export DEPLOY_PYTHON=1
export DEPLOY_GTK=1
export GTK_DIR=gtk-4.0
export DEPLOY_GSTREAMER=1
export DEPLOY_PULSE=1
export DEPLOY_LOCALE=1
export STARTUPWMCLASS=ng.tshia.Stickler # Wayland's app ID
# No GTK_CLASS_FIX: its preloaded library prints a line in every process, ffprobe's too, and the
# app reads ffprobe's output (an AppImage analysis failed: "ffprobe: …: Setting window class").
rm -rf ./AppDir ./dist
quick-sharun /usr/bin/stickler-gtk \
	/usr/lib/libgirepository* \
	/usr/lib/gio/modules/libgiognutls.so* \
	/usr/lib/librsvg-2.so* \
	/usr/bin/ffmpeg /usr/bin/ffprobe /usr/bin/uv
mkdir -p ./AppDir/share/stickler ./AppDir/share/fonts
cp -r /usr/share/stickler/adapters ./AppDir/share/stickler/
cp -r /usr/share/fonts/stickler ./AppDir/share/fonts/
# quick-sharun keeps the translations of the libraries it knows, not the app's own
for po in po/*.po; do
	lang=$(basename "$po" .po)
	install -Dm644 "/usr/share/locale/$lang/LC_MESSAGES/stickler.mo" \
		"./AppDir/share/locale/$lang/LC_MESSAGES/stickler.mo"
done
# every file the app looks for under its prefix must be there
for needed in share/stickler/adapters/_common/pyproject.toml share/fonts/stickler/Leipzig.ttf \
	share/icons/hicolor/scalable/apps/ng.tshia.Stickler.svg; do
	[ -f "./AppDir/$needed" ] || { echo "missing in the AppImage: $needed" >&2; exit 1; }
done
for po in po/*.po; do
	mo="./AppDir/share/locale/$(basename "$po" .po)/LC_MESSAGES/stickler.mo"
	[ -f "$mo" ] || { echo "missing in the AppImage: $mo" >&2; exit 1; }
done
quick-sharun --make-appimage
for built in dist/*.AppImage; do
	mv "$built" "dist/Stickler-$VERSION-x86_64.AppImage"
done
for zsync in dist/*.zsync; do
	[ -e "$zsync" ] && mv "$zsync" "dist/Stickler-$VERSION-x86_64.AppImage.zsync"
done
ls -la dist
