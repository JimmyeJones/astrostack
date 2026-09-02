"""Data-driven starting tone curve for the editor's ``tone.curves`` op.

The Curves op is the last major tonal control that drops a beginner on a flat
identity line to hand-shape — Levels (black/white/gamma), Stretch (strength/
black), Sharpen, Denoise, Star-size and Deconv-PSF all offer a one-click "From
your image" starting point. This module derives a gentle, well-anchored midtone
lift curve straight from the display-space histogram of the image *entering* the
op, so a beginner gets a pleasant contrast start to nudge instead of a blank line.

The shape keeps the *sky* on the identity so the background is neither crushed
nor lifted, lifts a typical midtone that sits **above** the sky a *touch* toward
a pleasant grey, and holds the highlight shoulder on the identity so star cores
roll off rather than blow. It is strictly monotone by construction (the control
points are sorted and strictly increasing in both x and y), so the resulting
``np.interp`` LUT can never invert or posterise the picture.

The sky anchor is the histogram **mode** (the dominant background level), not a
fixed low percentile. On a deep-sky frame the *bulk* of the sky sits at the
median, so the old design — anchoring the sky at p1 and lifting p50 — lifted the
entire sky (measured +42 % background brightness), undoing the noise-aware target
the stretch just chose. Anchoring at the mode keeps the sky exactly on identity
and lifts only tones clearly above it (the faint structure a beginner actually
wants to bring out).

Pure-numpy and engine-side so it's testable in isolation from the webapp. NaN =
uncovered (mosaic gaps) and is excluded from every percentile.
"""

from __future__ import annotations

import numpy as np

#: Display-space grey the midtone lift aims the image's typical tone toward — the
#: same pleasant target the Levels gamma suggestion uses. Exposed so the webapp can
#: name the goal the suggested curve solves for rather than showing a bare curve.
CURVE_TARGET_BG = 0.25

#: Fraction of the gap between the midtone and the target the midtone is lifted —
#: deliberately gentle (a *touch* toward the target, not all the way) so the curve
#: stays subtle and can never over-brighten into a blown, garish result.
_LIFT_FRACTION = 0.5

#: Percentiles anchoring the curve above the sky: the typical midtone (the point
#: we lift) and the highlight shoulder (kept on identity so star cores roll off,
#: same high percentile as the Levels white suggestion, p99.5).
_MID_PCT = 50.0
_HIGH_PCT = 99.5

#: Minimum separation required between the anchor tones (so the curve is monotone
#: with headroom) and minimum midtone lift for a meaningful suggestion — below
#: these the curve would be imperceptible or risk collapsing, so we return
#: ``None`` and leave the identity line.
_MIN_GAP = 0.02
_MIN_LIFT = 0.01

#: Minimum number of strictly-positive pixels :func:`_sky_mode` needs before it
#: will measure the sky on them alone. Below this the image is essentially all
#: black and the whole (clipped) population is the honest thing to measure.
_MIN_SKY_SAMPLES = 100

#: Where :func:`fallback_tone_curve` puts its shoulder, and how far it lifts it,
#: both as a fraction of the headroom between the sky and white. Chosen so a sky
#: of zero reproduces the old fixed S-curve's shoulder exactly (0.75 → 0.82).
_FALLBACK_SHOULDER_AT = 0.75
_FALLBACK_SHOULDER_LIFT = 0.07


def _sky_mode(finite: np.ndarray) -> float:
    """Robust estimate of the dominant background (sky) level: the peak of the
    histogram over the image's *lower half* (``[p0.5, median]``).

    The sky is always at or below the median of an astro frame — stars and any
    object pull the upper tail up, never the background down — so searching only
    the lower half finds the sky reliably whether the frame is sky-dominated (the
    median itself is the sky) or object-dominated (the median has drifted up into
    the object, but the sky is still the dominant peak below it). Searching the
    full range instead lets a *saturated* object plateau (many pixels piled in one
    bright bin) outvote the noise-spread sky and misreport the sky as near-white.

    Measured over the **strictly positive** pixels. The stretch that runs
    immediately before the Curves op (``tone.stretch``) hard-clips one to two per
    cent of the darkest pixels to *exactly* zero, and clipped shadows are not sky
    — but because they all land on one value they form the tallest bin there is,
    so counting them made the sky read as ~0.0008 on every real stack instead of
    the ~0.14 it actually sits at. (That is the whole of the "Auto brightens the
    sky" bug: with the sky reported near black, the "the median *is* the sky, so
    decline" gate in :func:`suggest_tone_curve` never fired and the lift landed on
    the background itself.) An image with no hard-clipped shadows has no zeros to
    drop, so its measurement is unchanged pixel for pixel."""
    positive = finite[finite > 0.0]
    # An image that is *almost all* zero has no positive population to measure —
    # fall back to the whole thing rather than reading a handful of stray pixels
    # as the sky. Same floor as the caller's "too few finite pixels" guard.
    if positive.size < _MIN_SKY_SAMPLES:
        positive = finite
    lo = float(np.percentile(positive, 0.5))
    hi = float(np.median(positive))
    if not (hi > lo):
        return hi
    counts, edges = np.histogram(positive, bins=128, range=(lo, hi))
    i = int(np.argmax(counts))
    return float((edges[i] + edges[i + 1]) / 2.0)


