"""NaN-aware per-channel histogram of a display-space (or linear) RGB image."""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import as_rgb

# A channel's sky-background median must sit this far (in display [0,1] units)
# from the mean of the three before we call the background "cast" rather than
# neutral. ~1% of range is comfortably below the ~2% decimation-parity floor the
# other proxy advisories live with, yet catches the faint green/magenta casts the
# audit notes measured on real Auto exports (e.g. R/G/B 0.243/0.209/0.243).
_SKY_CAST_TOL = 0.01

# Colour name for the *dominant* sky-background deviation: a channel that reads
# high tints the sky its own colour; a channel that reads low tints it the
# complementary colour (low green → magenta, low red → cyan, low blue → yellow).
_CAST_HIGH = {0: "red", 1: "green", 2: "blue"}
_CAST_LOW = {0: "cyan", 1: "magenta", 2: "yellow"}


def sky_channel_medians(rgb: np.ndarray) -> list[float] | None:
    """Robust per-channel sky-background medians of an RGB image, or ``None``.

    The *sky population* is the finite pixels at or below the luminance median,
    so bright stars/target don't pull the medians (the same trick
    ``presets.analyze_proxy`` / ``classify_target`` use). Returns a 3-list of the
    R/G/B sky medians in the image's own units, or ``None`` when there aren't
    enough finite sky pixels to measure (a failed/empty stack). Shared by
    :func:`measure_sky_cast` (the read-out) and the ``tone.neutralize_background``
    op (the one-click fix), so both anchor on the *same* sky population. Read-only,
    side-effect free."""
    img = as_rgb(rgb)
    lum = img[..., :3].mean(axis=2)
    finite_mask = np.isfinite(lum)
    if int(finite_mask.sum()) < 16:
        return None
    med = float(np.median(lum[finite_mask]))
    # Sky = finite pixels at or below the luminance median. Guard the degenerate
    # case where every finite pixel equals the median (a flat frame) by keeping
    # the whole finite population rather than an empty selection.
    sky_mask = finite_mask & (lum <= med)
    if int(sky_mask.sum()) < 16:
        sky_mask = finite_mask
    medians = []
    for idx in range(3):
        chan = img[..., idx][sky_mask]
        chan = chan[np.isfinite(chan)]
        medians.append(float(np.median(chan)) if chan.size else float("nan"))
    if not all(np.isfinite(m) for m in medians):
        return None
    return medians


def measure_sky_cast(rgb: np.ndarray) -> dict:
    """Robust per-channel sky-background medians + a plain colour-cast verdict.

    Measures the *sky population* only (see :func:`sky_channel_medians`) so bright
    stars/target don't pull the medians. Intended for the post-recipe display
    image, so a user can *see* whether their finished sky background actually
    ended up neutral.

    Returns ``{r, g, b, neutral, cast, deviation}`` where ``r/g/b`` are the sky
    medians in display ``[0, 1]``, ``deviation`` is the largest per-channel
    departure from their mean, ``neutral`` is ``deviation <= _SKY_CAST_TOL``, and
    ``cast`` names the dominant tint (``"neutral"`` when balanced). Returns
    ``None``-valued medians + ``cast="unknown"`` when there aren't enough finite
    sky pixels to measure (a failed/empty stack). Read-only, side-effect free."""
    medians = sky_channel_medians(rgb)
    if medians is None:
        return {"r": None, "g": None, "b": None,
                "neutral": True, "cast": "unknown", "deviation": 0.0}
    mean_m = sum(medians) / 3.0
    devs = [m - mean_m for m in medians]
    dominant = int(np.argmax(np.abs(devs)))
    deviation = float(abs(devs[dominant]))
    if deviation <= _SKY_CAST_TOL:
        cast = "neutral"
    elif devs[dominant] > 0:
        cast = _CAST_HIGH[dominant]
    else:
        cast = _CAST_LOW[dominant]
    return {
        "r": round(medians[0], 5),
        "g": round(medians[1], 5),
        "b": round(medians[2], 5),
        "neutral": cast == "neutral",
        "cast": cast,
        "deviation": round(deviation, 5),
    }


# The object population for :func:`measure_object_colour`: pixels standing this
# many robust sky-σ above the sky level. 2σ is the same "is this sky or is this
# something" line the background-flatten object masks draw
# (``bg/per_frame._build_object_mask_for_bg``), and it is deliberately generous —
# we want the faint outer nebulosity, which is where a colour cast shows, not
# just the core.
_OBJECT_SIGMA_ABOVE = 2.0

# …and *below* this percentile of the object population's luminance, because the
# brightest pixels are saturated star cores. A clipped core reads neutral-white
# whatever colour the nebula is, so leaving them in dilutes the very measurement
# this makes. 0.5 % is a small enough bite to leave a genuine bright core intact.
_OBJECT_BRIGHT_CLIP_PCT = 99.5

# Below this many object pixels there is nothing to measure honestly (a
# star-field with no extended target, a failed stack, a tiny proxy).
_MIN_OBJECT_PIXELS = 256


