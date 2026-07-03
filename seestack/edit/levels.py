"""Data-driven black/white points for the editor's ``tone.levels`` op.

The Levels op makes a beginner hand-guess a black point and a white point on the
0..1 display-space image, when the natural values come straight from the image's
own histogram: put the black point just above the sky background and the white
point just below the brightest highlights. This module computes that pair from
low/high percentiles of the finite pixels, offered as a one-click "From your
image" suggestion (the same idiom the sharpen/denoise/star-size buttons use).

Pure-numpy and engine-side so it's testable in isolation from the webapp. NaN =
uncovered (mosaic gaps) and is excluded from the percentiles.
"""

from __future__ import annotations

import numpy as np


def suggest_levels_points(
    rgb: np.ndarray,
    lo_pct: float = 1.0,
    hi_pct: float = 99.5,
    min_gap: float = 0.05,
) -> tuple[float, float] | None:
    """Suggest ``(black, white)`` display-space points for the Levels op.

    ``rgb`` is the image *as it enters the Levels op* — i.e. already stretched
    into display space (roughly [0, 1]); percentiles on linear data would be
    meaningless. ``black`` is a low percentile of the finite pixels (just above
    the sky so the background goes black without crushing visible signal) and
    ``white`` a high percentile (just below the brightest cores so a single hot
    pixel doesn't set the white point). Returns ``None`` — no useful suggestion —
    when there are too few finite pixels or the two points would collapse to a
    near-empty range (``white - black < min_gap``), which the op treats as
    identity anyway.
    """
    finite = rgb[np.isfinite(rgb)]
    if finite.size < 100:
        return None
    black = float(np.percentile(finite, lo_pct))
    white = float(np.percentile(finite, hi_pct))
    black = min(max(black, 0.0), 1.0)
    white = min(max(white, 0.0), 1.0)
    if white - black < min_gap:
        return None
    return round(black, 3), round(white, 3)
