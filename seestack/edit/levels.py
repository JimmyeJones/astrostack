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

#: The display-space grey the midtone (gamma) suggestion aims the image's typical
#: tone at, after the black/white points are applied. Exposed so the webapp can
#: tell the user *what goal* the suggested gamma solves for ("lands the sky at
#: ~25% grey") rather than showing a bare number.
GAMMA_TARGET = 0.25


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


def suggest_levels_gamma(
    rgb: np.ndarray,
    black: float,
    white: float,
    target: float = GAMMA_TARGET,
    min_lift: float = 1.05,
) -> float | None:
    """Suggest a midtone ``gamma`` for the Levels op so the image's typical tone
    lands at a pleasant target grey after the black/white points are applied.

    The Levels op maps a finite pixel ``v`` to ``x**(1/gamma)`` where
    ``x = clip((v - black) / (white - black), 0, 1)``. We take the median of the
    finite pixels (the sky/background-dominated typical tone), find where it falls
    after the black/white remap, and solve ``x_m**(1/gamma) = target`` for
    ``gamma = ln(x_m) / ln(target)`` — a midtone lift that brightens the picture
    the same way the black/white auto-levels sets its endpoints, without moving
    black or white.

    ``rgb`` must be the image *as it enters the Levels op* (display space, roughly
    ``[0, 1]``), the same input as :func:`suggest_levels_points`. Returns ``None``
    (leave gamma at 1.0) when there aren't enough finite pixels, the range is
    degenerate, the median doesn't sit strictly between black and white, or the
    resulting lift is too small to matter (``< min_lift``). NaN = uncovered and is
    excluded. The result is clamped to the op's ``[0.1, 5.0]`` range.
    """
    rng = white - black
    if rng <= 0:
        return None
    finite = rgb[np.isfinite(rgb)]
    if finite.size < 100:
        return None
    median = float(np.median(finite))
    x_m = (median - black) / rng
    # The median must land strictly inside (0, 1) after the remap, and below the
    # target (so a lift, not a crush) for a meaningful gamma to exist.
    if not (0.0 < x_m < 1.0) or not (0.0 < target < 1.0) or x_m >= target:
        return None
    gamma = np.log(x_m) / np.log(target)
    if not np.isfinite(gamma) or gamma < min_lift:
        return None
    return round(float(min(max(gamma, 0.1), 5.0)), 3)
