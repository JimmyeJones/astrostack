"""Data-driven starting tone curve for the editor's ``tone.curves`` op.

The Curves op is the last major tonal control that drops a beginner on a flat
identity line to hand-shape — Levels (black/white/gamma), Stretch (strength/
black), Sharpen, Denoise, Star-size and Deconv-PSF all offer a one-click "From
your image" starting point. This module derives a gentle, well-anchored midtone
lift curve straight from the display-space histogram of the image *entering* the
op, so a beginner gets a pleasant contrast start to nudge instead of a blank line.

The shape (mirroring the backlog spec) keeps the sky floor on the identity so the
background is neither crushed nor lifted, lifts the typical midtone a *touch*
toward a pleasant grey, and holds the highlight shoulder on the identity so star
cores roll off rather than blow. It is strictly monotone by construction (the
control points are sorted and strictly increasing in both x and y), so the
resulting ``np.interp`` LUT can never invert or posterise the picture.

Pure-numpy and engine-side so it's testable in isolation from the webapp. NaN =
uncovered (mosaic gaps) and is excluded from every percentile.
"""

from __future__ import annotations

import numpy as np

#: Display-space grey the midtone lift aims the image's typical tone toward — the
#: same pleasant target the Levels gamma suggestion uses. Exposed so the webapp can
#: name the goal the suggested curve solves for rather than showing a bare curve.
CURVE_TARGET_BG = 0.25

#: Fraction of the gap between the median and the target the midtone is lifted —
#: deliberately gentle (a *touch* toward the target, not all the way) so the curve
#: stays subtle and can never over-brighten into a blown, garish result.
_LIFT_FRACTION = 0.5

#: Percentiles anchoring the curve: the sky floor (kept on identity so the
#: background isn't crushed or lifted), the typical midtone (the point we lift),
#: and the highlight shoulder (kept on identity so star cores roll off). The floor
#: and shoulder use the same low/high percentiles as the Levels black/white
#: suggestion (p1 / p99.5) so the anchors stay well clear of the sky-dominated
#: median even on a sparse starfield — where p10/p90 would collapse onto it.
_SKY_PCT = 1.0
_MID_PCT = 50.0
_HIGH_PCT = 99.5

#: Minimum separation required between the anchor tones (so the curve is monotone
#: with headroom) and minimum midtone lift for a meaningful suggestion — below
#: these the curve would be imperceptible or risk collapsing, so we return
#: ``None`` and leave the identity line.
_MIN_GAP = 0.02
_MIN_LIFT = 0.01


def suggest_tone_curve(
    rgb: np.ndarray,
    target: float = CURVE_TARGET_BG,
) -> list[list[float]] | None:
    """Suggest a gentle starting tone curve for the ``tone.curves`` op.

    ``rgb`` is the image *as it enters the Curves op* — i.e. already stretched
    into display space (roughly ``[0, 1]``); percentiles on linear data would be
    meaningless (the same input :func:`seestack.edit.levels.suggest_levels_points`
    expects). Returns an ordered list of ``[x, y]`` control points (endpoints
    pinned at ``0`` and ``1``) forming a strictly-monotone midtone-lift curve, or
    ``None`` when there's no useful suggestion: too few finite pixels, a
    degenerate/flat range where the anchors would collide, or a typical tone that
    already sits at or above the target grey (nothing to lift).
    """
    finite = rgb[np.isfinite(rgb)]
    if finite.size < 100:
        return None
    if not (0.0 < target < 1.0):
        return None

    sky = min(max(float(np.percentile(finite, _SKY_PCT)), 0.0), 1.0)
    mid = min(max(float(np.percentile(finite, _MID_PCT)), 0.0), 1.0)
    high = min(max(float(np.percentile(finite, _HIGH_PCT)), 0.0), 1.0)

    # The midtone must sit strictly inside the sky→highlight range with headroom,
    # or the curve can't be monotone — a flat/degenerate image collapses them.
    if not (sky + _MIN_GAP <= mid and mid + _MIN_GAP <= high):
        return None

    # Only ever lift (never crush) the midtone, and only a gentle fraction of the
    # way to the target grey. If the typical tone is already at/above target there
    # is nothing pleasant to do — leave the identity line.
    if mid >= target:
        return None
    y_mid = mid + _LIFT_FRACTION * (target - mid)
    # Keep the lifted midtone strictly below the highlight anchor (with headroom)
    # so the curve stays monotone and the shoulder still rolls off.
    y_mid = min(y_mid, high - _MIN_GAP / 2.0)
    if y_mid - mid < _MIN_LIFT:
        return None

    # Assemble the control points. The sky floor and highlight shoulder sit on the
    # identity; drop either when it coincides with the pinned 0/1 endpoint (e.g. a
    # hard black clip lands p1 at exactly 0), which keeps the curve valid instead
    # of forcing a duplicate point.
    # Compare the *rounded* anchor against the pinned endpoints (not the raw
    # value): a sky floor of 0.0004 rounds to 0.0, and a saturated-highlight
    # p99.5 of 0.9998 rounds to 1.0 — either would duplicate a 0/1 endpoint and
    # trip the strict-monotone guard below into dropping an otherwise-valid curve.
    points: list[list[float]] = [[0.0, 0.0]]
    if round(sky, 3) > 0.0:
        points.append([round(sky, 3), round(sky, 3)])
    points.append([round(mid, 3), round(y_mid, 3)])
    if round(high, 3) < 1.0:
        points.append([round(high, 3), round(high, 3)])
    points.append([1.0, 1.0])

    # Final safety net: only return a curve that is strictly increasing in both x
    # and y (so the LUT can never invert or posterise). Rounding or an unusual
    # histogram could in principle break the ordering — bail rather than ship a
    # bad curve.
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if (any(b <= a for a, b in zip(xs, xs[1:], strict=False))
            or any(b <= a for a, b in zip(ys, ys[1:], strict=False))):
        return None
    return points
