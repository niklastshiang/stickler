#!/bin/bash
# Checks the ffmpeg and ffprobe that scripts/mac_ffmpeg.sh built (SPEC.md, module
# `mac-package`; task 133): with nothing else on the PATH they read a clip of every format the
# app names, write FLAC and raw samples as the core asks for them, and tell the length.
#
#   scripts/mac_ffmpeg_test.sh <folder with ffmpeg and ffprobe> <another ffmpeg, to make clips>
#
# The second ffmpeg (Homebrew's on the runner) only makes the clips; ours has no MP3, Vorbis,
# Opus or AAC encoder.
set -euo pipefail

built=$(cd "${1:?usage: scripts/mac_ffmpeg_test.sh <built> <ffmpeg to make clips>}" && pwd)
maker=${2:?usage: scripts/mac_ffmpeg_test.sh <built> <ffmpeg to make clips>}
clips=$(mktemp -d)
trap 'rm -rf "$clips"' EXIT

for kind in mp3 m4a flac wav ogg opus aiff; do
  "$maker" -v error -f lavfi -i "sine=frequency=440:duration=2" "$clips/clip.$kind"
done

export PATH="$built:/usr/bin:/bin:/usr/sbin:/sbin"
test "$(command -v ffmpeg)" = "$built/ffmpeg"
test "$(command -v ffprobe)" = "$built/ffprobe"
for clip in "$clips"/clip.*; do
  # as audio.readable, audio.load_mono and audio.duration call them
  ffmpeg -v error -y -i "$clip" -map 0:a:0 -c:a flac "$clip.flac"
  samples=$(ffmpeg -v error -i "$clip" -ar 22050 -f f32le - | wc -c)
  seconds=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$clip.flac")
  channels=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$clip")
  echo "$(basename "$clip"): $seconds s, $channels channel(s), $samples bytes of samples"
  case "$seconds" in 1.9* | 2.0*) ;; *) echo "wrong length" >&2; exit 1 ;; esac
  test "$samples" -gt 150000 # 2 s at 22050 Hz, 4 bytes a sample
done
# the drum track's two formats, and a song's tags
ffmpeg -v error -y -i "$clips/clip.flac" "$clips/out.wav"
ffmpeg -v error -y -i "$clips/clip.wav" "$clips/out.flac"
ffprobe -v error -show_entries format_tags -of json "$clips/clip.mp3" >/dev/null
echo "ffmpeg and ffprobe read and write what the core asks for"
