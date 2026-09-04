"""
Sigma-clipped statistics that stay quiet about this engine's no-coverage NaNs.

``NaN = no coverage`` is a load-bearing convention here (mosaic edges, uncovered
sky, masked pixels), so nearly every array a background/QC pass measures carries
NaNs by design. ``astropy.stats.sigma_clipped_stats`` handles them correctly —
it clips them out before the statistics — but it *warns* every time it does
("Input data contains invalid values (NaNs or infs), which were automatically
clipped"), and astropy routes that warning into the application log. A single
stack emits dozens of them, which is enough to bury a genuine NaN/inf problem in
the Logs page a beginner actually reads.

Passing the non-finite pixels as an explicit ``mask=`` says the same thing on
purpose and silently. The numbers are unchanged: the masked call returns
bit-identical ``(mean, median, std)`` to the unmasked one (pinned in
``tests/test_skystats.py``), because it is the same set of pixels either way.

The one case that needs care is an array with *no* finite pixel at all. Masking
everything makes astropy return ``np.ma.masked`` rather than NaN, and
``float(np.ma.masked)`` emits a warning of its own — trading one noisy warning
for another — so that case short-circuits to NaN of the input's own dtype, which
is exactly what the unmasked call used to return.
"""

from __future__ import annotations

import numpy as np


def sigma_clipped_stats_finite(data: np.ndarray, **kwargs):
    """``sigma_clipped_stats`` over the finite pixels only, without warning.

    Drop-in for ``sigma_clipped_stats(data, …)`` on any array that may carry
    no-coverage NaNs (or infs). Returns the same ``(mean, median, std)`` triple,
    in the same dtype, with ``NaN`` for all three when nothing finite is left to
    measure.
    """
    from astropy.stats import sigma_clipped_stats

    arr = np.asarray(data)
    finite = np.isfinite(arr)
    if finite.all():
        return sigma_clipped_stats(arr, **kwargs)
    if not finite.any():
        # Keep the caller's dtype: every consumer guards on `np.isfinite(...)`,
        # and an integer array can't hold NaN, so fall back to float64 there.
        nan = arr.dtype.type(np.nan) if arr.dtype.kind == "f" else np.float64(np.nan)
        return nan, nan, nan
    return sigma_clipped_stats(arr, mask=~finite, **kwargs)
