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
median, so the original design — anchoring the sky at p1 and lifting p50 — lifted
the entire sky (measured +42 % background brightness), undoing the noise-aware
target the stretch just chose.

That anchor then had to survive two further corrections, both from the 2026-09-02
external audit's A1 finding, and both worth knowing before touching this file:

1. **The mode must ignore the stretch's hard-clip spike.** Every stretch that runs
   before this one clips its shadows to a single value (``autostretch`` lands 1–2 %
   of an ordinary stack on exactly 0.0), and that one value holds more pixels than
   any real bin, so it won *every* histogram. The sky read as ~0.0008 and the whole
   safety design collapsed: the "the median IS the sky, so decline" gate never
   fired and the background rode the lift again, +36 % through the full Auto
   recipe. :func:`_unclipped` drops it.
2. **The lifted point must clear the sky's noise, not just the sky's centre.** A
   stretched background is *wide* (σ of 0.02–0.09 in display space), and the mode
   is a jittery estimator on the near-flat histogram such a background produces —
   so p50 as the lift anchor was one estimator wobble away from sitting inside the
   grain. The anchor is now ``max(p50, sky + 3σ)``: what gets lifted is faint
   structure, and estimator error is harmless by construction.

The result is the module's original promise, actually kept: the sky stays exactly
on identity and only tones clearly above it are lifted.

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

#: Percentiles anchoring the curve above the sky: the typical midtone (a *floor*
#: for the point we lift) and the highlight shoulder (kept on identity so star
#: cores roll off, same high percentile as the Levels white suggestion, p99.5).
_MID_PCT = 50.0
_HIGH_PCT = 99.5

#: How many robust sigmas of the background the lifted point must clear. The
#: median alone is not a safe lift anchor: on a sky-dominated frame it sits *in*
#: the sky, and the sky's noise band after a stretch is wide (0.02–0.09 in display
#: space, depending on depth), so lifting p50 rides the background upward. At 3σ
#: only ~0.1 % of sky pixels sit above the lifted point, so what gets lifted is
#: faint structure rather than grain.
_SKY_MARGIN_SIGMA = 3.0

#: Minimum separation required between the anchor tones (so the curve is monotone
#: with headroom) and minimum midtone lift for a meaningful suggestion — below
#: these the curve would be imperceptible or risk collapsing, so we return
#: ``None`` and leave the identity line.
_MIN_GAP = 0.02
_MIN_LIFT = 0.01


#: Below this many un-clipped samples the floor-spike exclusion is abandoned and
#: the mode is measured over everything — a tiny or almost-entirely-clipped patch
#: has no meaningful histogram left once the floor is dropped.
_MIN_UNCLIPPED = 100


def _unclipped(finite: np.ndarray) -> np.ndarray:
    """``finite`` with the *hard-clip spike* — the pixels sitting exactly on the
    array's floor — removed.

    Every stretch this curve runs after clips its shadows: :func:`autostretch`
    subtracts ``median − 2σ`` and clamps, which lands **1–2 % of an ordinary
    Seestar stack on exactly 0.0**, and :func:`asinh_stretch` does the same at its
    black point. That spike is a *single* value holding thousands of pixels, so it
    is always the tallest bin of any histogram that includes it — it outvotes the
    real sky by construction, however the bins are drawn. It is also not a tone
    anybody sees as the sky: it is the part of the sky the stretch deliberately
    threw away.

    Dropping the floor exactly (rather than "everything ≤ 0") keeps this general:
    it catches a clip at any level, and on an *unclipped* image it removes a single
    pixel and changes nothing. Falls back to the full population when too little
    survives to measure."""
    floor = float(np.min(finite))
    pop = finite[finite > floor]
    return pop if pop.size >= _MIN_UNCLIPPED else finite


def _sky_mode(finite: np.ndarray) -> float:
    """Robust estimate of the dominant background (sky) level: the peak of the
    histogram over the image's *lower half* (``[p0.5, median]``), measured over the
    :func:`_unclipped` population so a stretch's shadow-clip spike cannot pose as
    the sky.

    The sky is always at or below the median of an astro frame — stars and any
    object pull the upper tail up, never the background down — so searching only
    the lower half finds the sky reliably whether the frame is sky-dominated (the
    median itself is the sky) or object-dominated (the median has drifted up into
    the object, but the sky is still the dominant peak below it). Searching the
    full range instead lets a *saturated* object plateau (many pixels piled in one
    bright bin) outvote the noise-spread sky and misreport the sky as near-white.

    The median stays the *whole frame's* median on purpose: it is the same number
    :func:`suggest_tone_curve` compares the sky against, and the two must agree."""
    pop = _unclipped(finite)
    lo = float(np.percentile(pop, 0.5))
    hi = float(np.median(finite))
    if not (hi > lo):
        return hi
    counts, edges = np.histogram(pop, bins=128, range=(lo, hi))
    i = int(np.argmax(counts))
    return float((edges[i] + edges[i + 1]) / 2.0)


