"""
Drizzle stacking path.

Drizzle (Fruchter & Hook, 2002 — the same algorithm HST uses) does two things
that bilinear reproject + weighted mean cannot:

  1. **Super-resolution.** Output pixels can be smaller than input pixels
     (``scale > 1``), so dithered frames with sub-pixel offsets contribute
     finer detail to the output than any single frame contains. With the
     Seestar's natural tracking jitter you get a real resolution lift.

  2. **Correct partial-pixel weighting.** Each input pixel "drops" onto the
     output as a square footprint scaled by ``pixfrac`` (e.g. 0.7 = 70% of
     the input pixel size). The intersection area between that drop and each
     output pixel becomes the weight. Sharper than bilinear (which always
     spreads to a 2×2 neighbourhood), at the cost of higher noise per pixel.

Trade-offs vs the standard weighted-sum path:

  - Drizzle is **CPU-only**. The GPU reproject path doesn't apply.
  - Drizzle cannot do per-pixel sigma clipping in a single pass — the
    accumulation is one-shot. Single-pass drizzle therefore keeps satellites,
    plane trails and cosmic rays that slipped past frame-level QC. The
    optional **two-pass rejection** (``StackOptions.drizzle_reject``) fixes
    this: pass 1 drizzles values *and* their squares to build a per-output-
    pixel mean/σ of the actual contributions, pass 2 re-drizzles with any
    contribution outside ``mean ± κ·σ`` given zero weight. Because both the
    tested value and the statistics are box-sampled raw pixels, PSF-gradient
    systematics cancel (σ at a star edge automatically widens with the
    dither-phase spread) — so star cores are not eaten, unlike naive
    clipping of raw pixels against an interpolated mean.
  - Drizzle is slower per frame than reproject + accumulate, especially with
    ``scale > 1`` (which expands the output canvas). Two-pass rejection
    roughly doubles that again.

Recommendation: use drizzle when you have **lots** of dithered frames
(typically 200+) AND want extra resolution. Otherwise the weighted-mean path
gives faster, equally clean results on Seestar data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Outlier rejection is only trusted where enough frames overlap: with fewer
# effective contributions the sample σ is meaningless. (Below ~11 frames a
# non-iterated κ=3 clip can't fire anyway — the largest possible z-score of a
# point against statistics that include it is (n−1)/√n.)
_MIN_REJECT_NEFF = 3.0


@dataclass
class DrizzleParams:
    """Parameters for one drizzle accumulator."""

    pixfrac: float = 0.8       # 0.5–1.0; smaller = sharper, noisier
    scale: float = 1.0         # output pixels per input pixel; 2.0 = super-res
    kernel: str = "square"     # 'square', 'gaussian', 'turbo', 'lanczos2', 'lanczos3'


class DrizzleStacker:
    """
    Three Drizzle instances (one per RGB channel) wrapped behind a common
    add/result API matching ``WeightedSumAccumulator``.

    Output canvas size is the *reference* shape multiplied by ``scale``.
    Output WCS is the reference WCS with adjusted scale. The constructor
    builds those for you.
    """

    def __init__(
        self,
        ref_wcs,
        ref_shape: tuple[int, int],
        params: DrizzleParams,
        *,
        compute_stats: bool = False,
    ) -> None:
        from drizzle.resample import Drizzle

        self.params = params
        self.ref_wcs = ref_wcs
        self.ref_shape = ref_shape
        self.out_shape, self.out_wcs = _compute_output_canvas(ref_wcs, ref_shape, params.scale)

        # ``disable_ctx``: the context bitmask records *which* input frames hit
        # each output pixel — we never read it, and it costs one full-canvas
        # int32 plane per 32 frames (re-copied via np.append every time a plane
        # is added). On a multi-thousand-frame Seestar stack that is tens of GB
        # and quadratic copying, so it must stay off.
        def _make_drizzlers():
            return [
                Drizzle(
                    kernel=params.kernel,
                    fillval=0.0,
                    out_shape=self.out_shape,
                    exptime=0.0,
                    disable_ctx=True,
                )
                for _ in range(3)
            ]

        self._drizzlers = _make_drizzlers()
        # Statistics mode (rejection pass 1): a parallel set of drizzlers fed
        # with value² under the *same* weights, so E[v²] − E[v]² gives the
        # per-output-pixel temporal variance of the contributions. (The
        # library's ``data2`` plane resamples with *squared* weights — meant
        # for propagating input variance maps — so it can't be reused here.)
        self._sq_drizzlers = _make_drizzlers() if compute_stats else None
        self._n_added = 0
        # Unweighted per-output-pixel *frame count* for the coverage_min/max
        # "N frames per pixel" diagnostics. ``coverage`` (out_wht) is Σ of
        # (quality weight × footprint overlap area), so it equals the frame
        # count only at unit weight *and* pixfrac=1/scale=1 — with quality
        # weighting on, or any pixfrac<1 / scale≠1, it is not an integer frame
        # count and understates it. The *support* of a frame's deposit is
        # independent of its scalar weight, so a strict increase in channel-0's
        # accumulated weight after a frame is added marks exactly the output
        # pixels that frame contributed to (a clip-rejected or out-of-bounds
        # pixel leaves the weight unchanged, so it correctly doesn't count).
        # Mirrors ``WeightedSumAccumulator.frame_coverage``. The statistics-only
        # accumulator never surfaces this (its output is discarded), so it skips
        # the per-frame copy.
        self._count: np.ndarray | None = (
            None if compute_stats else np.zeros(self.out_shape, dtype=np.uint32)
        )
        # Memory-free rejection tally for the two-pass reject path (mirrors the
        # κ-σ and min/max accumulators): while pass 2 zero-weights outlier
        # contributions we sum two scalars — the covered samples that would have
        # contributed (in-bounds & finite) and the subset the clip actually
        # dropped. Only accumulated when a ``clip`` is supplied to
        # :meth:`add_frame`; ``rejection_counts`` reports them so the stacker can
        # surface a data-driven "rejection clipped ~X% of samples" trust line for
        # drizzle too.
        self._n_contributed = 0
        self._n_rejected = 0

    @property
    def output_canvas_shape(self) -> tuple[int, int]:
        return self.out_shape

    def add_frame(
        self,
        rgb: np.ndarray,
        in_wcs,
        *,
        weight: float = 1.0,
        clip: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> None:
        """
        Add one debayered, optionally bg-flattened frame to the drizzle.

        ``rgb`` is (H, W, 3) at the input frame's resolution. ``in_wcs`` is
        the input frame's astropy WCS. ``weight`` scales this frame's
        contribution (quality weighting) — since the drizzle output is a
        weighted average, scaling the weight map yields the weighted mean.

        ``clip`` is an optional ``(mean, tol)`` pair from
        :meth:`clip_reference` (both ``(H_out, W_out, 3)``). Each input pixel
        is tested against the statistics of the output pixel nearest its
        centre: contributions with ``|value − mean| > tol`` get zero weight.
        NaN mean or infinite tol always keeps the pixel.
        """
        # Drizzle wants a "pixmap" — for each input pixel, the (x, y)
        # coordinate in the output. Compute once per frame, share across
        # channels (saves ~3× the WCS transform cost).
        pixmap = _build_pixmap(in_wcs, self.out_wcs, rgb.shape[0], rgb.shape[1])
        # Mask out-of-bounds pixels with a weight map of 0.
        h_out, w_out = self.out_shape
        in_bounds = (
            (pixmap[..., 0] >= 0) & (pixmap[..., 0] <= w_out - 1)
            & (pixmap[..., 1] >= 0) & (pixmap[..., 1] <= h_out - 1)
        )
        if clip is not None:
            mean, tol = clip
            # Nearest output pixel per input-pixel centre. Out-of-bounds
            # coordinates clamp harmlessly — their weight is already 0.
            xi = np.clip(np.rint(pixmap[..., 0]), 0, w_out - 1).astype(np.intp)
            yi = np.clip(np.rint(pixmap[..., 1]), 0, h_out - 1).astype(np.intp)
        # Snapshot channel-0's accumulated weight so a strict post-add increase
        # marks this frame's output footprint for the unweighted frame count.
        prev_wht0 = (
            self._drizzlers[0].out_wht.copy() if self._count is not None else None
        )
        for c in range(3):
            vals = rgb[..., c]
            finite = np.isfinite(vals)
            # NaN (no-data) input pixels must carry zero weight — replacing
            # them with 0.0 at full weight would dilute real signal.
            wmap = np.where(in_bounds & finite, float(weight), 0.0).astype(np.float32)
            if clip is not None:
                # NaN deviations (NaN input or uncovered mean) compare False —
                # i.e. keep — so only a *finite* excursion above tol rejects.
                rejected = np.abs(vals - mean[yi, xi, c]) > tol[yi, xi, c]
                wmap[rejected] = 0.0
                # Trust tally: count only samples that *would* have contributed
                # (in bounds & finite). ``rejected`` can be True for an
                # out-of-bounds pixel whose clamped mean happens to differ, but
                # its weight was already 0, so it never counts.
                contributing = in_bounds & finite
                self._n_contributed += int(contributing.sum())
                self._n_rejected += int(np.count_nonzero(contributing & rejected))
            ch = np.where(finite, vals, 0.0).astype(np.float32, copy=False)
            self._drizzlers[c].add_image(
                data=ch,
                exptime=1.0,
                pixmap=pixmap,
                weight_map=wmap,
                pixfrac=self.params.pixfrac,
                in_units="counts",
            )
            if self._sq_drizzlers is not None:
                self._sq_drizzlers[c].add_image(
                    data=ch * ch,
                    exptime=1.0,
                    pixmap=pixmap,
                    weight_map=wmap,
                    pixfrac=self.params.pixfrac,
                    in_units="counts",
                )
        if self._count is not None:
            self._count += (
                self._drizzlers[0].out_wht > prev_wht0
            ).astype(np.uint32, copy=False)
        self._n_added += 1

    def clip_reference(self, kappa: float) -> tuple[np.ndarray, np.ndarray]:
        """
        Build the per-output-pixel clip reference ``(mean, tol)`` from a
        statistics pass (``compute_stats=True``).

        ``mean`` is the weighted mean of the contributions (NaN where nothing
        landed). ``tol`` is ``kappa × σ`` of those contributions, with a
        Bessel-style small-sample correction, and ``+inf`` (never reject)
        wherever the effective contribution count is below ``_MIN_REJECT_NEFF``
        — clipping against one or two samples is noise, not statistics.
        """
        if self._sq_drizzlers is None:
            raise ValueError("clip_reference requires compute_stats=True")
        h, w = self.out_shape
        mean = np.full((h, w, 3), np.nan, dtype=np.float32)
        tol = np.full((h, w, 3), np.inf, dtype=np.float32)
        for c in range(3):
            m = self._drizzlers[c].out_img
            m2 = self._sq_drizzlers[c].out_img
            wht = self._drizzlers[c].out_wht
            # Weighted population variance; the accumulated weight doubles as
            # an effective sample count (unit frame weights × pixfrac overlap
            # ≈ number of contributing frames).
            var = np.clip(m2 - m * m, 0.0, None)
            neff = wht
            # Bessel factor only where it's meaningful; below the neff gate the
            # tolerance becomes +inf anyway, so avoid a blow-up/overflow there.
            bessel = np.where(neff > 1.0, neff / np.maximum(neff - 1.0, 1e-6), 1.0)
            var = var * bessel
            t = (float(kappa) * np.sqrt(var)).astype(np.float32)
            covered = wht > 0
            t[~covered | (neff < _MIN_REJECT_NEFF)] = np.inf
            mean[..., c] = np.where(covered, m, np.nan)
            tol[..., c] = t
        return mean, tol

    def result(self) -> np.ndarray:
        """
        Mean image, NaN where no input frame contributed.

        The STScI drizzle library already keeps ``out_img`` as the running
        *weighted average* of every contribution (not the raw sum); ``out_wht``
        is the accumulated per-pixel weight. So ``out_img`` is directly the mean
        surface brightness per output pixel — dividing it by ``out_wht`` again
        would deflate the flux by roughly the number of contributing frames
        (and overflow where the weight is large). We only need ``out_img``,
        masked to NaN where nothing landed (``out_wht == 0``), so drizzle at
        ``scale=1, pixfrac=1`` conserves surface brightness and matches the
        weighted-mean path.
        """
        h, w = self.out_shape
        rgb = np.full((h, w, 3), np.nan, dtype=np.float32)
        for c, driz in enumerate(self._drizzlers):
            wht = driz.out_wht
            img = driz.out_img
            rgb[..., c] = np.where(wht > 0, img, np.nan)
        return rgb

    @property
    def coverage(self) -> np.ndarray:
        """(H, W, 3) per-pixel weight — used for the coverage map output."""
        h, w = self.out_shape
        cov = np.zeros((h, w, 3), dtype=np.float32)
        for c, driz in enumerate(self._drizzlers):
            cov[..., c] = driz.out_wht
        return cov

    @property
    def frame_coverage(self) -> np.ndarray | None:
        """Per-output-pixel **frame count** (2-D), independent of quality weights
        and pixfrac/scale.

        Unlike :attr:`coverage` (Σ of weighted footprint overlap), this counts
        how many frames actually deposited signal into each output pixel, so
        ``coverage_min``/``coverage_max`` report an honest "N frames per pixel"
        even with quality weighting on (or any pixfrac<1 / scale≠1, where the
        weight sum is fractional). ``None`` on a statistics-only accumulator,
        whose output is discarded."""
        return self._count

    @property
    def n_added(self) -> int:
        return self._n_added

    def rejection_counts(self) -> tuple[int, int]:
        """``(n_contributed, n_rejected)`` — how many covered samples the
        reject pass saw and how many its κ-σ clip dropped, summed while pass 2
        ran (no per-frame tracking, no extra canvas). Both zero when this
        drizzler was fed no ``clip`` (single-pass drizzle). The fraction is
        *data-driven* like the standard κ-σ path (contributions outside
        ``mean ± κ·σ``), so the stacker surfaces it with the sigma-clip trust
        wording, not min/max's structural one."""
        return self._n_contributed, self._n_rejected


