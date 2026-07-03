"""
Streaming stack accumulators.

Two accumulator types matter for our pipeline:

  * ``WeightedSumAccumulator`` — keeps ``sum`` and ``weight`` per pixel. Final
    image = ``sum / weight``. Used for the basic stack and for pass 2 of
    sigma-clipping.

  * ``WelfordAccumulator`` — adds a running variance estimate (Welford's
    algorithm) so we can compute per-pixel mean and standard deviation in a
    single streaming pass. Used for **pass 1** of sigma-clipped stacking,
    where pass 2 then re-streams the frames clipping pixels that fall outside
    ``mean ± k·σ``.

Both are designed to handle the **coverage map** correctly — pixels with zero
contributions come out as NaN, not as 0 / 0. That's the property that makes
mosaics and partial-overlap stacks work without bright seams: dividing the
sum by an actual per-pixel weight keeps brightness consistent everywhere.

Memory
------
For typical Seestar canvases (~1920×1080 RGB) each float32 accumulator is
about 25 MB — a couple hundred MB for everything. Both classes are simple
in-RAM accumulators; oversized canvases are refused up-front by the memory
guard in ``stack.stacker`` (there is no out-of-core variant).
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class WeightedSumAccumulator:
    """``sum / weight`` streaming accumulator with NaN-safe reductions."""

    def __init__(self, shape: tuple[int, ...], dtype: np.dtype | type = np.float32) -> None:
        self.shape = shape
        self._sum = np.zeros(shape, dtype=dtype)
        self._weight = np.zeros(shape, dtype=dtype)

    def add(
        self,
        image: np.ndarray,
        mask: np.ndarray | None = None,
        weight: float = 1.0,
    ) -> None:
        """
        Add one frame.

        Parameters
        ----------
        image
            Same shape as the accumulator. NaNs are treated as missing.
        mask
            Optional bool array (same shape, or broadcastable). False entries
            are skipped *in addition to* NaN entries.
        weight
            Per-frame scalar weight (1.0 = standard mean). Higher weights
            give the frame more influence in the final ``sum/weight``
            average. Used by quality-weighted stacking to down-weight
            soft / cloud-affected subs.
        """
        if image.shape != self.shape:
            raise ValueError(f"image shape {image.shape} != accumulator {self.shape}")
        valid = np.isfinite(image)
        if mask is not None:
            valid &= np.broadcast_to(mask, image.shape).astype(bool, copy=False)
        contribution = np.where(valid, image, 0.0).astype(self._sum.dtype, copy=False)
        if weight != 1.0:
            contribution = contribution * np.float32(weight)
        self._sum += contribution
        valid_weighted = valid.astype(self._weight.dtype, copy=False)
        if weight != 1.0:
            valid_weighted = valid_weighted * np.float32(weight)
        self._weight += valid_weighted

    def add_window(
        self,
        window_image: np.ndarray,
        y0: int,
        x0: int,
        mask: np.ndarray | None = None,
        weight: float = 1.0,
    ) -> None:
        """
        Add a frame that only covers the sub-rectangle ``[y0:y0+wh, x0:x0+ww]``.

        Used by the windowed reproject path so a mosaic-panel frame only
        touches its own region of the canvas instead of the whole thing.
        ``window_image`` is (wh, ww, 3); NaNs are treated as missing.
        """
        wh, ww = window_image.shape[:2]
        valid = np.isfinite(window_image)
        if mask is not None:
            valid &= np.broadcast_to(mask, window_image.shape).astype(bool, copy=False)
        contribution = np.where(valid, window_image, 0.0).astype(self._sum.dtype, copy=False)
        valid_w = valid.astype(self._weight.dtype, copy=False)
        if weight != 1.0:
            contribution = contribution * np.float32(weight)
            valid_w = valid_w * np.float32(weight)
        # In-place add into the canvas sub-views.
        self._sum[y0:y0 + wh, x0:x0 + ww] += contribution
        self._weight[y0:y0 + wh, x0:x0 + ww] += valid_w

    def result(self) -> np.ndarray:
        """Return ``sum / weight`` with empty pixels = NaN."""
        out = np.full(self.shape, np.nan, dtype=self._sum.dtype)
        nz = self._weight > 0
        out[nz] = self._sum[nz] / self._weight[nz]
        return out

    @property
    def coverage(self) -> np.ndarray:
        """Per-pixel weight (number of contributing frames). Read-only view."""
        return self._weight

    @property
    def sum(self) -> np.ndarray:
        return self._sum


class MinMaxRejectAccumulator:
    """Single-pass top/bottom-*k* (extremes) rejection accumulator, NaN-aware.

    For each pixel it keeps a running ``sum`` and ``count`` plus the *k smallest*
    and *k largest* valid contributions, then reduces to the mean of the middle
    values by dropping the k lowest and k highest:

        result = (sum − Σ(k smallest) − Σ(k largest)) / (count − 2k)   when count ≥ 2k+1

    With the default ``reject_count=1`` this is exactly the classic min/max reject
    (drop one min, one max). Raising *k* handles **multiple** outliers crossing the
    same pixel across a session — e.g. three satellite/plane trails at ``k=3`` —
    which a single-extreme drop leaves behind.

    Like κ-σ's alternative, this is an **order-statistic** reject: it removes a lone
    satellite/plane trail (a per-pixel max) or cold/dead sample (a min) *even in a
    tiny stack* where κ-σ mathematically can't (a lone outlier's deviation stays
    below κ for n < 11). It's tie-safe (a saturated star core shared by several
    frames loses only k contributions, because each extreme *value* is subtracted
    once regardless of how many frames hit it) and memory-bounded (``2 + 2k`` canvas
    planes, one pass — no need to hold every frame).

    Coverage degrades gracefully:

    * ``count ≥ 2k+1`` — the two k-sets are disjoint with a middle left: full k-trim.
    * ``3 ≤ count < 2k+1`` — can't spare 2k, so degrade to the proven single min/max
      drop (``(sum − min − max) / (count − 2)``).
    * ``1 ≤ count < 3`` — can't spare two: plain mean of whatever covered the pixel.
    * ``count == 0`` — stays NaN.

    Being an order statistic, it ignores per-frame quality weights (like a median
    would) — the ``weight`` argument is accepted for a uniform consumer signature
    but not applied.
    """

    def __init__(self, shape: tuple[int, ...], dtype: np.dtype | type = np.float32,
                 reject_count: int = 1) -> None:
        self.shape = shape
        self._k = max(1, int(reject_count))
        self._sum = np.zeros(shape, dtype=dtype)
        self._count = np.zeros(shape, dtype=np.uint32)
        # k sorted planes per side; seed with the ±inf identities so an as-yet
        # uncovered slot never wins the extremes. ``_mins`` ascending (``_mins[0]``
        # is the true min), ``_maxs`` descending (``_maxs[0]`` is the true max).
        self._mins = np.full((self._k, *shape), np.inf, dtype=dtype)
        self._maxs = np.full((self._k, *shape), -np.inf, dtype=dtype)

    def add(self, image: np.ndarray, mask: np.ndarray | None = None, weight: float = 1.0) -> None:
        if image.shape != self.shape:
            raise ValueError(f"image shape {image.shape} != accumulator {self.shape}")
        self._add_into(image, slice(None), slice(None), mask)

    def add_window(
        self,
        window_image: np.ndarray,
        y0: int,
        x0: int,
        mask: np.ndarray | None = None,
        weight: float = 1.0,
    ) -> None:
        """Extremes update for a frame covering only ``[y0:y0+wh, x0:x0+ww]``."""
        wh, ww = window_image.shape[:2]
        self._add_into(window_image, slice(y0, y0 + wh), slice(x0, x0 + ww), mask)

    def _add_into(self, image: np.ndarray, ys: slice, xs: slice,
                  mask: np.ndarray | None) -> None:
        valid = np.isfinite(image)
        if mask is not None:
            valid &= np.broadcast_to(mask, image.shape).astype(bool, copy=False)
        if not valid.any():
            return
        # Contributions of invalid pixels are neutralised: 0 for the sum, and the
        # ±inf identities so they never displace a real value in the k-sets.
        vals = np.where(valid, image, 0.0).astype(self._sum.dtype, copy=False)
        self._sum[ys, xs] += vals
        self._count[ys, xs] += valid.astype(np.uint32, copy=False)
        # Insertion into the k smallest (invalid → +inf never displaces).
        cand = np.where(valid, image, np.inf).astype(self._mins.dtype, copy=False)
        mins = self._mins[:, ys, xs]
        for j in range(self._k):
            slot = np.minimum(cand, mins[j])
            cand = np.maximum(cand, mins[j])  # the larger bubbles down
            mins[j] = slot
        self._mins[:, ys, xs] = mins
        # Insertion into the k largest (invalid → -inf never displaces).
        cand = np.where(valid, image, -np.inf).astype(self._maxs.dtype, copy=False)
        maxs = self._maxs[:, ys, xs]
        for j in range(self._k):
            slot = np.maximum(cand, maxs[j])
            cand = np.minimum(cand, maxs[j])  # the smaller bubbles down
            maxs[j] = slot
        self._maxs[:, ys, xs] = maxs

    def result(self) -> np.ndarray:
        out = np.full(self.shape, np.nan, dtype=self._sum.dtype)
        cnt = self._count
        k = self._k
        # count ≥ 2k+1: the two k-sets are disjoint with a middle — full k-trim.
        full = cnt >= (2 * k + 1)
        if full.any():
            # Index each side's k-plane sum *before* combining, so the ±inf
            # identities at still-uncovered pixels never form an inf−inf NaN.
            drop = self._mins.sum(axis=0)[full] + self._maxs.sum(axis=0)[full]
            denom = cnt[full].astype(self._sum.dtype) - 2.0 * k
            out[full] = (self._sum[full] - drop) / denom
        # 3 ≤ count < 2k+1: can't spare 2k — degrade to a single min/max drop.
        # (For k=1, 2k+1 == 3 so this band is empty and behaviour is unchanged.)
        single = (cnt >= 3) & (cnt < (2 * k + 1))
        if single.any():
            denom = cnt[single].astype(self._sum.dtype) - 2.0
            out[single] = (self._sum[single] - self._mins[0][single]
                           - self._maxs[0][single]) / denom
        # 1–2 samples: can't spare two — fall back to the plain mean.
        lt3 = (cnt >= 1) & (cnt < 3)
        if lt3.any():
            out[lt3] = self._sum[lt3] / cnt[lt3].astype(self._sum.dtype)
        return out

    @property
    def coverage(self) -> np.ndarray:
        """Per-pixel contributing-frame count (float, matching the other
        accumulators' coverage semantics)."""
        return self._count.astype(self._sum.dtype)


class WelfordAccumulator:
    """
    Streaming mean + variance via Welford's online algorithm. NaN-aware.

    For each pixel we keep three running quantities: count ``n``, mean ``m``,
    and ``M2`` (sum of squared deviations). Update for value x:

        n   ← n + 1
        d   ← x - m
        m   ← m + d / n
        M2  ← M2 + d · (x - m_new)

    Population variance is ``M2 / n``. We use that (not the sample variance)
    because it converges to the true variance as ``n`` grows and works fine
    when ``n == 1``.
    """

    def __init__(self, shape: tuple[int, ...], dtype: np.dtype | type = np.float32) -> None:
        self.shape = shape
        self._n = np.zeros(shape, dtype=np.uint32)
        self._mean = np.zeros(shape, dtype=dtype)
        self._m2 = np.zeros(shape, dtype=dtype)

    def add(self, image: np.ndarray) -> None:
        if image.shape != self.shape:
            raise ValueError(f"image shape {image.shape} != accumulator {self.shape}")
        valid = np.isfinite(image)
        if not valid.any():
            return
        x = image.astype(self._mean.dtype, copy=False)
        # Indices we will update.
        n_old = self._n.astype(self._mean.dtype, copy=False)
        n_new = n_old + valid
        # Avoid division by zero for the not-valid pixels by using n_new where
        # valid, 1 elsewhere (and we won't update mean/m2 there).
        n_safe = np.where(valid, n_new, 1.0)
        delta = np.where(valid, x - self._mean, 0.0)
        new_mean = self._mean + delta / n_safe
        delta2 = np.where(valid, x - new_mean, 0.0)
        self._m2 = self._m2 + delta * delta2
        self._mean = new_mean
        # Cast n_new back to uint32 for storage.
        self._n = n_new.astype(np.uint32, copy=False)

    def add_window(self, window_image: np.ndarray, y0: int, x0: int) -> None:
        """
        Welford update for a frame covering only ``[y0:y0+wh, x0:x0+ww]``.

        Same online mean/variance maths as ``add``, applied to canvas
        sub-views so a windowed frame doesn't have to be embedded in a
        full-canvas array first.
        """
        wh, ww = window_image.shape[:2]
        valid = np.isfinite(window_image)
        if not valid.any():
            return
        x = window_image.astype(self._mean.dtype, copy=False)
        sub_n = self._n[y0:y0 + wh, x0:x0 + ww]
        sub_mean = self._mean[y0:y0 + wh, x0:x0 + ww]
        sub_m2 = self._m2[y0:y0 + wh, x0:x0 + ww]

        n_old = sub_n.astype(self._mean.dtype, copy=False)
        n_new = n_old + valid
        n_safe = np.where(valid, n_new, 1.0)
        delta = np.where(valid, x - sub_mean, 0.0)
        new_mean = sub_mean + delta / n_safe
        delta2 = np.where(valid, x - new_mean, 0.0)
        # In-place writes back to the canvas sub-views.
        sub_m2 += delta * delta2
        sub_mean[...] = new_mean
        sub_n[...] = n_new.astype(np.uint32, copy=False)

    def mean(self) -> np.ndarray:
        out = np.full(self.shape, np.nan, dtype=self._mean.dtype)
        nz = self._n > 0
        out[nz] = self._mean[nz]
        return out

    def variance(self) -> np.ndarray:
        # Unbiased sample variance (divide by n-1), NaN for n<2. NaN is the
        # signal the sigma-clip pass uses to *not* clip single-coverage pixels:
        # with population variance, n=1 gives std=0 and the clip tolerance
        # collapses to 0, so float-rounding noise spuriously rejects the only
        # frame covering a mosaic-edge pixel. The stacker widens a NaN std to an
        # infinite tolerance (keep-all), which is the correct behaviour here.
        out = np.full(self.shape, np.nan, dtype=self._m2.dtype)
        valid = self._n >= 2
        nf = self._n[valid].astype(self._m2.dtype)
        out[valid] = self._m2[valid] / (nf - 1.0)
        return out

    def std(self) -> np.ndarray:
        var = self.variance()
        with np.errstate(invalid="ignore"):
            return np.sqrt(np.where(np.isfinite(var) & (var >= 0), var, np.nan))

    @property
    def count(self) -> np.ndarray:
        return self._n
