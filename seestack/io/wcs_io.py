"""
WCS serialization for the project DB.

We store an astropy WCS as a FITS-header text blob in the ``wcs_json`` column
(despite the name — it's not really JSON, it's FITS header text, which is plain
ASCII and easy to inspect). FITS header round-trips cleanly through astropy
without any data loss.

This module wraps that round-trip so the rest of the code doesn't have to care
about astropy import paths or header formatting details.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

log = logging.getLogger(__name__)


def wcs_to_text(wcs) -> str:
    """Serialize an astropy WCS to a FITS-header text string."""
    return str(wcs.to_header(relax=True))


def wcs_from_text(text: str | None):
    """Reconstruct a WCS from a stored text blob. Returns None on failure."""
    if not text:
        return None
    import warnings

    from astropy.io.fits import Header
    from astropy.wcs import FITSFixedWarning, WCS

    try:
        with warnings.catch_warnings():
            # astropy "fixes" DATE-OBS → MJD-OBS and warns every time; it's
            # harmless normalisation, just noise. Silence it.
            warnings.simplefilter("ignore", FITSFixedWarning)
            return WCS(Header.fromstring(text))
    except Exception as exc:  # noqa: BLE001 — corrupt cache, treat as missing
        log.warning("WCS parse failed (treating frame as unsolved): %s", exc)
        return None


def wcs_text_from_sidecar(wcs_path: str | Path) -> str | None:
    """Read an ASTAP ``.wcs`` sidecar file and return its FITS header as text."""
    wcs_path = Path(wcs_path)
    if not wcs_path.exists():
        return None
    from astropy.io.fits import Header

    try:
        # ASTAP writes a tiny FITS header file (no data block).
        with open(wcs_path, "rb") as f:
            raw = f.read().decode("ascii", errors="replace")
        # The header is padded to multiples of 2880 bytes by FITS convention,
        # but astropy's ``Header.fromstring`` handles that gracefully.
        return str(Header.fromstring(raw))
    except Exception:  # noqa: BLE001
        return None


def celestial_wcs_from_fits(fits_path: str | Path):  # noqa: ANN201 — returns (WCS|None, int, int)
    """Read a 2-D celestial WCS and pixel dims from a FITS file's header.

    Returns ``(wcs, width_px, height_px)`` — the celestial (RA/Dec) WCS plus the
    image's ``NAXIS1``/``NAXIS2`` — or ``(None, 0, 0)`` when the file is missing,
    unreadable, or carries no celestial WCS. The stack output FITS is a
    ``(3, H, W)`` cube with only the 2-D celestial keys merged in (see
    :func:`seestack.stack.output._write_fits`), so we take ``wcs.celestial`` and
    guard ``has_celestial`` — a header with no WCS yields ``None`` rather than a
    silent identity WCS."""
    p = Path(fits_path)
    if not p.exists():
        return None, 0, 0
    import warnings

    from astropy.io import fits
    from astropy.wcs import WCS, FITSFixedWarning

    try:
        header = fits.getheader(p)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FITSFixedWarning)
            wcs = WCS(header).celestial
        if not wcs.has_celestial or wcs.naxis != 2:
            return None, 0, 0
        width = int(header.get("NAXIS1", 0) or 0)
        height = int(header.get("NAXIS2", 0) or 0)
        return wcs, width, height
    except Exception as exc:  # noqa: BLE001 — a bad/missing header just means "no WCS"
        log.warning("WCS read from FITS failed (%s): %s", p, exc)
        return None, 0, 0


def wcs_dict_rescaled_to_preview(
    fits_path: str | Path, preview_w: int, preview_h: int,
) -> dict | None:
    """The stack's **stored** celestial WCS, rescaled to a downscaled preview PNG.

    The stack master FITS carries the *true* canvas WCS — for a mosaic that is the
    astropy-built union canvas WCS (`compute_mosaic_canvas`), for a single target
    the reference frame's own solved WCS — merged into its header by
    :func:`seestack.stack.output._write_fits`. That is the exact geometry the pixels
    were reprojected onto, so consuming it verbatim places the overlay at the right
    RA/Dec **and** orientation with no hand-rolled rotation-sign guesswork.

    The preview PNG is a uniform downscale of that canvas, so we return a WCS that
    maps *preview-pixel* coordinates to the same sky positions. For a linear WCS
    (world = CRVAL + M · (pixel − CRPIX)) the rescale is exact: with per-axis factors
    ``s_x = full_w/preview_w`` and ``s_y = full_h/preview_h``, the matrix columns
    scale by ``(s_x, s_y)`` and ``CRPIX → (CRPIX − 0.5)/s + 0.5`` (the FITS 1-based
    pixel-centre convention PIL's area resampling also uses). Returns a dict of FITS
    keywords in the same shape :func:`webapp.routers.sky._tan_wcs` produces, or
    ``None`` when the master FITS is missing/headerless/carries no celestial WCS (the
    caller then falls back to the frame-0 extrapolation).
    """
    if preview_w <= 0 or preview_h <= 0:
        return None
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        s_x = full_w / preview_w
        s_y = full_h / preview_h
        m = wcs.pixel_scale_matrix  # 2×2 CD matrix (deg/px), includes sign + rotation
        cd = m.copy()
        cd[:, 0] *= s_x
        cd[:, 1] *= s_y
        crpix = wcs.wcs.crpix
        crval = wcs.wcs.crval
        ctype = list(wcs.wcs.ctype)
        return {
            "NAXIS": 2, "NAXIS1": int(preview_w), "NAXIS2": int(preview_h),
            "CTYPE1": ctype[0], "CTYPE2": ctype[1],
            "CRPIX1": (float(crpix[0]) - 0.5) / s_x + 0.5,
            "CRPIX2": (float(crpix[1]) - 0.5) / s_y + 0.5,
            "CRVAL1": float(crval[0]), "CRVAL2": float(crval[1]),
            "CD1_1": float(cd[0, 0]), "CD1_2": float(cd[0, 1]),
            "CD2_1": float(cd[1, 0]), "CD2_2": float(cd[1, 1]),
        }
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "fall back"
        log.warning("WCS rescale to preview failed (%s): %s", fits_path, exc)
        return None


def _extent_from_scale_matrix(
    m, full_w: int, full_h: int,
) -> tuple[float, float, float]:
    """(width_deg, height_deg, rotation_deg) from a 2×2 CD/scale matrix + dims.

    ``m[i][j]`` is ``∂world_i/∂pixel_j`` (astropy's ``wcs.pixel_scale_matrix``
    layout, deg/px): column 0 is the RA/Dec change per x-pixel, column 1 per
    y-pixel. The angular size along each pixel axis is that column's magnitude,
    so ``width_deg = full_w · |col_x|`` and ``height_deg = full_h · |col_y|``.

    The position angle is recovered from the second row as
    ``atan2(-CD2_1, CD2_2)`` — the inverse of the FITS-standard CROTA2→CD
    relation for the RA-flipped convention (CDELT1 < 0). For a single-frame
    canvas (whose stored WCS *is* the reference frame's solved WCS) this returns
    exactly the ``CROTA2`` the frame's ``rotation_deg`` carried, so the built-in
    3D viewer is unchanged there; for a mosaic it returns the *union canvas*
    rotation instead of frame 0's extrapolation.
    """
    cd11, cd21 = float(m[0][0]), float(m[1][0])   # column 0 (per x-pixel)
    cd12, cd22 = float(m[0][1]), float(m[1][1])   # column 1 (per y-pixel)
    width_deg = full_w * math.hypot(cd11, cd21)
    height_deg = full_h * math.hypot(cd12, cd22)
    rotation_deg = math.degrees(math.atan2(-cd21, cd22))
    return width_deg, height_deg, rotation_deg


def canvas_extent_from_fits(
    fits_path: str | Path,
) -> tuple[float, float, float] | None:
    """A stack canvas's on-sky (width_deg, height_deg, rotation_deg) from its
    **stored** WCS, or ``None`` when the master FITS is missing/headerless.

    The stack master FITS carries the true canvas geometry (for a mosaic the
    astropy-built union-canvas WCS, for a single target the reference frame's own
    solved WCS). Deriving size + rotation from it places the built-in 3D viewer's
    tile on the *canvas* grid — mirroring what the Aladin overlay's ``wcs`` already
    does — instead of extrapolating from a single representative frame. Returns
    ``None`` (caller falls back to the frame-0 pixscale/rotation) when no
    celestial WCS is present. See :func:`_extent_from_scale_matrix`.
    """
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        return _extent_from_scale_matrix(wcs.pixel_scale_matrix, full_w, full_h)
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "fall back"
        log.warning("WCS extent from FITS failed (%s): %s", fits_path, exc)
        return None


def footprint_radec_deg(wcs, width_px: int, height_px: int) -> list[tuple[float, float]] | None:
    """
    Return the four corners of the frame in RA/Dec degrees, in image order
    (TL, TR, BR, BL). Useful for footprint plotting and mosaic detection.
    """
    if wcs is None:
        return None
    try:
        # pixel_to_world gives a SkyCoord; we want degrees as plain floats.
        corners_px = [(0, 0), (width_px - 1, 0), (width_px - 1, height_px - 1), (0, height_px - 1)]
        out: list[tuple[float, float]] = []
        for x, y in corners_px:
            sky = wcs.pixel_to_world(x, y)
            out.append((float(sky.ra.deg), float(sky.dec.deg)))
        return out
    except Exception:  # noqa: BLE001
        return None
