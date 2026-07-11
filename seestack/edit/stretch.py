"""Data-driven Strength + Black point for the editor's asinh ``tone.stretch`` op.

The Stretch op is the single most consequential editor control, yet — unlike
Levels (black/white/gamma), Sharpen, Denoise, Star-size and Deconv-PSF — its two
asinh sliders (``stretch`` = how hard to lift faint detail, ``black`` = the black
point) are still hand-guessed. This module derives a good pair straight from the
run's own linear data, so a beginner gets a well-exposed asinh stretch — the sky
landed at a pleasant target grey, the sky floor put at black — the same idiom the
other "From your image" buttons use.

The maths mirrors :func:`seestack.render.thumbnail.asinh_stretch` exactly (that's
the op this suggests for), so the suggested values reproduce its behaviour:

  * asinh normalizes the whole image to ``[0, 1]`` by its global finite min and a
    robust 99.5th-percentile max (so one hot pixel can't crush the range), then
    per channel clips a shadow floor at ``shadows = median + (6·black − 2)·σ``
    and maps ``x = (v − shadows)/(1 − shadows)`` through
    ``arcsinh(x/a) / arcsinh(1/a)`` with ``a = 0.004**stretch``.
  * **Black point** — we put the sky floor (a low percentile of the finite
    pixels) at black, exactly as :func:`seestack.edit.levels.suggest_levels_points`
    does for the Levels black point, and invert the ``shadows`` formula for the
    ``black`` slider that lands it there.
  * **Strength** — with that black point fixed, we solve (numerically; the asinh
    response is monotonic in ``stretch``) for the ``stretch`` that maps the sky
    median to :data:`STRETCH_TARGET_BG`, the same target grey the STF autostretch
    aims its sky at.

Pure-numpy and engine-side so it's testable in isolation from the webapp. NaN =
uncovered (mosaic gaps) and is excluded from every statistic.
"""

from __future__ import annotations

import math

import numpy as np

#: The display-space grey the strength suggestion lands the image's sky median
#: at — a clean dark-sky level. It is deliberately *lower* than the STF
#: autostretch's 0.20: asinh's curve is far gentler than STF's midtones transfer
#: function, so on a typical Seestar stack (where a handful of near-saturated
#: stars set the normalization ceiling) even full strength lands the sky well
#: below 0.20. 0.10 is a level asinh can actually reach on most stacks — giving a
#: punchy dark sky with faint signal lifted clear of black — so the suggested
#: strength lands on a meaningful intermediate value instead of always maxing
#: out. On a very high-dynamic-range stack even full strength can't reach it, and
#: the suggestion then correctly clamps to 1.0 (max lift). Exposed so the webapp
#: can name the goal the suggested strength solves for rather than a bare number.
STRETCH_TARGET_BG = 0.10

#: asinh softening sweep base: ``a = _ASINH_A_BASE ** stretch`` (1.0 ≈ linear at
#: stretch=0 down to a very aggressive lift at stretch=1). Kept in step with
#: :func:`seestack.render.thumbnail.asinh_stretch`.
_ASINH_A_BASE = 0.004


def _robust_median_sigma(v: np.ndarray) -> tuple[float, float]:
    """Median and MAD-based sigma of ``v`` (finite pixels only), resistant to
    bright stars — mirrors the estimator inside :func:`asinh_stretch`."""
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med)))
    sigma = 1.4826 * mad if mad > 0 else float(v.std() or 1e-3)
    return med, sigma


def _asinh_out(x: float, stretch: float) -> float:
    """The asinh response ``arcsinh(x/a) / arcsinh(1/a)`` at a given ``stretch``,
    for a normalized, shadow-clipped value ``x`` in ``[0, 1]``. Monotonic
    increasing in ``stretch``, so a bisection can invert it for the target."""
    a = _ASINH_A_BASE ** float(min(max(stretch, 0.0), 1.0))
    return math.asinh(x / a) / math.asinh(1.0 / a)


def suggest_asinh_stretch(
    rgb: np.ndarray,
    target_bg: float = STRETCH_TARGET_BG,
    black_pct: float = 1.0,
) -> tuple[float, float] | None:
    """Suggest ``(stretch, black)`` for the asinh ``tone.stretch`` op.

    ``rgb`` is the image *as it enters the Stretch op* — i.e. still linear (the
    stretch is what maps to display space), the raw stacked proxy with any
    prior linear ops applied. Returns ``None`` — no useful suggestion — when
    there are too few finite pixels, the data has no dynamic range, or the sky
    median doesn't sit above the chosen black floor.

    Both values are clamped to the op's ``[0, 1]`` slider range and rounded to a
    slider-friendly precision.
    """
    img = np.asarray(rgb, dtype=np.float64)
    finite = img[np.isfinite(img)]
    if finite.size < 100:
        return None
    lo = float(finite.min())
    hi = float(np.percentile(finite, 99.5))
    if not math.isfinite(hi) or hi <= lo:
        hi = float(finite.max())             # degenerate/near-flat image
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return None
    # Same global min / robust-99.5th-percentile normalize asinh does, so our
    # median/sigma live in the same [0, 1] space its shadow-clip formula does.
    norm = (finite - lo) / (hi - lo)
    median, sigma = _robust_median_sigma(norm)
    if sigma <= 0:
        return None

    if not (0.0 < target_bg < 1.0):
        return None

    # Black point: put the sky floor (a low percentile of the finite pixels) at
    # black. Invert asinh's ``shadows = median + (6·black − 2)·σ`` for the
    # ``black`` slider that lands ``shadows`` at that floor.
    floor = float(np.percentile(norm, black_pct))
    black = (2.0 + (floor - median) / sigma) / 6.0
    black = min(max(black, 0.0), 1.0)

    # Reproduce asinh's own shadow clip (from this black) so the strength we
    # solve for is faithful to what the op will actually do.
    shadows = min(max(median + (6.0 * black - 2.0) * sigma, 0.0), 0.999)
    rng = max(1.0 - shadows, 1e-6)
    x_med = (median - shadows) / rng
    if x_med <= 0.0:
        return None

    # Strength: solve _asinh_out(x_med, stretch) = target_bg by bisection (the
    # response is monotonic in stretch). Clamp to the endpoints when the target
    # is already met at stretch 0 or can't be reached even at stretch 1.
    if _asinh_out(x_med, 0.0) >= target_bg:
        stretch = 0.0
    elif _asinh_out(x_med, 1.0) <= target_bg:
        stretch = 1.0
    else:
        lo_s, hi_s = 0.0, 1.0
        for _ in range(40):
            mid = 0.5 * (lo_s + hi_s)
            if _asinh_out(x_med, mid) < target_bg:
                lo_s = mid
            else:
                hi_s = mid
        stretch = 0.5 * (lo_s + hi_s)

    return round(float(stretch), 3), round(float(black), 3)