def fallback_tone_curve(rgb: np.ndarray) -> list[list[float]]:
    """The gentle contrast curve auto-contrast falls back to when
    :func:`suggest_tone_curve` declines — anchored on *this image's* sky.

    The fallback used to be the fixed S-curve ``[[0,0],[0.25,0.2],[0.75,0.82],
    [1,1]]``, and its lower control point is below the sky of a typical stretched
    stack: it pulled a 0.19 background down to ~0.15, i.e. it **darkened the sky
    by a fifth** every time the data-driven suggestion declined. Which branch runs
    is not something the user chose, so both branches have to obey the same rule —
    *never move the background* — or the one-click result depends on which side of
    a gate the stack happened to fall.

    So the shape is kept and re-expressed relative to the measured sky: the sky
    and both endpoints sit on the identity, and a single shoulder above the sky is
    lifted a touch to add contrast to the structure. At a sky of zero it reduces
    to the old curve's shoulder exactly (``0.75 → 0.82``); the old lower point is
    simply gone, because "pull 0.25 down" *is* the bug. Returns the identity when
    the image is too bright or too degenerate to place a shoulder — doing nothing
    is the right answer there, and is still better than moving the background.
    """
    finite = rgb[np.isfinite(rgb)]
    identity = [[0.0, 0.0], [1.0, 1.0]]
    if finite.size < 100:
        return identity
    sky = min(max(_sky_mode(finite), 0.0), 1.0)
    headroom = 1.0 - sky
    if headroom <= _MIN_GAP:
        return identity

    x_shoulder = sky + _FALLBACK_SHOULDER_AT * headroom
    y_shoulder = x_shoulder + _FALLBACK_SHOULDER_LIFT * headroom

    points: list[list[float]] = [[0.0, 0.0]]
    if round(sky, 3) > 0.0:
        points.append([round(sky, 3), round(sky, 3)])
    points.append([round(x_shoulder, 3), round(y_shoulder, 3)])
    if round(y_shoulder, 3) < 1.0:
        points.append([1.0, 1.0])

    # Same strict-monotone safety net as the suggested curve: rounding at a very
    # high sky could collide two points, and a non-monotone LUT would posterise.
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if (any(b <= a for a, b in zip(xs, xs[1:], strict=False))
            or any(b <= a for a, b in zip(ys, ys[1:], strict=False))):
        return identity
    return points


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
    degenerate/flat range where the anchors would collide, nothing meaningfully
    above the sky to lift, or a typical tone that already sits at or above the
    target grey (nothing to lift).
    """
    finite = rgb[np.isfinite(rgb)]
    if finite.size < 100:
        return None
    if not (0.0 < target < 1.0):
        return None

    # The sky is the histogram mode — the background level that must stay put. The
    # old design anchored the sky at p1 and lifted p50, but on a sky-dominated
    # deep-sky frame p50 *is* the sky, so the whole background rode the lift.
    sky = min(max(_sky_mode(finite), 0.0), 1.0)
    mid = min(max(float(np.percentile(finite, _MID_PCT)), 0.0), 1.0)
    high = min(max(float(np.percentile(finite, _HIGH_PCT)), 0.0), 1.0)

    # The midtone must sit strictly ABOVE the sky (with headroom) and strictly
    # below the highlight shoulder, or the curve can't be monotone — and, crucially,
    # when the median IS the sky (a sky-dominated frame with little extended signal)
    # this gate declines rather than lifting the background. Leaving the identity
    # line is the safe, correct result there: the noise-aware stretch already placed
    # the sky where it wants it.
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
