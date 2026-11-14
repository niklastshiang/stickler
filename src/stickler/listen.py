"""Listening snippets for judging error spots by ear (SPEC.md, "Release 3").

A snippet is the passage around a spot, played twice with a short pause: first plain, then with
a click at the moment in question. The music is on the left channel, the click alone on the
right, like `stickler align`'s click.wav: in the same ear, the drums mask a marker (measured on
the first trial snippets: a soft tone mixed in was inaudible). The owner answers "is there a
<drum> hit at the marker?" without knowing whether the reference or a model claims it. The drum
stem carries the passage; the mix is mixed in quietly for context (and against stem artefacts).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from stickler import audio

SR = 22050
BEFORE, AFTER = 2.5, 1.5  # seconds of music before and after the spot
GAP = 0.7  # pause between the plain and the marked pass
STEM_WEIGHT, MIX_WEIGHT = 1.0, 0.35
PEAK = 0.8  # the passage is normalised to this peak, so quiet songs are as audible as loud ones
MARKER_FREQ = 1000.0
MARKER_SECONDS = 0.04
MARKER_LEVEL = 0.9  # alone in its ear, so it can be as loud as the music
LOOP_BEFORE, LOOP_AFTER = 0.75, 0.5  # the loop: just the spot, to hear it again and again
FADE = 0.01  # seconds faded in and out at the loop's ends, so the seam does not click


@dataclass(frozen=True)
class Snippet:
    signal: np.ndarray  # (frames, 2): music left, marker right; passage, pause, passage again
    sr: int
    marker: float  # seconds into `signal` where the marker starts


def _passage(
    mix: np.ndarray, stem: np.ndarray, time: float, sr: int, before: float, after: float
) -> tuple[np.ndarray, int]:
    """Drum stem plus some mix around `time`, normalised; and the spot's index in it."""
    start = max(0, int(round((time - before) * sr)))
    end = min(len(mix), len(stem), int(round((time + after) * sr)))
    passage = STEM_WEIGHT * stem[start:end] + MIX_WEIGHT * mix[start:end]
    peak = float(np.max(np.abs(passage))) if passage.size else 0.0
    if peak > 0:
        passage = passage * (PEAK / peak)
    return passage, int(round(time * sr)) - start


def _marker(frames: int, at: int, sr: int, freq: float) -> np.ndarray:
    t = np.arange(int(MARKER_SECONDS * sr)) / sr
    click = MARKER_LEVEL * np.exp(-t * 120) * np.cos(2 * np.pi * freq * t)
    marker = np.zeros(frames)
    n = max(0, min(len(click), frames - at))
    marker[at : at + n] = click[:n]
    return marker


def render(
    mix: np.ndarray,
    stem: np.ndarray,
    time: float,
    sr: int = SR,
    marker_freq: float = MARKER_FREQ,
) -> Snippet:
    """The snippet for a spot at `time` seconds; mix and stem are mono at `sr`."""
    passage, at = _passage(mix, stem, time, sr, BEFORE, AFTER)
    gap = np.zeros(int(GAP * sr))
    music = np.concatenate([passage, gap, passage])
    marker = _marker(len(passage), at, sr, marker_freq)
    right = np.concatenate([np.zeros_like(passage), gap, marker])
    return Snippet(np.stack([music, right], axis=1), sr, (len(passage) + len(gap) + at) / sr)


def render_loop(
    mix: np.ndarray,
    stem: np.ndarray,
    time: float,
    sr: int = SR,
    marker_freq: float = MARKER_FREQ,
) -> Snippet:
    """Only the spot, with the click, to be played in a loop (ends faded)."""
    passage, at = _passage(mix, stem, time, sr, LOOP_BEFORE, LOOP_AFTER)
    n = min(int(FADE * sr), len(passage) // 2)
    if n:
        ramp = np.linspace(0.0, 1.0, n)
        passage[:n] *= ramp
        passage[-n:] *= ramp[::-1]
    marker = _marker(len(passage), at, sr, marker_freq)
    return Snippet(np.stack([passage, marker], axis=1), sr, at / sr)


def write(path: Path, snippet: Snippet) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return audio.write_wav(path, snippet.signal, snippet.sr)
