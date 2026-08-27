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


def wcs_center_deg_from_text(text: str | None) -> tuple[float, float] | None:
    """The reference-point (CRVAL) RA/Dec in degrees from a stored WCS text blob.

    ASTAP writes its solution with the reference pixel (CRPIX) at the image
    centre, so CRVAL1/CRVAL2 are the frame's centre coordinates — the very values
    :func:`seestack.solve.astap._parse_astap_ini` reads from the ``.ini`` sidecar.
    This lets a solved frame's centre be recovered from the ``.wcs`` sidecar when
    the ``.ini`` is missing or unparseable, so the frame stays eligible as the
    stack reference and as a sibling plate-solve hint (both require a centre)
    rather than becoming a solved-but-centreless orphan. Returns ``None`` when the
    text carries no usable celestial reference point.
    """
    wcs = wcs_from_text(text)
    if wcs is None:
        return None
    try:
        cel = wcs.celestial
        if not cel.has_celestial:
            return None
        ra = float(cel.wcs.crval[0])
        dec = float(cel.wcs.crval[1])
        if not (math.isfinite(ra) and math.isfinite(dec)):
            return None
        return ra, dec
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "no centre"
        log.warning("WCS centre extraction failed: %s", exc)
        return None


def wcs_text_is_usable(text: str | None) -> bool:
    """True when a WCS text blob carries a usable celestial (RA/Dec) solution.

    ``wcs_from_text`` is deliberately permissive — it returns a WCS object for
    *any* parseable FITS header, including one with no WCS keys at all (an empty
    or truncated ASTAP ``.wcs`` sidecar reads as a bare ``"END"`` blob, which is
    a **truthy** string and a non-``None``, ``has_celestial=False`` WCS). So
    ``if wcs_text:`` / ``if wcs is None:`` are not enough to tell "solved" from
    "the sidecar was there but said nothing": use this instead anywhere a stored
    solution is about to be trusted (persisted, propagated, or reprojected
    through). A genuine solve always ends with a celestial reference point, so
    this rejects only the garbage case.
    """
    return wcs_center_deg_from_text(text) is not None


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


def _rotate_matrix_and_crpix(m, crpix, width: int, height: int, north_up_deg: float):  # noqa: ANN001,ANN202
    """Re-express a canvas's ``(CD, CRPIX, NAXIS)`` on the grid that
    :func:`seestack.render.orient.rotate_image_north_up` produces from it.

    Returns ``(cd, crpix, new_w, new_h)`` — or ``None`` when the rotation's pixel
    geometry is degenerate. The rotation maps rotated-image pixels back to
    original ones as ``p_in = M · p_out + t`` (0-based indices), so in FITS
    1-based terms ``p_in¹ = M · p_out¹ + t¹`` with ``t¹ = t + (1,1) − M·(1,1)``.
    Substituting into ``world = CD · (p¹ − CRPIX)`` gives ``CD′ = CD · M`` and
    ``CRPIX′ = M⁻¹ · (CRPIX − t¹)`` — exact for the linear part of the WCS, which
    is all a rigid rotation of the pixel grid can touch (``CRVAL``/``CTYPE`` are
    untouched, so the tangent point stays where it is).
    """
    import numpy as np

    from seestack.render.orient import north_up_pixel_transform

    xf = north_up_pixel_transform(width, height, north_up_deg)
    if xf is None:
        return None
    rot, t, new_w, new_h = xf
    one = np.array([1.0, 1.0])
    t1 = t + one - rot @ one
    cd = np.asarray(m, dtype=float) @ rot
    crpix_new = np.linalg.solve(rot, np.asarray(crpix, dtype=float) - t1)
    return cd, crpix_new, new_w, new_h


def wcs_dict_rescaled_to_preview(
    fits_path: str | Path, preview_w: int, preview_h: int,
    *, north_up_deg: float = 0.0,
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

    ``north_up_deg`` is for the one preview that is **not** a plain downscale of the
    canvas: History's "Adjust" can save the preview rotated so celestial North points
    up. Pass the rotation that was applied and the canvas WCS is rotated onto the same
    grid before the rescale, so the tile is placed at the orientation the stored
    picture actually has. (Rotation and a uniform downscale commute, so composing them
    in this order matches what the render did to within the sub-pixel rounding of the
    rotated canvas's bounding box.) The default ``0.0`` leaves every existing call
    bit-for-bit unchanged.
    """
    if preview_w <= 0 or preview_h <= 0:
        return None
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        m = wcs.pixel_scale_matrix  # 2×2 CD matrix (deg/px), includes sign + rotation
        crpix = wcs.wcs.crpix
        if north_up_deg:
            rotated = _rotate_matrix_and_crpix(m, crpix, full_w, full_h, north_up_deg)
            if rotated is None:
                return None
            m, crpix, full_w, full_h = rotated
        s_x = full_w / preview_w
        s_y = full_h / preview_h
        cd = m.copy()
        cd[:, 0] *= s_x
        cd[:, 1] *= s_y
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
    fits_path: str | Path, *, north_up_deg: float = 0.0,
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

    ``north_up_deg`` describes a stored preview that was saved rotated so North
    points up (History's "Adjust"); pass it and the extent describes that rotated
    grid instead — a bigger bounding box, and a position angle of ~0 because the
    picture now *is* North-up. The default ``0.0`` is the unrotated canvas exactly
    as before.
    """
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        m = wcs.pixel_scale_matrix
        if north_up_deg:
            rotated = _rotate_matrix_and_crpix(
                m, wcs.wcs.crpix, full_w, full_h, north_up_deg)
            if rotated is None:
                return None
            m, _crpix, full_w, full_h = rotated
        return _extent_from_scale_matrix(m, full_w, full_h)
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