def measure_object_colour(rgb: np.ndarray) -> dict:
    """Robust *sky-subtracted* colour of the object pixels in a display image.

    The companion to :func:`measure_sky_cast`, measured on the other population:
    that one asks "did my **background** end up neutral", this one asks "what
    colour did the **thing I shot** come out". Both anchor on the same robust sky
    level (:func:`sky_channel_medians`), which is what makes this honest — a
    nebula's colour is its *excess over the sky*, not its absolute level, so a
    bright light-polluted sky can't make everything read orange.

    The object population is the finite pixels sitting ``_OBJECT_SIGMA_ABOVE``
    robust sky-σ above the sky, minus the top ``100 - _OBJECT_BRIGHT_CLIP_PCT``%
    by luminance (saturated star cores read neutral-white and would dilute the
    hue). Per channel we take the median of ``pixel - sky_median`` over that
    population, clipped at zero.

    Returns ``{r, g, b, fraction, balance, green_excess, measured}`` where
    ``r/g/b`` are those sky-subtracted medians in display ``[0, 1]`` units,
    ``fraction`` is the share of finite pixels the population covers,
    ``balance`` is ``(r - b) / (r + b)`` in ``[-1, 1]`` (positive = warmer than
    blue), ``green_excess`` is how far green stands above the stronger of red and
    blue as a share of the total, and ``measured`` is ``False`` when there was
    nothing to measure (in which case the numbers are ``None``). Read-only,
    side-effect free; the verdict itself lives in :mod:`seestack.colourcheck`.
    """
    unmeasured = {"r": None, "g": None, "b": None, "fraction": 0.0,
                  "balance": None, "green_excess": None, "measured": False}
    sky = sky_channel_medians(rgb)
    if sky is None:
        return unmeasured
    img = as_rgb(rgb)
    lum = img[..., :3].mean(axis=2)
    finite = np.isfinite(lum)
    n_finite = int(finite.sum())
    if n_finite < _MIN_OBJECT_PIXELS:
        return unmeasured
    # Robust σ of the *sky* itself, read from the lower half of the luminance
    # distribution only, so the target's own pixels cannot inflate it: for a
    # Gaussian sky the gap between the median and the 15.87th percentile is
    # exactly 1σ. (A MAD of that same lower half looks like the obvious choice
    # and is wrong — the half is truncated at its own median, so the MAD comes
    # out well under σ and the "object" threshold below then admits a third of a
    # pure-noise frame.)
    vals = lum[finite]
    med_lum, lo_lum = np.percentile(vals, [50.0, 15.87])
    sigma = float(med_lum - lo_lum)
    if not np.isfinite(sigma) or sigma <= 0:
        return unmeasured
    obj = finite & (lum > float(med_lum) + _OBJECT_SIGMA_ABOVE * sigma)
    if int(obj.sum()) < _MIN_OBJECT_PIXELS:
        return unmeasured
    hi = float(np.percentile(lum[obj], _OBJECT_BRIGHT_CLIP_PCT))
    trimmed = obj & (lum <= hi)
    if int(trimmed.sum()) >= _MIN_OBJECT_PIXELS:
        obj = trimmed
    # Per channel: the object population's median *excess over the sky*. The sky
    # medians come from :func:`sky_channel_medians`, i.e. the median of the lower
    # half, which sits ~0.67σ under the true sky — so each channel keeps the same
    # small positive offset. That is deliberate: an equal offset on all three
    # only ever pulls `balance` toward zero, i.e. toward silence, so the bias
    # cannot manufacture a verdict.
    levels = []
    for idx in range(3):
        chan = img[..., idx][obj]
        chan = chan[np.isfinite(chan)]
        if not chan.size:
            return unmeasured
        levels.append(max(float(np.median(chan)) - sky[idx], 0.0))
    total = sum(levels)
    if total <= 0:
        return unmeasured
    r, g, b = levels
    balance = (r - b) / (r + b) if (r + b) > 0 else 0.0
    return {
        "r": round(r, 5), "g": round(g, 5), "b": round(b, 5),
        "fraction": round(float(obj.sum()) / float(n_finite), 5),
        "balance": round(float(balance), 5),
        "green_excess": round(float((g - max(r, b)) / total), 5),
        "measured": True,
    }


def compute_histogram(rgb: np.ndarray, bins: int = 128,
                      lo: float = 0.0, hi: float = 1.0) -> dict:
    """Return ``{bins, edges, r, g, b}`` counts over ``[lo, hi]``, ignoring NaN.

    The editor calls this on the post-recipe display image (already in ``[0, 1]``),
    so the default range suits a finished picture's histogram view.
    """
    img = as_rgb(rgb)
    edges = np.linspace(lo, hi, bins + 1, dtype=np.float64)
    out: dict = {"bins": bins, "edges": edges[:-1].round(5).tolist()}
    for idx, name in enumerate("rgb"):
        chan = img[..., idx]
        vals = chan[np.isfinite(chan)]
        if vals.size:
            counts, _ = np.histogram(np.clip(vals, lo, hi), bins=bins, range=(lo, hi))
        else:
            counts = np.zeros(bins, dtype=np.int64)
        out[name] = counts.astype(int).tolist()
    return out
