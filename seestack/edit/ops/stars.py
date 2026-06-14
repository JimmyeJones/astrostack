"""Classic star reduction (no ML).

Grey-scale morphological erosion shrinks small bright features (stars) far more
than extended structure (nebulosity/galaxy), so blending in the erosion only where
it darkens reduces stars while barely touching the rest. A star mask from the
existing detector further protects non-star regions when available.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, EditParam, OpSpec, as_rgb, finite_mask, register


def _reduce(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import grey_erosion

    amount = float(params.get("amount", 0.5))
    size = max(1, int(params.get("size", 2)))
    out = as_rgb(rgb).copy()
    cover = finite_mask(out)
    if not cover.any() or amount <= 0:
        return out

    filled = out.copy()
    for c in range(3):
        chan = filled[..., c]
        chan[~cover] = float(np.nanmedian(chan)) if np.isfinite(chan).any() else 0.0

    footprint = np.ones((2 * size + 1, 2 * size + 1), dtype=bool)
    for c in range(3):
        eroded = grey_erosion(filled[..., c], footprint=footprint)
        # Only pull pixels down where erosion darkens them (star cores/halos).
        reduced = filled[..., c] - amount * np.maximum(0.0, filled[..., c] - eroded)
        out[..., c][cover] = reduced[cover]
    return out


register(OpSpec(
    id="stars.reduce", label="Star reduction", group="stars_geometry", stage="nonlinear",
    apply=_reduce, proxy_safe=True,
    help="Shrink stars morphologically without touching nebulosity. No AI model.",
    params=[
        EditParam("amount", "Amount", "float", default=0.5, min=0.0, max=1.0, step=0.05),
        EditParam("size", "Star size (px)", "int", default=2, min=1, max=8, step=1),
    ],
))
