"""
Mosaic output-canvas computation.

The stacker reprojects every frame onto a single shared output canvas. For a
single-target stack that canvas can just be the reference frame's footprint.
For a **mosaic** — where the Seestar panned across a region larger than its
~1.3° field — the canvas has to be the *union* of every frame's footprint, or
the off-panel frames have nowhere to land and you get the classic "only the
reference panel shows, with bright contamination at its edges" bug.

``compute_mosaic_canvas`` builds that union canvas:

  1. Collect the 4 sky-corner coordinates of every plate-solved frame.
  2. Pick a tangent point at the median (RA, Dec) of all corners.
  3. Build a TAN-projected WCS there at the median input pixel scale.
  4. Project every corner into that WCS, take the bounding box, and shift
     CRPIX so the box's min corner sits at pixel (0, 0).

Once all frames share this canvas the weighted-sum accumulator's per-pixel
``sum / coverage`` normalisation makes overlapping regions come out at the
same brightness as single-coverage regions — no bright seams.

RA wraparound: Seestar mosaics span a few degrees at most, so the only risk
is a mosaic straddling RA = 0°. We detect a >180° apparent spread and shift
into a continuous frame before taking the median.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Hard ceiling so a pathological frame set (one bad plate-solve flung across
# the sky) can't try to allocate a terabyte-scale canvas.
MAX_CANVAS_PX = 16000

# In "auto" mode, only switch to a union canvas when it's meaningfully bigger
# than the reference frame — otherwise a normal dithered single-target stack
# would needlessly get a slightly different canvas size. 1.3× area is the
# threshold (roughly: footprint centres span more than ~15% of the FOV).
AUTO_UNION_AREA_RATIO = 1.3


@dataclass
class CanvasResult:
    """Output of ``compute_mosaic_canvas``."""

    wcs_text: str
    shape: tuple[int, int]      # (height, width)
    is_mosaic: bool             # True if the union is materially bigger than ref
    n_footprints: int
    span_deg: float             # diagonal sky span of the union


def compute_mosaic_canvas(
    frames,
    reference_shape: tuple[int, int],
    *,
    max_canvas_px: int = MAX_CANVAS_PX,
) -> CanvasResult | None:
    """
    Compute the union output canvas for a set of plate-solved frames.

    Parameters
    ----------
    frames
        Iterable of FrameRow. Frames without WCS / dimensions are skipped.
    reference_shape
        (h, w) of the reference frame — used to decide ``is_mosaic``.
    max_canvas_px
        Raise ``ValueError`` if either canvas dimension would exceed this.

    Returns
    -------
    CanvasResult, or None if fewer than one usable frame was found (caller
    should fall back to the reference-frame canvas).
    """
    from astropy.coordinates import SkyCoord
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales
    import astropy.units as u

    from seestack.io.wcs_io import footprint_radec_deg, wcs_from_text, wcs_to_text

    all_ra: list[float] = []
    all_dec: list[float] = []
    pixscales: list[float] = []
    n_footprints = 0

    for f in frames:
        if not f.wcs_json or f.width_px is None or f.height_px is None:
            continue
        wcs = wcs_from_text(f.wcs_json)
        if wcs is None:
            continue
        corners = footprint_radec_deg(wcs, f.width_px, f.height_px)
        if not corners:
            continue
        n_footprints += 1
        for ra, dec in corners:
            all_ra.append(ra)
            all_dec.append(dec)
        # Derive the pixel scale from the WCS itself, not from the DB field —
        # the DB's pixscale_arcsec is populated by plate-solving and may be
        # None (e.g. frames imported with an embedded WCS). proj_plane_pixel_
        # scales returns degrees/pixel per axis; take the mean and convert.
        try:
            scales_deg = proj_plane_pixel_scales(wcs)
            pix_arcsec = float(np.mean(scales_deg)) * 3600.0
            if np.isfinite(pix_arcsec) and pix_arcsec > 0:
                pixscales.append(pix_arcsec)
        except Exception:  # noqa: BLE001 — degenerate WCS; fall back below
            pass

    if n_footprints == 0 or len(all_ra) < 4:
        return None

    ra = np.asarray(all_ra, dtype=np.float64)
    dec = np.asarray(all_dec, dtype=np.float64)

    # RA wraparound: if the apparent spread is huge, the set straddles 0°.
    # Shift everything > 180° into negative so the data is continuous.
    if ra.max() - ra.min() > 180.0:
        ra = np.where(ra > 180.0, ra - 360.0, ra)

    center_ra = float(np.median(ra))
    center_dec = float(np.median(dec))
    # Median pixel scale of the inputs; fall back to a Seestar-ish value.
    pixscale_arcsec = float(np.median(pixscales)) if pixscales else 2.5

    # Provisional TAN WCS at the union centroid.
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [center_ra % 360.0, center_dec]
    w.wcs.cdelt = [-pixscale_arcsec / 3600.0, pixscale_arcsec / 3600.0]
    w.wcs.crpix = [1.0, 1.0]

    # Project every corner into this WCS's pixel space (0-based).
    sky = SkyCoord((ra % 360.0) * u.deg, dec * u.deg)
    xs, ys = w.world_to_pixel(sky)
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    finite = np.isfinite(xs) & np.isfinite(ys)
    if not finite.any():
        return None
    xs = xs[finite]
    ys = ys[finite]

    x_min = float(np.floor(xs.min()))
    x_max = float(np.ceil(xs.max()))
    y_min = float(np.floor(ys.min()))
    y_max = float(np.ceil(ys.max()))

    # Pad by 1 px on every side so reproject interpolation at the edge is safe.
    width = int(x_max - x_min) + 3
    height = int(y_max - y_min) + 3
    if width > max_canvas_px or height > max_canvas_px:
        raise ValueError(
            f"mosaic canvas would be {width}×{height} px, exceeding the "
            f"{max_canvas_px} px limit. A frame with a bad plate-solve may be "
            "flinging the canvas across the sky — check the Footprints tab."
        )

    # Shift CRPIX so the bounding-box min corner lands at pixel (1, 1) with a
    # 1 px pad. world_to_pixel is 0-based; FITS CRPIX is 1-based.
    w.wcs.crpix = [
        w.wcs.crpix[0] - x_min + 1.0,
        w.wcs.crpix[1] - y_min + 1.0,
    ]

    ref_h, ref_w = reference_shape
    ref_area = max(ref_h * ref_w, 1)
    union_area = width * height
    is_mosaic = union_area > AUTO_UNION_AREA_RATIO * ref_area

    # Diagonal sky span of the union, for the log line.
    span_deg = float(
        np.hypot((x_max - x_min) * pixscale_arcsec,
                 (y_max - y_min) * pixscale_arcsec) / 3600.0
    )

    return CanvasResult(
        wcs_text=wcs_to_text(w),
        shape=(height, width),
        is_mosaic=is_mosaic,
        n_footprints=n_footprints,
        span_deg=span_deg,
    )
