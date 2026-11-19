#!/bin/bash
# Builds ffmpeg and ffprobe for the Mac app from ffmpeg's own source (SPEC.md, module
# `mac-package`, decision 2): audio only, static, nothing found on the machine linked in.
# Without --enable-gpl and --enable-nonfree the result is LGPL 2.1 or later.
#
#   scripts/mac_ffmpeg.sh <folder>      # writes <folder>/ffmpeg, <folder>/ffprobe and the licence
#
# Runs on macOS arm64 with Xcode's command line tools (bash 3.2: no arrays of bash 4).
set -euo pipefail

FFMPEG_VERSION=9.0.2 # 2026-11-19: the newest release on ffmpeg.org/releases
FFMPEG_SHA256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e

out=${1:?usage: scripts/mac_ffmpeg.sh <folder>}
mkdir -p "$out"
out=$(cd "$out" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsSL --retry 3 -o "$work/ffmpeg.tar.xz" \
  "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz"
echo "$FFMPEG_SHA256  $work/ffmpeg.tar.xz" | shasum -a 256 -c -
tar -xJf "$work/ffmpeg.tar.xz" -C "$work"
cd "$work/ffmpeg-$FFMPEG_VERSION"

# What the core asks of them (src/stickler/audio.py, api.save_drum_track): read the files of
# paths.AUDIO_SUFFIXES, write FLAC, WAV and raw float samples, resample.
export MACOSX_DEPLOYMENT_TARGET=26.0
./configure \
  --arch=arm64 --cc=clang \
  --disable-everything --disable-autodetect --disable-doc --disable-debug --disable-network \
  --disable-ffplay --disable-avdevice \
  --enable-protocol=file,pipe \
  --enable-demuxer=mp3,flac,wav,w64,ogg,aiff,aac,mov,matroska \
  --enable-parser=mpegaudio,flac,vorbis,opus,aac \
  --enable-decoder=mp3,mp3float,flac,vorbis,opus,aac,alac \
  --enable-decoder=pcm_u8,pcm_s8,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le \
  --enable-decoder=pcm_s16be,pcm_s24be,pcm_s32be,pcm_f32be \
  --enable-encoder=flac,pcm_s16le,pcm_s24le,pcm_f32le \
  --enable-muxer=flac,wav,pcm_f32le,pcm_s16le \
  --enable-filter=aresample,aformat,anull,atempo,volume,pan,amix,atrim,asetpts
make -j"$(sysctl -n hw.ncpu)" ffmpeg ffprobe >/dev/null

install -m 755 ffmpeg ffprobe "$out/"
install -m 644 COPYING.LGPLv2.1 "$out/ffmpeg-COPYING.LGPLv2.1"
"$out/ffmpeg" -hide_banner -version | head -n 3
