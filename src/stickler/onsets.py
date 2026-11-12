"""Onset detection without a model: spectral flux per frequency band (numpy).

Used for the quality check of own references and for time alignment. Deliberately not a
transcription model, so that the models do not judge their own checkers.
"""

from __future__ import annotations

import numpy as np

HOP = 0.01  # s per frame
N_FFT = 1024
# kick, snare/toms, cymbals/hi-hat (Hz)
BANDS = ((20.0, 150.0), (150.0, 2500.0), (5000.0, 16000.0))
MIN_GAP = 0.04  # s: two onsets closer than this count as one
WINDOW = 0.1  # s: neighbourhood for the adaptive threshold
FLOOR = 0.05  # share of the 99th percentile below which nothing counts
# The flux peak comes before the actual attack (centred 46 ms window). Measured on MDB
# against the annotations: median −10.6 ms (oracle stems, 23 songs), −11.0 ms (Demucs, 10).
# The time axis is therefore corrected, otherwise aligned references would be early.
DETECTOR_LEAD = 0.011  # s


def _stft_mag(signal: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    hop = int(round(sr * HOP))
    padded = np.pad(signal.astype(np.float32), N_FFT // 2)
    n = 1 + (len(padded) - N_FFT) // hop
    if n < 2:
        return np.zeros((0, N_FFT // 2 + 1), dtype=np.float32), hop
    idx = np.arange(N_FFT)[None, :] + hop * np.arange(n)[:, None]
    frames = padded[idx] * np.hanning(N_FFT).astype(np.float32)
    return np.abs(np.fft.rfft(frames, axis=1)), hop


def band_flux(signal: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Times (s) and positive spectral flux per band, shape (frames, len(BANDS)).
    Mean over the frequency bins, so that wide bands do not drown out narrow ones."""
    mag, hop = _stft_mag(signal, sr)
    log = np.log1p(100.0 * mag)
    rise = np.maximum(0.0, np.diff(log, axis=0, prepend=log[:1]))
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    flux = np.stack(
        [rise[:, (freqs >= lo) & (freqs < hi)].mean(axis=1) for lo, hi in BANDS], axis=1
    )
    times = np.arange(len(flux)) * hop / sr + DETECTOR_LEAD
    return times, flux


def combined(flux: np.ndarray) -> np.ndarray:
    """Bands normalised to their 99th percentile and summed (silent bands do not count)."""
    if len(flux) == 0:
        return np.zeros(0)
    scale = np.percentile(flux, 99, axis=0)
    scale[scale <= 0] = np.inf
    return (flux / scale).sum(axis=1)


def pick_peaks(env: np.ndarray, frame_rate: float) -> np.ndarray:
    """Indices of local maxima above an adaptive threshold (mean of the neighbourhood)."""
    if len(env) == 0 or env.max() <= 0:
        return np.zeros(0, dtype=int)
    gap = max(1, int(round(MIN_GAP * frame_rate)))
    win = max(1, int(round(WINDOW * frame_rate)))
    padded = np.pad(env, win, mode="edge")
    kernel = np.ones(2 * win + 1) / (2 * win + 1)
    local = np.convolve(padded, kernel, mode="valid")
    floor = FLOOR * np.percentile(env[env > 0], 99)
    peaks = []
    for i in np.flatnonzero((env > local) & (env > floor)):
        lo, hi = max(0, i - gap), min(len(env), i + gap + 1)
        if env[i] == env[lo:hi].max() and (not peaks or i - peaks[-1] > gap):
            peaks.append(i)
    return np.array(peaks, dtype=int)


def onset_times(signal: np.ndarray, sr: int) -> np.ndarray:
    """Onset times (s) over all bands."""
    times, flux = band_flux(signal, sr)
    return times[pick_peaks(combined(flux), 1.0 / HOP)]
