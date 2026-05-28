"""Helpers to synthesise fake Seestar FITS files for tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def make_star_field(
    width: int = 480,
    height: int = 320,
    n_stars: int = 40,
    seed: int = 42,
    star_fwhm_px_full: float = 4.0,
    sky_level: float = 1000.0,
    sky_noise: float = 50.0,
    streak: bool = False,
) -> np.ndarray:
    """
    Generate a fake Bayer mosaic with Gaussian stars on a noisy sky.

    Width and height refer to the mosaic dimensions (full sensor). The bayer
    pattern is RGGB. Returns a uint16 array suitable for FITS BITPIX=16.
    """
    rng = np.random.default_rng(seed)
    img = rng.normal(loc=sky_level, scale=sky_noise, size=(height, width)).astype(np.float32)

    # Place stars at random positions, each a 2D gaussian.
    sigma = star_fwhm_px_full / 2.3548
    box = max(7, int(np.ceil(sigma * 6)))
    half = box // 2
    yy, xx = np.indices((box, box))
    for _ in range(n_stars):
        # Keep away from the edges so we don't worry about clipping.
        cx = int(rng.integers(half + 4, width - half - 4))
        cy = int(rng.integers(half + 4, height - half - 4))
        peak = float(rng.uniform(2000, 30000))
        kernel = peak * np.exp(-((xx - half) ** 2 + (yy - half) ** 2) / (2 * sigma * sigma))
        img[cy - half : cy - half + box, cx - half : cx - half + box] += kernel

    if streak:
        # A diagonal bright streak crossing most of the frame.
        for t in range(0, min(width, height) - 20):
            y = 30 + t
            x = 20 + t
            if 0 <= y < height and 0 <= x < width:
                img[y, x] += 8000
                if x + 1 < width:
                    img[y, x + 1] += 4000
                if y + 1 < height:
                    img[y + 1, x] += 4000

    img = np.clip(img, 0, 65535).astype(np.uint16)
    return img


def write_seestar_fits(
    path: str | Path,
    *,
    width: int = 480,
    height: int = 320,
    n_stars: int = 40,
    seed: int = 42,
    streak: bool = False,
    add_wcs: bool = False,
    ra_center_deg: float = 83.6,
    dec_center_deg: float = -5.4,
    pixscale_arcsec: float = 5.0,
) -> Path:
    """Write a synth FITS file with Seestar-like headers. Requires astropy."""
    from astropy.io import fits

    data = make_star_field(
        width=width, height=height, n_stars=n_stars, seed=seed, streak=streak
    )
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["EXPTIME"] = 10.0
    hdu.header["GAIN"] = 80.0
    hdu.header["CCD-TEMP"] = -10.0
    hdu.header["DATE-OBS"] = "2024-09-12T03:14:55.123"
    hdu.header["INSTRUME"] = "Seestar S50"
    if add_wcs:
        # Simple TAN-projected WCS — enough for stacker tests to reproject.
        hdu.header["CTYPE1"] = "RA---TAN"
        hdu.header["CTYPE2"] = "DEC--TAN"
        hdu.header["CRVAL1"] = ra_center_deg
        hdu.header["CRVAL2"] = dec_center_deg
        hdu.header["CRPIX1"] = width / 2 + 0.5
        hdu.header["CRPIX2"] = height / 2 + 0.5
        hdu.header["CDELT1"] = -pixscale_arcsec / 3600.0
        hdu.header["CDELT2"] = pixscale_arcsec / 3600.0
    path = Path(path)
    hdu.writeto(path, overwrite=True)
    return path


def make_synth_wcs_text(
    *,
    width: int = 480,
    height: int = 320,
    ra_center_deg: float = 83.6,
    dec_center_deg: float = -5.4,
    pixscale_arcsec: float = 5.0,
) -> str:
    """A serialised WCS header string usable as ``frame.wcs_json`` in tests."""
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra_center_deg, dec_center_deg]
    w.wcs.crpix = [width / 2 + 0.5, height / 2 + 0.5]
    w.wcs.cdelt = [-pixscale_arcsec / 3600.0, pixscale_arcsec / 3600.0]
    return str(w.to_header(relax=True))
