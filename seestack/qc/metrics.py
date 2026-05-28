"""
Per-frame quality metrics.

Computed once per frame and stored in the project DB. The whole point of having
these is so the user can sort/filter the frame table to find bad subs without
opening each one.

Metrics
-------
- ``star_count``        : number of detected stars. Sudden drops = clouds.
- ``sky_adu_median``    : median sky background, ADU. Higher = more light pollution
                          / moonlight / haze.
- ``fwhm_px``           : median full-width-at-half-max of detected stars, in
                          pixels. Lower = sharper.
- ``eccentricity_median``: 0=round, 1=elongated. Tracking errors push this up.

Implementation notes
--------------------
Star detection runs on the **raw Bayer mosaic's green channel** (every other
pixel on a checkerboard) — no debayer needed for QC. Stars are wider than 2
pixels, so the green-only image still has plenty of signal and runs ~2× faster
than detecting on a debayered RGB stack.

DAOStarFinder is photutils' standard finder; it's fast and robust. We size it
for Seestar pixel scale (~2.5 arcsec/px) where stars are typically 2.5–4 px
FWHM. Threshold is in units of the sky standard deviation, so it adapts to the
sky brightness automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class FrameMetrics:
    """Output of one full QC pass on one frame."""

    star_count: int
    sky_adu_median: float
    fwhm_px: float | None
    eccentricity_median: float | None
    streak_detected: bool = False
    streak_count: int = 0


def green_channel(mosaic: np.ndarray, pattern: str = "RGGB") -> np.ndarray:
    """
    Pull the green pixels out of a raw Bayer mosaic into a half-resolution image.

    Cheaper than debayer and good enough for star detection / FWHM / sky stats.
    """
    pattern = pattern.upper()
    layouts = {
        "RGGB": ((0, 1), (1, 0)),  # G is at top-right and bottom-left
        "BGGR": ((0, 1), (1, 0)),
        "GRBG": ((0, 0), (1, 1)),
        "GBRG": ((0, 0), (1, 1)),
    }
    if pattern not in layouts:
        # Fall back to a sensible default rather than failing QC.
        log.warning("unknown bayer pattern %r, falling back to RGGB layout", pattern)
        pattern = "RGGB"
    (y1, x1), (y2, x2) = layouts[pattern]
    g1 = mosaic[y1::2, x1::2]
    g2 = mosaic[y2::2, x2::2]
    # Crop to common size, then average.
    h = min(g1.shape[0], g2.shape[0])
    w = min(g1.shape[1], g2.shape[1])
    return 0.5 * (g1[:h, :w] + g2[:h, :w])


def estimate_sky(image: np.ndarray) -> tuple[float, float]:
    """Return ``(median, std)`` of the sky background using sigma-clipping."""
    from astropy.stats import sigma_clipped_stats

    _, median, std = sigma_clipped_stats(image, sigma=3.0, maxiters=5)
    return float(median), float(std)


def detect_stars(
    image: np.ndarray,
    *,
    fwhm_guess_px: float = 3.0,
    threshold_sigma: float = 5.0,
    sky_median: float | None = None,
    sky_std: float | None = None,
) -> "np.ndarray":
    """
    Find stars with photutils DAOStarFinder. Returns an astropy QTable rows.

    Parameters
    ----------
    image
        2D image (typically the green channel at half-resolution).
    fwhm_guess_px
        Approximate stellar FWHM. For Seestar at ~2.5"/px on the half-res green
        channel, 3.0 is a reasonable starting point.
    threshold_sigma
        How many sky standard deviations above the median a peak must be. 5σ is
        the standard photometry threshold and keeps false positives low.
    sky_median, sky_std
        If you already have these, pass them in to avoid recomputing.
    """
    from photutils.detection import DAOStarFinder

    if sky_median is None or sky_std is None:
        sky_median, sky_std = estimate_sky(image)

    finder = DAOStarFinder(
        fwhm=fwhm_guess_px,
        threshold=threshold_sigma * sky_std,
        exclude_border=True,
    )
    sources = finder(image - sky_median)
    return sources  # may be None if nothing found


def median_fwhm(image: np.ndarray, sources, *, box_size: int = 11) -> float | None:
    """
    Estimate median FWHM by fitting a 2D Gaussian to small cutouts around the
    brightest detected stars.

    Returns None if no usable stars (e.g. all near edges, all saturated).
    """
    if sources is None or len(sources) == 0:
        return None
    from astropy.modeling import fitting, models

    h, w = image.shape
    half = box_size // 2

    # Use up to 30 of the brightest non-saturated stars — more than enough for a
    # stable median, and bounds the time per frame.
    sources = sources.copy()
    sources.sort("flux", reverse=True)
    sources = sources[:30]

    fwhms: list[float] = []
    fitter = fitting.LevMarLSQFitter()
    # photutils renamed columns from xcentroid → x_centroid; support both for
    # version flexibility.
    cols = sources.colnames
    xcol = "x_centroid" if "x_centroid" in cols else "xcentroid"
    ycol = "y_centroid" if "y_centroid" in cols else "ycentroid"
    for row in sources:
        x = float(row[xcol])
        y = float(row[ycol])
        ix = int(round(x))
        iy = int(round(y))
        if ix - half < 0 or ix + half + 1 > w or iy - half < 0 or iy + half + 1 > h:
            continue
        cutout = image[iy - half : iy + half + 1, ix - half : ix + half + 1]
        cutout = cutout - np.median(cutout)
        if cutout.max() <= 0:
            continue
        # Initial Gaussian guess.
        g_init = models.Gaussian2D(
            amplitude=cutout.max(),
            x_mean=half, y_mean=half,
            x_stddev=2.0, y_stddev=2.0,
        )
        yy, xx = np.indices(cutout.shape)
        try:
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                g = fitter(g_init, xx, yy, cutout)
        except Exception:  # noqa: BLE001 — fits fail on noisy stars, fine to skip
            continue
        sx = abs(float(g.x_stddev.value))
        sy = abs(float(g.y_stddev.value))
        if not np.isfinite(sx) or not np.isfinite(sy) or sx == 0 or sy == 0:
            continue
        # FWHM from sigma: 2 * sqrt(2 * ln 2) ≈ 2.3548
        fwhm = 2.3548200450309493 * 0.5 * (sx + sy)
        if 0.5 < fwhm < 20.0:
            fwhms.append(fwhm)

    if not fwhms:
        return None
    return float(np.median(fwhms))


def median_eccentricity(sources) -> float | None:
    """
    Median star eccentricity from DAOStarFinder's roundness measure.

    DAOStarFinder produces ``roundness1`` and ``roundness2``; near-zero means
    round. We map to a 0-1 eccentricity via |roundness|, clipped — this is an
    approximation, but it tracks tracking errors well enough to flag bad frames.
    """
    if sources is None or len(sources) == 0:
        return None
    r1 = np.abs(np.asarray(sources["roundness1"]))
    r2 = np.abs(np.asarray(sources["roundness2"]))
    ecc = np.clip(np.maximum(r1, r2), 0.0, 1.0)
    return float(np.median(ecc))


def compute_frame_metrics(
    fits_path: str | Path,
    *,
    bayer_pattern: str | None = None,
    detect_streaks: bool = True,
) -> FrameMetrics:
    """
    Run the full QC pass on one frame and return all metrics. Pure function:
    safe to call from a worker process.
    """
    from seestack.io.fits_loader import load_seestar_raw

    img, info = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    pattern = bayer_pattern or info.bayer_pattern or "RGGB"
    g = green_channel(img, pattern=pattern)

    sky_med, sky_std = estimate_sky(g)
    sources = detect_stars(g, sky_median=sky_med, sky_std=sky_std)
    n_stars = 0 if sources is None else int(len(sources))
    fwhm = median_fwhm(g, sources)
    ecc = median_eccentricity(sources)

    streak_flag = False
    streak_n = 0
    if detect_streaks:
        from seestack.qc.streaks import detect_streaks as _ds
        streak_flag, streak_n = _ds(g, sky_median=sky_med, sky_std=sky_std)

    return FrameMetrics(
        star_count=n_stars,
        sky_adu_median=sky_med,
        fwhm_px=fwhm,
        eccentricity_median=ecc,
        streak_detected=streak_flag,
        streak_count=streak_n,
    )
