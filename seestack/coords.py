"""Sky-coordinate helpers shared across the engine.

Kept dependency-free (numpy only, no intra-package imports) so both ``io`` and
``stack`` can use it without creating a layer cycle. Its reason to exist is the
RA 0°/360° wrap: the same unwrap heuristic was independently re-derived — and the
same wrap bug independently reintroduced — in three separate places
(``stack/mosaic.py``, ``stack/reference.py``, ``io/library.py``), so it lives here
once with one set of boundary tests behind it.
"""

from __future__ import annotations

import numpy as np

__all__ = ["unwrap_ra_deg", "circular_median_ra_deg"]


def unwrap_ra_deg(ras) -> np.ndarray:
    """Unwrap RA values (degrees) into a continuous range across the 0°/360° seam.

    A target imaged near RA=0h has frames straddling the boundary (some at
    ~359.9°, some at ~0.1°). A plain median/mean/subtraction of those values lands
    ~180° away — the opposite side of the sky — flinging the apparent centre off,
    scoring good frames as gross plate-solve outliers, and reporting a bogus ~360°
    span. When the apparent spread exceeds 180° the set is assumed to straddle the
    seam, so every value above 180° is shifted down by 360° to form one continuous
    run (values may go slightly negative). With no wrap every value is returned
    unchanged, so a normal target behaves exactly as before.

    Returns a ``float64`` ndarray in the (possibly shifted) continuous space; fold
    back to [0, 360) with ``% 360.0`` when you need a canonical RA. An empty input
    is returned as an empty array.
    """
    arr = np.asarray(ras, dtype=np.float64)
    if arr.size and float(arr.max() - arr.min()) > 180.0:
        arr = np.where(arr > 180.0, arr - 360.0, arr)
    return arr


def circular_median_ra_deg(ras) -> float:
    """Median RA (degrees, folded to [0, 360)) correct across the 0°/360° seam.

    Unwraps with :func:`unwrap_ra_deg`, medians in the continuous space, then folds
    back to [0, 360). Assumes ``ras`` is non-empty.
    """
    med = float(np.median(unwrap_ra_deg(ras))) % 360.0
    # A tiny-negative median (e.g. a target sitting exactly on the seam) folds to
    # exactly 360.0 under the float ``%`` — snap that back to 0.0 so the result is
    # always in [0, 360).
    return 0.0 if med >= 360.0 else med
