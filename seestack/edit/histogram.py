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


def measure_sky_cast(rgb: np.ndarray) -> dict:
    """Robust per-channel sky-background medians + a plain colour-cast verdict.

    Measures the *sky population* only — the finite pixels at or below the
    luminance median — so bright stars/target don't pull the medians (the same
    trick ``presets.analyze_proxy`` / ``classify_target`` use). Intended for the
    post-recipe display image, so a user can *see* whether their finished sky
    background actually ended up neutral.

    Returns ``{r, g, b, neutral, cast, deviation}`` where ``r/g/b`` are the sky
    medians in display ``[0, 1]``, ``deviation`` is the largest per-channel
    departure from their mean, ``neutral`` is ``deviation <= _SKY_CAST_TOL``, and
    ``cast`` names the dominant tint (``"neutral"`` when balanced). Returns
    ``None``-valued medians + ``cast="unknown"`` when there aren't enough finite
    sky pixels to measure (a failed/empty stack). Read-only, side-effect free."""
    img = as_rgb(rgb)
    lum = img[..., :3].mean(axis=2)
    finite_mask = np.isfinite(lum)
    if int(finite_mask.sum()) < 16:
        return {"r": None, "g": None, "b": None,
                "neutral": True, "cast": "unknown", "deviation": 0.0}
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
