"""Star mask for mask-gated local edits.

A *star mask* is a soft ``[0, 1]`` map that is ~1 on stars and ~0 on background
and extended structure (nebulosity, galaxies). It lets editor ops act on stars
and background separately — e.g. reduce stars without eating the nebula, or lift
faint background without bloating the stars.

Method: grey-scale **morphological opening** removes structures smaller than the
footprint while leaving larger ones intact, so ``luminance − opening`` (a white
top-hat) isolates small bright features — stars. We normalise that robustly,
feather the edges, and grow it slightly to cover star halos.

Proxy safety: the footprint is a *physical* star size in full-resolution pixels.
On the decimated live-preview proxy the same star spans fewer pixels, so we
divide the footprint by ``ctx.proxy_scale`` (= full_width / proxy_width). That
keeps the preview mask consistent with the full-res result.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, as_rgb, luminance


def star_mask(
    rgb: np.ndarray,
    *,
    size_px: float = 4.0,
    grow: float = 0.5,
    ctx: EditContext | None = None,
) -> np.ndarray:
    """Return a soft ``[0, 1]`` star mask, shape ``(H, W)`` float32.

    Parameters
    ----------
    size_px
        Approximate star radius in full-resolution pixels — the opening
        footprint. Larger captures bigger/bloated stars (and risks small
        nebula knots).
    grow
        Extra feathering/growth (0..1) to cover halos around bright stars.
    ctx
        Edit context; ``proxy_scale`` rescales the footprint for the preview.
    """
    from scipy.ndimage import gaussian_filter, grey_opening

    lum = luminance(as_rgb(rgb))
    cover = np.isfinite(lum)
    if not cover.any():
        return np.zeros(lum.shape, dtype=np.float32)

    fill = float(np.nanmedian(lum[cover]))
    flat = np.where(cover, lum, fill).astype(np.float32, copy=False)

    scale = max(1.0, ctx.proxy_scale) if ctx is not None else 1.0
    s = max(1, int(round(size_px / scale)))
    footprint = np.ones((2 * s + 1, 2 * s + 1), dtype=bool)

    opened = grey_opening(flat, footprint=footprint)
    tophat = np.maximum(0.0, flat - opened)  # bright compact features = stars

    # Normalise against a robust *bright* reference (99.9th pct ≈ star cores,
    # but rejects a lone hot pixel). Then floor out the low-level residual that
    # extended structure (nebula/galaxy) leaves behind, so only true stars keep
    # significant mask weight.
    hi = float(np.percentile(tophat[cover], 99.9))
    if hi <= 0:
        return np.zeros(lum.shape, dtype=np.float32)
    mask = np.clip(tophat / hi, 0.0, 1.0)
    floor = 0.15
    mask = np.clip((mask - floor) / (1.0 - floor), 0.0, 1.0)

    # Feather edges and grow to catch halos.
    mask = gaussian_filter(mask, sigma=max(0.6, s * (0.5 + grow)))
    mx = float(mask.max())
    if mx > 0:
        mask = np.clip(mask / mx, 0.0, 1.0)
    mask[~cover] = 0.0
    return mask.astype(np.float32, copy=False)
