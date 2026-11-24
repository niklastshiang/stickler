"""A synthetic drum clip for the spike: kicks (falling sine), snares (noise) and hi-hat ticks
at a given tempo, mono 16 bit WAV. Another tempo makes another file (the results cache keys on
the content). `python make_clip.py <out.wav> [--bpm 120] [--seconds 10]`"""

import argparse
import math
import struct
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--bpm", type=float, default=120.0)
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()
    sr = 44100
    n = int(args.seconds * sr)
    samples = [0.0] * n
    seed = 1
    step = 60.0 / args.bpm / 2  # eighth notes
    for k in range(int(args.seconds / step)):
        start = int(k * step * sr)
        hat = k % 2 == 1
        for i in range(int((0.05 if hat else 0.15) * sr)):
            if start + i >= n:
                break
            t = i / sr
            seed = (seed * 1103515245 + 12345) % 2**31
            noise = seed / 2**30 - 1
            if hat:
                samples[start + i] += 0.25 * math.exp(-t * 90) * noise
            elif k % 4 == 0:
                env = math.exp(-t * 30)
                samples[start + i] += 0.8 * env * math.sin(2 * math.pi * (60 + 80 * env) * t)
            else:
                samples[start + i] += 0.5 * math.exp(-t * 30) * noise
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))
    print(f"{args.out}: {args.seconds} s at {args.bpm} BPM")


if __name__ == "__main__":
    main()