def _compute_output_canvas(ref_wcs, ref_shape: tuple[int, int], scale: float):
    """
    Build a scaled output WCS and shape from the reference.

    For ``scale=1.0`` the output equals the reference; for ``scale=2.0`` the
    output canvas has 4× the area at half the input pixel scale.
    """
    h_in, w_in = ref_shape
    h_out = int(round(h_in * scale))
    w_out = int(round(w_in * scale))
    out_wcs = ref_wcs.deepcopy()
    # Scale CRPIX so the same sky point still maps to the same fractional
    # offset within the canvas.
    out_wcs.wcs.crpix = (
        (ref_wcs.wcs.crpix[0] - 0.5) * scale + 0.5,
        (ref_wcs.wcs.crpix[1] - 0.5) * scale + 0.5,
    )
    # Scale CDELT (or CD matrix) so the pixel scale shrinks by ``scale``.
    if out_wcs.wcs.has_cd():
        out_wcs.wcs.cd = ref_wcs.wcs.cd / scale
    else:
        out_wcs.wcs.cdelt = ref_wcs.wcs.cdelt / scale
    return (h_out, w_out), out_wcs


def _build_pixmap(in_wcs, out_wcs, h_in: int, w_in: int) -> np.ndarray:
    """
    For each input pixel, return its output (x, y) pixel coordinate.

    ``pixmap`` shape is (h_in, w_in, 2) with [..., 0]=x and [..., 1]=y.
    Drizzle uses this to determine where each input pixel "drops" into the
    output canvas — far simpler than an internal WCS round-trip.
    """
    from astropy.wcs.utils import pixel_to_pixel

    yy, xx = np.indices((h_in, w_in), dtype=np.float64)
    out_x, out_y = pixel_to_pixel(in_wcs, out_wcs, xx, yy)
    pixmap = np.empty((h_in, w_in, 2), dtype=np.float64)
    pixmap[..., 0] = out_x
    pixmap[..., 1] = out_y
    # Replace NaNs (points outside projection) with -1 so drizzle ignores them.
    bad = ~(np.isfinite(pixmap[..., 0]) & np.isfinite(pixmap[..., 1]))
    pixmap[bad] = -1.0
    return pixmap
