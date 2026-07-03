"""Largest well-covered rectangle for one-click mosaic-border trimming.

A Seestar mosaic's union canvas has ragged, low-coverage edges — corners touched
by a single frame, NaN gaps where no frame reached — that look messy and are
noisier than the well-covered interior. This module finds the largest
axis-aligned rectangle whose pixels are all *well covered* (per-pixel frame
coverage at or above a fraction of the peak), so the editor can offer a single
"Trim to well-covered area" button that sets a ``geometry.crop`` op to that
rectangle. It's a pure geometry helper (no I/O); the coverage map is loaded and
downsampled by the caller.
"""

from __future__ import annotations

import numpy as np

# Below this coverage fraction of the peak a pixel is treated as fringe/uncovered.
DEFAULT_MIN_FRAC = 0.5
# If the best rectangle already spans essentially the whole frame there's nothing
# worth trimming, so we return None (no crop) rather than a no-op crop.
_FULL_AREA_FRAC = 0.985


def _largest_hist_rect(heights: np.ndarray, base_row: int):
    """Largest rectangle in a 1-D histogram, as ``(r0, c0, r1, c1, area)``.

    ``heights[c]`` is how many consecutive covered rows end at ``base_row`` in
    column ``c`` (the bar rising upward from the base). The returned rectangle is
    half-open in both axes (rows ``[r0, r1)``, cols ``[c0, c1)``). Classic
    monotone-stack sweep, O(w).
    """
    stack: list[int] = []  # indices of strictly-increasing bar heights
    best_area = 0
    best = None
    n = len(heights)
    for i in range(n + 1):
        cur = int(heights[i]) if i < n else 0
        while stack and int(heights[stack[-1]]) >= cur:
            top = stack.pop()
            height = int(heights[top])
            left = stack[-1] + 1 if stack else 0
            width = i - left
            area = height * width
            if height > 0 and area > best_area:
                best_area = area
                best = (base_row - height + 1, left, base_row + 1, i)
        stack.append(i)
    if best is None:
        return None
    return (*best, best_area)


def _max_rectangle(mask: np.ndarray):
    """Largest all-True axis-aligned rectangle in a 2-D boolean mask, as
    ``(r0, c0, r1, c1)`` half-open, or ``None`` when the mask is empty."""
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int64)
    best_area = 0
    best = None
    for r in range(h):
        row = mask[r]
        heights = np.where(row, heights + 1, 0)
        res = _largest_hist_rect(heights, r)
        if res is not None and res[4] > best_area:
            best_area = res[4]
            best = res[:4]
    return best


def largest_covered_rect(coverage: np.ndarray,
                         min_frac: float = DEFAULT_MIN_FRAC):
    """Fractional ``(x0, y0, x1, y1)`` bounds (each in 0..1) of the largest
    axis-aligned rectangle whose pixels are all well covered, or ``None`` when
    there's nothing worth trimming.

    A pixel is "well covered" when its coverage is finite and at least
    ``min_frac`` of the peak coverage; NaN (no coverage) always counts as
    uncovered. ``None`` is returned when the coverage is uniform (a single-field
    stack — every pixel passes, so the rectangle is the whole frame), when the
    best rectangle already spans essentially the whole frame (nothing ragged to
    trim), or when the result would be degenerate — so the caller can treat
    ``None`` as "leave the image alone".
    """
    cov = np.asarray(coverage, dtype=np.float32)
    if cov.ndim != 2 or cov.size == 0:
        return None
    finite = cov[np.isfinite(cov)]
    if finite.size == 0:
        return None
    peak = float(finite.max())
    if peak <= 0:
        return None
    frac = min(0.95, max(0.05, float(min_frac)))
    mask = np.isfinite(cov) & (cov >= frac * peak)
    if mask.all() or not mask.any():
        return None  # uniform (single-field) or nothing covered → no trim
    rect = _max_rectangle(mask)
    if rect is None:
        return None
    r0, c0, r1, c1 = rect
    h, w = mask.shape
    if (r1 - r0) < 2 or (c1 - c0) < 2:
        return None  # degenerate
    if (r1 - r0) * (c1 - c0) >= _FULL_AREA_FRAC * h * w:
        return None  # already spans the whole frame — nothing worth trimming
    return (c0 / w, r0 / h, c1 / w, r1 / h)
