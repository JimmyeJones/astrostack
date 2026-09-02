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


def star_reduce_differs_on_proxy(size: float, proxy_scale: float) -> bool:
    """True when the star-reduction live preview does not faithfully show the
    strength the full-res export will apply.

    Star reduction erodes with a footprint of ``size`` full-resolution pixels,
    divided by ``proxy_scale`` for the decimated live-preview proxy (``_reduce`` /
    :mod:`seestack.edit.starmask`) so the preview shrinks stars by the same
    *physical* amount the export will. But morphology can't use a sub-pixel
    footprint — it rounds to whole pixels and clamps at one — and the stars
    themselves are what decimation destroys first, so on a decimated proxy the
    preview's reduction lands somewhere near, but not on, the export's.

    **This used to claim a direction, and the direction was wrong.** The rule was
    "``size / proxy_scale < 1`` ⇒ the preview *over*-reduces", reasoned from where
    the footprint clamps. Measured instead — preview ÷ export star flux removed,
    three synthetic Seestar fields (600 stars, 1.27 px sigma) × proxy steps 2–5 ×
    ``size`` 1–4 — the ratio spans **0.63 to 1.58** and only ``size`` 1 (0.20–0.50
    proxy px) over-reduces in every fixture. At the *default* ``size`` 2 it ranged
    0.81–1.06 with no consistent sign, and at ``size`` 3–4 the preview
    consistently under-reduced by 5–37 % — the exact opposite of what the caption
    told the user, on the values Auto and the presets actually use. No threshold
    in ``size / proxy_scale`` separates the two directions (0.5 proxy px
    over-reduces at ``size`` 1 and under-reduces at ``size`` 2), because the
    footprint rounding and the star mask move together.

    So the honest statement is the one every measurement supports: **on a
    decimated proxy the number is not faithful in either direction** — every
    decimated case measured at least 5 % off, most far more. The editor says that
    and asks the user to judge the strength on the export, instead of pointing
    them confidently the wrong way. On the export (``proxy_scale == 1``), and with
    the op off (``size <= 0``), there is nothing to caption. Advisory only: there
    is no clean pixel-level fix, since blending the darkening by the fractional
    radius over-corrects into heavy under-reduction (~0.5–0.73×) — erosion is
    non-linear. The sibling ``stars.boost_nebula`` shares the same ``star_mask``
    footprint mechanism.
    """
    if not np.isfinite(size) or not np.isfinite(proxy_scale):
        return False
    return proxy_scale > 1.0 and size > 0.0


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
