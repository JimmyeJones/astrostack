"""
Photometric color calibration.

Two implementations:

  - **Gray-star** (no network needed): detect stars, measure their R/G/B
    aperture fluxes, assume the *average* star is neutral white. Solve for
    per-channel scale factors so the median star colour is grey. This is the
    classic OSC fallback — works well in densely populated fields, less well
    in regions with strongly biased star populations.

  - **Gaia** (requires astroquery + internet): cross-match detected stars to
    the Gaia catalog by sky coordinates. Use each match's published BP-RP
    colour to predict what its R/G/B should be in a "physically correct"
    image, then solve for scale factors that best fit the data. This is what
    SiriL's PCC and PixInsight's SPCC do.

Both modes return ``(R_scale, G_scale, B_scale)`` factors. The G channel is
locked to 1.0 (the reference), so calibration only changes R and B relative
to G. Apply by multiplying each channel by its factor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


MODE_GRAY_STAR = "gray_star"
MODE_GAIA = "gaia"


@dataclass
class ColorCalibrationOptions:
    enabled: bool = False
    mode: str = MODE_GRAY_STAR  # 'gray_star' | 'gaia'
    detect_threshold_sigma: float = 6.0
    aperture_radius_px: float = 4.0
    min_stars: int = 20
    # Gaia-only knobs:
    gaia_max_stars: int = 500
    gaia_max_g_mag: float = 17.0
    gaia_timeout_s: float = 45.0  # network query is bounded by this


@dataclass
class ColorCalibrationResult:
    """The scale factors applied (G is always 1.0)."""

    scale_rgb: tuple[float, float, float]
    n_stars_used: int
    mode_used: str
    notes: str = ""


def calibrate_color(
    rgb: np.ndarray,
    wcs=None,
    options: ColorCalibrationOptions | None = None,
) -> tuple[np.ndarray, ColorCalibrationResult]:
    """
    Apply photometric colour calibration to a stacked RGB image.

    Returns ``(calibrated_rgb, result)``. If too few stars are found or the
    Gaia query fails, falls back to gray-star automatically; if even that
    can't be done, returns the input unchanged with ``mode_used="none"``.
    """
    if options is None:
        options = ColorCalibrationOptions(enabled=True)
    if not options.enabled:
        return rgb, ColorCalibrationResult((1.0, 1.0, 1.0), 0, "none", "disabled")

    # 1. Detect bright stars on luminance.
    detections = _detect_calibration_stars(rgb, options)
    if detections is None or len(detections) < options.min_stars:
        return rgb, ColorCalibrationResult(
            (1.0, 1.0, 1.0), 0, "none",
            f"only {0 if detections is None else len(detections)} stars found",
        )

    # 2. Aperture photometry per channel.
    fluxes = _aperture_photometry(rgb, detections, options.aperture_radius_px)
    # Keep only stars with positive flux in all 3 channels.
    keep = (fluxes[:, 0] > 0) & (fluxes[:, 1] > 0) & (fluxes[:, 2] > 0)
    fluxes = fluxes[keep]
    detections = detections[keep]
    if len(fluxes) < options.min_stars:
        return rgb, ColorCalibrationResult(
            (1.0, 1.0, 1.0), int(len(fluxes)), "none",
            "not enough stars with positive flux in every channel",
        )

    # 3. Solve for scale factors.
    if options.mode == MODE_GAIA and wcs is not None:
        try:
            # The Gaia query hits the network — bound it with a timeout so a
            # slow or unreachable server can't hang the whole stack. On
            # timeout (or any failure) we fall back to the offline gray-star
            # solver instead of blocking forever.
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout

            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_solve_gaia, rgb, fluxes, detections, wcs, options)
                try:
                    scale, n, note = fut.result(timeout=options.gaia_timeout_s)
                except FTimeout:
                    fut.cancel()
                    raise RuntimeError(
                        f"Gaia query exceeded {options.gaia_timeout_s:.0f}s"
                    ) from None
            calibrated = _apply_scale(rgb, scale)
            return calibrated, ColorCalibrationResult(scale, n, "gaia", note)
        except Exception as exc:  # noqa: BLE001
            log.warning("Gaia calibration failed (%s); falling back to gray-star", exc)

    scale, n, note = _solve_gray_star(fluxes)
    calibrated = _apply_scale(rgb, scale)
    return calibrated, ColorCalibrationResult(scale, n, "gray_star", note)


# ---- detection + photometry -------------------------------------------------


# Hard cap on stars carried into aperture photometry. Calibration only needs
# a few hundred well-measured stars; without a cap, a bad sky estimate on a
# big mosaic can produce hundreds of thousands of spurious detections and the
# photometry loop appears to hang.
MAX_CALIBRATION_STARS = 2000


def _detect_calibration_stars(rgb: np.ndarray, options: ColorCalibrationOptions):
    """Find bright, isolated, non-saturated stars on the luminance image.

    NaN-aware: on a mosaic union canvas the uncovered regions are NaN. If
    those were zero-filled before the sky estimate, ``sigma_clipped_stats``
    would return a tiny ``std`` (the zeros dominate), the detection threshold
    would collapse, and DAOStarFinder would flag every noise pixel. We mask
    the uncovered pixels out of both the statistics and the finder, and cap
    the detection count as a final safety net.
    """
    from astropy.stats import sigma_clipped_stats
    from photutils.detection import DAOStarFinder

    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32, copy=False)
    finite_mask = np.isfinite(luma)
    if not finite_mask.any():
        return None
    uncovered = ~finite_mask

    # Sky stats over covered pixels only.
    _, med, std = sigma_clipped_stats(
        luma, mask=uncovered, sigma=3.0, maxiters=5,
    )
    if not np.isfinite(std) or std <= 0:
        return None

    # DAOStarFinder needs a finite array; zero-fill the uncovered pixels but
    # *also* pass them as a mask so the finder ignores them (and the hard
    # edge between covered sky and the zero region can't be flagged as stars).
    luma_clean = np.where(finite_mask, luma, 0.0).astype(np.float32, copy=False)
    finder = DAOStarFinder(
        fwhm=3.0,
        threshold=options.detect_threshold_sigma * float(std),
        exclude_border=True,
    )
    sources = finder(luma_clean - float(med), mask=uncovered)
    if sources is None or len(sources) == 0:
        return sources

    # Cap to the brightest N — calibration doesn't need more, and this bounds
    # the cost of the aperture-photometry step no matter how the sky estimate
    # turned out.
    if len(sources) > MAX_CALIBRATION_STARS:
        sources = sources.copy()
        sources.sort("flux", reverse=True)
        sources = sources[:MAX_CALIBRATION_STARS]
        log.info("Color cal: capped %d detections to brightest %d",
                 len(sources), MAX_CALIBRATION_STARS)
    return sources


def _aperture_photometry(rgb: np.ndarray, sources, radius: float) -> np.ndarray:
    """Per-star, per-channel aperture flux (background-subtracted)."""
    from photutils.aperture import CircularAnnulus, CircularAperture, aperture_photometry

    xcol = "x_centroid" if "x_centroid" in sources.colnames else "xcentroid"
    ycol = "y_centroid" if "y_centroid" in sources.colnames else "ycentroid"
    positions = np.stack(
        [np.asarray(sources[xcol]), np.asarray(sources[ycol])], axis=-1
    )
    aper = CircularAperture(positions, r=radius)
    annulus = CircularAnnulus(positions, r_in=radius + 2, r_out=radius + 5)
    n = len(sources)
    out = np.zeros((n, 3), dtype=np.float32)
    for c in range(3):
        ch = np.where(np.isfinite(rgb[..., c]), rgb[..., c], 0.0).astype(np.float32, copy=False)
        phot = aperture_photometry(ch, aper)
        bg = aperture_photometry(ch, annulus)
        bg_per_pixel = bg["aperture_sum"] / annulus.area
        out[:, c] = (
            np.asarray(phot["aperture_sum"]) - np.asarray(bg_per_pixel) * aper.area
        ).astype(np.float32)
    return out


# ---- solvers ---------------------------------------------------------------


def _solve_gray_star(fluxes: np.ndarray) -> tuple[tuple[float, float, float], int, str]:
    """
    Per-channel scale = median(G_flux) / median(channel_flux), normalised so G=1.

    The assumption: the median star is approximately white. True on average
    over hundreds of stars; doesn't hold exactly but produces clean OSC
    calibration without external data.
    """
    med_r = float(np.median(fluxes[:, 0]))
    med_g = float(np.median(fluxes[:, 1]))
    med_b = float(np.median(fluxes[:, 2]))
    if med_g <= 0:
        return (1.0, 1.0, 1.0), len(fluxes), "G flux median is zero"
    scale_r = med_g / med_r if med_r > 0 else 1.0
    scale_b = med_g / med_b if med_b > 0 else 1.0
    return (scale_r, 1.0, scale_b), int(len(fluxes)), "gray-world over detected stars"


def _solve_gaia(
    rgb: np.ndarray,
    fluxes: np.ndarray,
    sources,
    wcs,
    options: ColorCalibrationOptions,
) -> tuple[tuple[float, float, float], int, str]:
    """
    Cross-match detected stars to Gaia, fit per-channel scale.

    The simple model: for a star with Gaia BP-RP colour ``c``, the expected
    R/G and B/G ratios follow a roughly linear function of ``c``. We don't
    need to be perfect — fitting only the central tendency (the "average"
    star's colour) is enough to get OSC raws to a believable white balance.
    """
    from astroquery.gaia import Gaia

    # Get sky coords of all detections.
    xcol = "x_centroid" if "x_centroid" in sources.colnames else "xcentroid"
    ycol = "y_centroid" if "y_centroid" in sources.colnames else "ycentroid"
    xs = np.asarray(sources[xcol])
    ys = np.asarray(sources[ycol])
    sky = wcs.pixel_to_world(xs, ys)

    # Query a cone around the frame centre. The frame is small so a single
    # cone gets everything.
    h, w = rgb.shape[:2]
    centre = wcs.pixel_to_world(w / 2.0, h / 2.0)
    # Worst-case radius is half the diagonal.
    corner = wcs.pixel_to_world(0.0, 0.0)
    radius_deg = float(centre.separation(corner).deg) * 1.1
    log.info("Querying Gaia: centre=(%.3f, %.3f) radius=%.3f° max=%d",
             centre.ra.deg, centre.dec.deg, radius_deg, options.gaia_max_stars)
    Gaia.ROW_LIMIT = options.gaia_max_stars
    job = Gaia.cone_search_async(
        coordinate=centre, radius=f"{radius_deg} deg",
    )
    gaia_table = job.get_results()
    if len(gaia_table) == 0:
        raise RuntimeError("no Gaia stars in field")

    # Match each detection to the nearest Gaia source within 5 px.
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    g_ra = np.asarray(gaia_table["ra"])
    g_dec = np.asarray(gaia_table["dec"])
    g_sky = SkyCoord(g_ra * u.deg, g_dec * u.deg)
    idx, sep, _ = sky.match_to_catalog_sky(g_sky)
    # 5 px tolerance translates to ~12.5" for the Seestar; use 10" upper bound.
    max_sep = 10.0 * u.arcsec
    matched = sep < max_sep

    # Compute BP-RP per matched star, then expected R/G and B/G under a simple
    # linear-in-colour model: R/G = a_r + b_r * (BP-RP), B/G = a_b + b_b * (BP-RP).
    # Coefficients here are rough averages from public OSC calibrations; users
    # who want better can swap them in via subclassing later.
    a_r, b_r = 0.95, 0.40   # red channel ratio vs BP-RP
    a_b, b_b = 1.10, -0.45  # blue channel ratio vs BP-RP

    bp = np.asarray(gaia_table["phot_bp_mean_mag"])
    rp = np.asarray(gaia_table["phot_rp_mean_mag"])
    g_mag = np.asarray(gaia_table["phot_g_mean_mag"])
    color = bp - rp

    use = matched & np.isfinite(color) & np.isfinite(g_mag) & (g_mag < options.gaia_max_g_mag)
    use_idx = idx[use]
    f_match = fluxes[use]
    if len(f_match) < options.min_stars:
        raise RuntimeError(f"only {len(f_match)} Gaia matches")

    c_match = color[use_idx]
    expected_rg = a_r + b_r * c_match
    expected_bg = a_b + b_b * c_match

    measured_rg = f_match[:, 0] / f_match[:, 1]
    measured_bg = f_match[:, 2] / f_match[:, 1]

    # Scale that aligns measured ratios to expected ratios — solve robustly
    # with the median.
    scale_r = float(np.median(expected_rg / np.maximum(measured_rg, 1e-9)))
    scale_b = float(np.median(expected_bg / np.maximum(measured_bg, 1e-9)))
    n_used = int(len(f_match))
    return (
        (scale_r, 1.0, scale_b),
        n_used,
        f"matched {n_used} Gaia stars within {max_sep.value:.0f}\"",
    )


def _apply_scale(rgb: np.ndarray, scale: tuple[float, float, float]) -> np.ndarray:
    """Multiply each channel by the calibration scale factor."""
    out = rgb.astype(np.float32, copy=True)
    for c in range(3):
        if scale[c] != 1.0:
            out[..., c] = np.where(np.isfinite(out[..., c]), out[..., c] * scale[c], out[..., c])
    return out
