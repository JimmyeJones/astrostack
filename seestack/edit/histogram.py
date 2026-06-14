"""NaN-aware per-channel histogram of a display-space (or linear) RGB image."""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import as_rgb


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
