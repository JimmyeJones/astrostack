"""
Robust low-order sky-surface fitting, shared by the background passes.

Both background passes need the same primitive: *"what smooth, frame-scale shape
does the sky have here?"* — the final-stack gradient pass uses it to detrend the
luminance before detecting objects (and to match each channel's own gradient), and
the per-frame flatten uses it for the same detrend so its object mask isn't
starved by light pollution.

Two deliberate choices, both measured (see ``final_gradient``'s history):

- **Degree 2.** Low enough that the surface cannot bend into a localised
  galaxy/nebula, high enough to follow the smooth shape light pollution has.
- **Fit per-tile medians, not raw pixels.** A median is unbiased however many of
  a tile's pixels the object mask removed, whereas least-squares over raw pixels
  with outlier clipping is not: clipping bites harder where the mask is denser,
  which bends a spurious few-ADU surface out of a frame that has no gradient at
  all. It is also far cheaper — ~600 samples instead of millions — which is what
  makes it affordable on the per-frame hot path and on every preview render.
"""

from __future__ import annotations

import numpy as np

# Degree of the robust sky polynomial (see the module docstring).
POLY_DEG = 2
# Grid resolution for the per-tile sky samples the surface is fitted to.
POLY_TILES = 24
# A tile needs this fraction of its pixels to be unmasked sky before its median is
# trusted as a sample; otherwise the tile is dropped from the fit.
POLY_TILE_MIN_FRAC = 0.25


def poly_design(ys: np.ndarray, xs: np.ndarray, deg: int) -> np.ndarray:
    """Design matrix for a 2D polynomial of degree ``deg`` in normalised coords."""
    terms = [np.ones_like(xs)]
    for d in range(1, deg + 1):
        for k in range(d + 1):
            terms.append((xs ** (d - k)) * (ys ** k))
    return np.stack(terms, axis=-1)


def eval_poly_surface(coef: np.ndarray, h: int, w: int, deg: int) -> np.ndarray:
    """Evaluate a :func:`poly_design` fit over a whole ``(h, w)`` grid.

    Same term order and normalised coordinates as :func:`poly_design`, but built
    by broadcasting two 1-D coordinate vectors in float32 instead of
    materialising the full design matrix. That matters on the per-frame hot path:
    the design-matrix form allocated ``n_terms`` float64 planes (~96 MB for a
    1080×1920 sub) and cost ~245 ms per call, which is most of what the mask used
    to spend; this is ~20 ms and a couple of float32 temporaries.
    """
    y = (np.arange(h, dtype=np.float32) / max(h - 1, 1) - 0.5).reshape(h, 1)
    x = (np.arange(w, dtype=np.float32) / max(w - 1, 1) - 0.5).reshape(1, w)
    x_pow = [np.ones((1, 1), dtype=np.float32)]
    y_pow = [np.ones((1, 1), dtype=np.float32)]
    for _ in range(deg):
        x_pow.append(x_pow[-1] * x)
        y_pow.append(y_pow[-1] * y)

    out = np.full((h, w), np.float32(coef[0]), dtype=np.float32)
    i = 1
    for d in range(1, deg + 1):
        for k in range(d + 1):
            out += np.float32(coef[i]) * (x_pow[d - k] * y_pow[k])
            i += 1
    return out


def tile_medians(
    plane: np.ndarray, include: np.ndarray, tiles: int = POLY_TILES,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Coarse grid of robust sky samples: ``(ys, xs, values)`` in normalised
    ``[-0.5, 0.5]`` coordinates, one entry per tile that held enough sky.
    """
    h, w = plane.shape[:2]
    ny = max(2, min(tiles, h))
    nx = max(2, min(tiles, w))
    y_edges = np.linspace(0, h, ny + 1).astype(int)
    x_edges = np.linspace(0, w, nx + 1).astype(int)
    ys: list[float] = []
    xs: list[float] = []
    vals: list[float] = []
    for iy in range(ny):
        y0, y1 = y_edges[iy], y_edges[iy + 1]
        if y1 <= y0:
            continue
        for ix in range(nx):
            x0, x1 = x_edges[ix], x_edges[ix + 1]
            if x1 <= x0:
                continue
            cell = plane[y0:y1, x0:x1]
            ok = include[y0:y1, x0:x1] & np.isfinite(cell)
            n_ok = int(ok.sum())
            if n_ok < max(8, int(POLY_TILE_MIN_FRAC * cell.size)):
                continue
            ys.append((y0 + y1) * 0.5 / max(h - 1, 1) - 0.5)
            xs.append((x0 + x1) * 0.5 / max(w - 1, 1) - 0.5)
            vals.append(float(np.median(cell[ok])))
    return (np.asarray(ys, dtype=np.float64),
            np.asarray(xs, dtype=np.float64),
            np.asarray(vals, dtype=np.float64))


def fit_sky_poly(
    plane: np.ndarray,
    include: np.ndarray | None = None,
    *,
    deg: int = POLY_DEG,
    iters: int = 3,
) -> np.ndarray | None:
    """
    Robust low-order polynomial surface through the *sky* of a 2D plane.

    ``include`` (optional) restricts the samples to those pixels (the sky mask).
    The solve runs over per-tile medians (see :func:`tile_medians`), then rejects
    tiles whose residual is a high outlier — nebulosity the mask missed — and
    re-solves, so a faint object cannot drag the surface up around it.

    Returns ``None`` when there is too little sky to fit, so callers can skip
    the pass rather than subtract a garbage surface.
    """
    h, w = plane.shape[:2]
    if include is None:
        include = np.ones((h, w), dtype=bool)
    ys, xs, vals = tile_medians(plane, include)
    n_terms = (deg + 1) * (deg + 2) // 2
    if vals.size < n_terms * 4:
        return None
    design = poly_design(ys, xs, deg)
    keep = np.ones(vals.shape, dtype=bool)
    coef = None
    for _ in range(iters):
        if int(keep.sum()) < n_terms * 4:
            break
        coef, *_ = np.linalg.lstsq(design[keep], vals[keep], rcond=None)
        resid = vals - design @ coef
        kept = resid[keep]
        sigma = 1.4826 * float(np.median(np.abs(kept - np.median(kept))))
        if not np.isfinite(sigma) or sigma <= 0.0:
            break
        keep = (resid < 2.5 * sigma) & (resid > -3.0 * sigma)
    if coef is None:
        return None
    return eval_poly_surface(coef, h, w, deg)
