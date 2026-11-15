"""Matching detected onsets to reference onsets for scoring. mir_eval (and with it scipy) is
loaded on the first call, so the app, which never scores, does not need either."""

from __future__ import annotations

import numpy as np


def match_events(ref: np.ndarray, est: np.ndarray, window: float) -> list[tuple[int, int]]:
    """mir_eval.util.match_events: the largest one-to-one matching within `window` seconds."""
    from mir_eval.util import match_events as matched

    return matched(ref, est, window)