def _sky_spread(finite: np.ndarray, sky: float) -> float:
    """Robust sigma of the background, measured from its **lower tail only**.

    Everything a frame contains above the sky — stars, the object, a gradient —
    inflates a two-sided spread, so the only uncontaminated half is the one below
    the sky level. For a Gaussian background the median absolute deviation of that
    half is ``0.6745σ``, hence the usual ``1.4826`` scaling. The hard-clip spike is
    excluded (:func:`_unclipped`): it is a pile of identical values at the bottom
    of that very tail and would otherwise stretch it.

    Returns ``0.0`` when there is too little tail to measure — the caller then
    falls back to its plain minimum-gap guard."""
    pop = _unclipped(finite)
    low = pop[pop <= sky]
    if low.size < _MIN_UNCLIPPED:
        return 0.0
    return float(1.4826 * np.median(sky - low))


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
    above the sky to lift, or a tone above the sky's noise that already sits at or
    above the target grey (nothing to lift). Callers that must produce *something*
    use :func:`fallback_tone_curve`, which is anchored on the same sky.
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
    # The point we lift must clear the background's own noise, not merely the
    # background's *centre*. Taking p50 alone was the second half of the +36 % sky
    # lift: on the sky-dominated frames the owner mostly shoots, p50 sits inside
    # the sky, and the mode is a jittery estimator on the near-flat histogram a
    # stretched sky produces — so a couple of hundredths of estimator error was
    # enough to slip the lift anchor into the background. Anchoring at
    # ``sky + 3σ`` makes that error harmless: the anchor is out of the grain by
    # construction, whatever the mode did.
    sigma = _sky_spread(finite, sky)
    mid = max(float(np.percentile(finite, _MID_PCT)), sky + _SKY_MARGIN_SIGMA * sigma)
    mid = min(max(mid, 0.0), 1.0)
    high = min(max(float(np.percentile(finite, _HIGH_PCT)), 0.0), 1.0)

    # The lift anchor must sit strictly ABOVE the sky (with headroom) and strictly
    # below the highlight shoulder, or the curve can't be monotone. With the anchor
    # now pushed clear of the noise this rarely bites, but it still catches the
    # degenerate frames (a flat image, sigma of 0) where the two would collide.
    if not (sky + _MIN_GAP <= mid and mid + _MIN_GAP <= high):
        return None

    # Only ever lift (never crush) the anchor, and only a gentle fraction of the
    # way to the target grey. If the anchor is already at/above target there is
    # nothing pleasant to do — a noisy or bright stack whose 3σ point has run past
    # the target grey lands here, and leaving the identity line (and the
    # sky-anchored fallback) is the right answer for it.
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


#: The highlight knee of the gentle fallback S-curve — the shoulder tone that gets
#: lifted when there is nothing between the sky and the stars worth lifting. Same
#: pair the built-in presets ship (and the historical fixed fallback used).
_FALLBACK_KNEE = (0.75, 0.82)


def fallback_tone_curve(rgb: np.ndarray) -> list[list[float]]:
    """The gentle contrast curve Auto falls back to when :func:`suggest_tone_curve`
    finds nothing to lift — **anchored on this image's own sky** rather than fixed.

    The historical fallback was the constant ``[[0,0],[0.25,0.2],[0.75,0.82],[1,1]]``.
    Its lower knee *darkens* everything below 0.25, and the frames that reach the
    fallback are exactly the sky-dominated ones whose sky the stretch just placed at
    0.18–0.25 — so the one curve meant to be a safe default was **dimming the
    background by ~20 %** on the pictures it ran on most. Auto's whole contract is
    that the noise-aware stretch decides where the sky sits and nothing downstream
    moves it.

    So: identity from black up through the measured sky, then the same gentle
    shoulder lift above it. The sky is pinned to itself, structure above it gains a
    little contrast, and the shoulder still rolls back onto the identity at white.
    Returns the plain identity when the sky sits at or above the knee (a bright
    image with no room left to shape) or the histogram is unusable — never a curve
    that moves the background."""
    identity: list[list[float]] = [[0.0, 0.0], [1.0, 1.0]]
    finite = rgb[np.isfinite(rgb)]
    if finite.size < 100:
        return identity
    # Anchor at the HIGHER of the measured sky and the frame's median. A frame only
    # reaches the fallback because it has nothing above its background worth
    # lifting — which is to say its median *is* background — so the median is a
    # sound floor for "what must not move", and taking the higher of the two makes
    # the mode's estimator error harmless in the safe direction. (On the one scene
    # where the mode reads 0.12 for a 0.18 sky — an objectless, star-poor frame
    # whose histogram is nearly flat — anchoring on the mode alone still lifted the
    # background 3.6 %; the median floor takes that to nil.)
    sky = round(min(max(max(_sky_mode(finite), float(np.median(finite))), 0.0), 1.0), 3)
    kx, ky = _FALLBACK_KNEE
    # The knee must sit clearly above the sky (with the same headroom the suggested
    # curve demands) or the segment between them would be near-vertical — a harsh,
    # noise-amplifying slope, not a gentle lift.
    if not (sky > 0.0 and sky + _MIN_GAP <= kx):
        return identity
    return [[0.0, 0.0], [sky, sky], [kx, ky], [1.0, 1.0]]
