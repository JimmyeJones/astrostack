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
    accumulation is one-shot. Outlier rejection has to come from the
    frame-level streak detector and from QC (which we already do).
  - Drizzle is slower per frame than reproject + accumulate, especially with
    ``scale > 1`` (which expands the output canvas).

Recommendation: use drizzle when you have **lots** of dithered frames
(typically 200+) AND want extra resolution. Otherwise the weighted-mean path
gives faster, equally clean results on Seestar data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


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
    ) -> None:
        from drizzle.resample import Drizzle

        self.params = params
        self.ref_wcs = ref_wcs
        self.ref_shape = ref_shape
        self.out_shape, self.out_wcs = _compute_output_canvas(ref_wcs, ref_shape, params.scale)

        self._drizzlers = [
            Drizzle(
                kernel=params.kernel,
                fillval=0.0,
                out_shape=self.out_shape,
                exptime=0.0,
            )
            for _ in range(3)
        ]
        self._n_added = 0

    @property
    def output_canvas_shape(self) -> tuple[int, int]:
        return self.out_shape

    def add_frame(self, rgb: np.ndarray, in_wcs) -> None:
        """
        Add one debayered, optionally bg-flattened frame to the drizzle.

        ``rgb`` is (H, W, 3) at the input frame's resolution. ``in_wcs`` is
        the input frame's astropy WCS.
        """
        # Drizzle wants a "pixmap" — for each input pixel, the (x, y)
        # coordinate in the output. Compute once per frame, share across
        # channels (saves ~3× the WCS transform cost).
        pixmap = _build_pixmap(in_wcs, self.out_wcs, rgb.shape[0], rgb.shape[1])
        # Mask out-of-bounds pixels with a weight map of 0.
        h_out, w_out = self.out_shape
        weight = (
            (pixmap[..., 0] >= 0) & (pixmap[..., 0] <= w_out - 1)
            & (pixmap[..., 1] >= 0) & (pixmap[..., 1] <= h_out - 1)
        ).astype(np.float32)
        for c in range(3):
            ch = np.where(np.isfinite(rgb[..., c]), rgb[..., c], 0.0).astype(np.float32, copy=False)
            self._drizzlers[c].add_image(
                data=ch,
                exptime=1.0,
                pixmap=pixmap,
                weight_map=weight,
                pixfrac=self.params.pixfrac,
                in_units="counts",
            )
        self._n_added += 1

    def result(self) -> np.ndarray:
        """
        Mean image, NaN where no input frame contributed.

        Drizzle's ``out_img`` is the sum of contributions and ``out_wht`` is
        the per-pixel weight (in input pixel area). For our purposes
        ``out_img / out_wht`` gives the mean intensity per output pixel.
        """
        h, w = self.out_shape
        rgb = np.full((h, w, 3), np.nan, dtype=np.float32)
        for c, driz in enumerate(self._drizzlers):
            wht = driz.out_wht
            img = driz.out_img
            nz = wht > 0
            rgb[..., c] = np.where(nz, img / np.where(nz, wht, 1.0), np.nan)
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
    def n_added(self) -> int:
        return self._n_added


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
