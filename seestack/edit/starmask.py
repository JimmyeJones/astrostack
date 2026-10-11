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

**Window safety: the two normalising references are properties of the whole
picture, so they go through ``EditContext.fit``** (the channel the stretch, the
tone curve, the colour solve and "Neutralize background" already use). The mask
is ``tophat / hi`` floored and feathered, then divided by its own post-blur
peak — and both ``hi`` (the 99.9th percentile of the top-hat) and that peak are
read off the whole array. Handed one 512 px window — which is exactly what the
editor's "check it at full size" loupe does, and star reduction is one of the
four advisories that control exists to answer — they describe *the window*, so
a star-poor patch of a mosaic normalises its own noise up to a full-strength
mask. Measured on a 1800×2400 canvas with a 512 px window (see
``tests/test_edit_starmask.py``): ``hi`` is 0.0080 in a star-poor outskirt
against the canvas's 0.219 — **27× low** — while the whole *proxy*'s is 0.213,
**2.7 %** from the canvas's, because a decimation that shrinks the footprint by
the same factor keeps the top-hat at the same physical scale. So the whole-image
render's numbers are the ones a window wants, and freezing them takes
``stars.reduce``'s window error from 5.81 % of the picture's own scale to
**0.03 %** and ``stars.boost_nebula``'s from 16.26 % to **0.00 %**.

With no ``ctx`` — and on every whole-image render, preview and export alike,
which supply no ``frozen_fits`` — every reference is measured exactly as before,
so no saved picture moves by a bit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
        Edit context; ``proxy_scale`` rescales the footprint for the preview, and
        ``fit`` carries the two whole-image references onto a window render.
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
    #
    # Both references are whole-picture properties, so they go through ``fit``
    # (module docstring). They are keyed by the *full-resolution* geometry that
    # decides them — ``size_px`` for the top-hat's footprint, and ``grow`` as well
    # for the post-blur peak — rather than by the derived pixel footprint, which
    # differs between a decimated whole-image render and the 1:1 window that
    # borrows from it. Keying it that way also means two masks of different sizes
    # built inside one op can never share a reference that only describes one of
    # them.
    hi = _fit(ctx, f"star_tophat_hi:{size_px:g}",
              lambda: float(np.percentile(tophat[cover], 99.9)))
    if not hi or hi <= 0:
        return np.zeros(lum.shape, dtype=np.float32)
    mask = np.clip(tophat / hi, 0.0, 1.0)
    floor = 0.15
    mask = np.clip((mask - floor) / (1.0 - floor), 0.0, 1.0)

    # Feather edges and grow to catch halos.
    mask = gaussian_filter(mask, sigma=max(0.6, s * (0.5 + grow)))
    mx = _fit(ctx, f"star_mask_peak:{size_px:g}:{grow:g}", lambda: float(mask.max()))
    if mx and mx > 0:
        # Clipped because a frozen peak is the *picture's*, and a window holding a
        # brighter star than the one the whole render peaked on would otherwise
        # come back above 1.
        mask = np.clip(mask / mx, 0.0, 1.0)
    mask[~cover] = 0.0
    return mask.astype(np.float32, copy=False)


def _fit(ctx: EditContext | None, name: str, compute: Callable[[], Any]) -> Any:
    """``ctx.fit(name, compute)``, or just ``compute()`` for a context-free call.

    The engine's own callers (and the tests) pass ``ctx=None``; the editor always
    has one. One helper rather than two branches at each site, so the two
    references cannot drift into being carried differently.
    """
    return compute() if ctx is None else ctx.fit(name, compute)
