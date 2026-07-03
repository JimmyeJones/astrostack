"""Star-mask-aware local edits (no ML).

Grey-scale morphological erosion shrinks small bright features (stars) far more
than extended structure (nebulosity/galaxy), so blending in the erosion only
where it darkens reduces stars while barely touching the rest. A soft **star
mask** (see :mod:`seestack.edit.starmask`) gates the effect so the bright cores
of nebulae and galaxies — which erosion would also pull down — are protected.

The same mask drives :func:`_boost_nebula`, which lifts and saturates the
*background* (everything that isn't a star) so faint nebulosity pops without
bloating or brightening the stars.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import (
    EditContext, EditParam, OpSpec, as_rgb, finite_mask, luminance, register,
)
from seestack.edit.starmask import star_mask


def _reduce(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import grey_erosion

    amount = float(params.get("amount", 0.5))
    size = max(1, int(params.get("size", 2)))
    protect = bool(params.get("protect_nebula", True))
    out = as_rgb(rgb).copy()
    cover = finite_mask(out)
    if not cover.any() or amount <= 0:
        return out

    filled = out.copy()
    for c in range(3):
        chan = filled[..., c]
        chan[~cover] = float(np.nanmedian(chan)) if np.isfinite(chan).any() else 0.0

    # Gate the reduction to actual stars so we don't erode nebula/galaxy cores.
    gate = star_mask(out, size_px=2.0 * size, ctx=ctx) if protect else np.ones(cover.shape, np.float32)

    # Scale the erosion footprint for the decimated preview proxy exactly like the
    # star-mask gate does (starmask.py), so the preview shrinks stars by the same
    # *physical* amount the full-res export will — otherwise a `2*size+1` footprint
    # covers proxy_scale× more scene on the proxy and the preview over-reduces. On
    # the export (proxy_scale == 1) `scaled_px` is a no-op, so output is unchanged.
    fp = max(1, int(round(ctx.scaled_px(size))))
    footprint = np.ones((2 * fp + 1, 2 * fp + 1), dtype=bool)
    for c in range(3):
        eroded = grey_erosion(filled[..., c], footprint=footprint)
        # Only pull pixels down where erosion darkens them (star cores/halos),
        # and only as far as the star mask allows.
        darken = np.maximum(0.0, filled[..., c] - eroded)
        reduced = filled[..., c] - amount * gate * darken
        out[..., c][cover] = reduced[cover]
    return out


def _boost_nebula(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    """Lift + saturate the background (non-star) regions to bring out faint
    nebulosity, leaving stars untouched. Runs in display space [0, 1]."""
    amount = float(params.get("amount", 0.3))
    size = max(1, int(params.get("size", 4)))
    out = as_rgb(rgb).copy()
    cover = finite_mask(out)
    if not cover.any() or amount <= 0:
        return out

    bg = (1.0 - star_mask(out, size_px=size, ctx=ctx))[..., None]  # 1 on background
    clipped = np.clip(out, 0.0, 1.0)
    lum = luminance(clipped)[..., None]
    # Gamma lift brightens midtones; a mild saturation boost adds colour.
    gamma = max(0.2, 1.0 - 0.6 * amount)
    brightened = clipped ** gamma
    saturated = lum + (1.0 + 0.5 * amount) * (brightened - lum)
    target = np.clip(saturated, 0.0, 1.0)

    w = bg * amount  # only touch background, scaled by strength
    blended = out * (1.0 - w) + target * w
    out[cover] = blended[cover]
    return out


register(OpSpec(
    id="stars.reduce", label="Star reduction", group="stars_geometry", stage="nonlinear",
    apply=_reduce, proxy_safe=True,
    help="Shrink stars morphologically without touching nebulosity. No AI model.",
    params=[
        EditParam("amount", "Amount", "float", default=0.5, min=0.0, max=1.0, step=0.05,
                  help="How strongly to shrink stars. 0 = off; start around 0.3 and "
                       "increase — too high leaves dark holes where bright stars were."),
        EditParam("size", "Star size (px)", "int", default=2, min=1, max=8, step=1,
                  help="Roughly how big your stars are, in pixels. Match it to your "
                       "actual star size — use the 'From your stars' button below."),
        EditParam("protect_nebula", "Protect nebula", "bool", default=True, group="advanced",
                  help="Gate the reduction with a star mask so nebula/galaxy cores aren't eroded."),
    ],
))

register(OpSpec(
    id="stars.boost_nebula", label="Boost nebula", group="stars_geometry", stage="nonlinear",
    apply=_boost_nebula, proxy_safe=True,
    help="Lift and saturate the background (non-star) regions so faint nebulosity "
         "pops, leaving stars untouched.",
    params=[
        EditParam("amount", "Amount", "float", default=0.3, min=0.0, max=1.0, step=0.05,
                  help="How strongly to lift and saturate the non-star background so "
                       "faint nebulosity pops. 0 = off; start gentle."),
        EditParam("size", "Star size (px)", "int", default=4, min=1, max=12, step=1,
                  group="advanced",
                  help="Star mask footprint — larger excludes bigger stars from the boost."),
    ],
))
