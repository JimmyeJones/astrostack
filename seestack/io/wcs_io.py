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


# --- the plain-TAN fast path (see `_wcs_from_plain_tan_text`) --------------
#
# Keywords that carry no WCS meaning at all, so the fast path may skip them.
_FAST_IGNORED_KEYS = frozenset({
    "SIMPLE", "BITPIX", "NAXIS", "EXTEND", "COMMENT", "HISTORY", "END", "",
})
# The image dimensions: not part of the transform, but `WCS(header)` records
# them as ``pixel_shape``, so the fast path must too.
_FAST_DIM_KEYS = frozenset({"NAXIS1", "NAXIS2"})
# Every keyword the fast path knows how to reproduce. A header carrying
# *anything* else — SIP (`A_ORDER`), `PV` distortion, a third axis, a
# `HIERARCH` card — is handed to astropy instead, so an unrecognised keyword
# can never be silently dropped from the transform.
_FAST_WCS_KEYS = frozenset({
    "WCSAXES", "CTYPE1", "CTYPE2", "CUNIT1", "CUNIT2",
    "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CDELT1", "CDELT2",
    "CROTA1", "CROTA2", "CD1_1", "CD1_2", "CD2_1", "CD2_2",
    "PC1_1", "PC1_2", "PC2_1", "PC2_2",
    "LONPOLE", "LATPOLE", "RADESYS", "EQUINOX", "MJDREF", "MJD-OBS", "DATE-OBS",
})


def _parse_fixed_format_cards(text: str):
    """Split FITS header text into ``(wcs_values, dimensions)``, or ``None``.

    A hand-rolled 80-column card scan, because `astropy.io.fits.Header` is the
    expensive half of the read (see :func:`wcs_from_text`): both building it and
    every subsequent ``key in header`` lookup re-verify cards. We only ever need
    a couple of dozen well-known keywords whose values are a float or a short
    quoted string.

    Returns ``None`` — meaning "hand this to astropy" — for anything at all
    unusual: a length that isn't a whole number of cards, a keyword outside
    :data:`_FAST_WCS_KEYS`, a duplicated keyword, a card with no ``= `` value
    indicator, or a value that doesn't parse. Being *conservative* here is what
    makes the fast path safe; it costs a slow parse on the rare header.
    """
    if len(text) % 80:
        return None
    values: dict[str, float | str] = {}
    dims: dict[str, float] = {}
    for i in range(0, len(text), 80):
        card = text[i:i + 80]
        keyword = card[:8].rstrip()
        if keyword == "END":
            break
        if keyword in _FAST_IGNORED_KEYS:
            continue
        if card[8:10] != "= ":
            return None
        if keyword in _FAST_DIM_KEYS:
            target: dict = dims
        elif keyword in _FAST_WCS_KEYS:
            target = values
        else:
            return None
        if keyword in target:
            return None  # a duplicated keyword: let astropy decide which wins
        field = card[10:]
        if field.lstrip().startswith("'"):
            quoted = field.lstrip()
            end = quoted.find("'", 1)
            if end < 0:
                return None
            target[keyword] = quoted[1:end].strip()
            continue
        token = field.split("/", 1)[0].strip()
        try:
            target[keyword] = float(token)
        except ValueError:
            return None
    return values, dims


def _wcs_from_plain_tan_text(text: str):
    """A WCS built by assignment, for the plain equatorial-TAN headers this app
    stores — or ``None`` when the header is anything else.

    ``WCS(Header.fromstring(text))`` costs **0.85–1.05 ms** a frame, almost all
    of it card verification rather than the projection maths, and
    :func:`seestack.stack.mosaic.compute_mosaic_canvas` reads one WCS per *sub*
    — so on the §1 owner's 5,477-sub target that is ~4.1 s of the 4.75 s a
    canvas computation takes, paid again by `/stack-estimate` on every Stack-page
    load and by `/rejection-outlook` on every Target-page load. Assigning the
    keywords onto a bare ``WCS(naxis=2)`` is **0.07 ms** — 12× cheaper — and
    produces a WCS that is *byte-identical* through ``to_header(relax=True)``,
    which is the equality the tests pin (a stronger bar than agreeing on a
    pixel grid, and the one that matters because `solve.bootstrap.propagate_wcs`
    re-serialises what it reads back).

    The rotation conventions are **not** re-implemented: ``CROTA`` is handed to
    wcslib via ``wcs.crota`` exactly as the header path does, and a header
    carrying ``CD`` keeps them (wcslib ignores ``CROTA``/``CDELT`` when ``CD`` is
    present — verified, not assumed). Anything outside the plain case — SIP or
    ``PV`` distortion, a non-TAN or non-equatorial projection, more than two
    axes, units that aren't degrees — returns ``None`` so the caller falls back
    to astropy's full, permissive read.
    """
    parsed = _parse_fixed_format_cards(text)
    if parsed is None:
        return None
    values, dims = parsed
    if values.get("WCSAXES", 2.0) != 2.0:
        return None
    if values.get("CTYPE1") != "RA---TAN" or values.get("CTYPE2") != "DEC--TAN":
        return None
    if any(k not in values for k in ("CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2")):
        return None
    if values.get("CUNIT1", "deg") != "deg" or values.get("CUNIT2", "deg") != "deg":
        return None

    import numpy as np
    from astropy.wcs import WCS

    wcs = WCS(naxis=2)
    prm = wcs.wcs
    prm.ctype = ["RA---TAN", "DEC--TAN"]
    prm.cunit = ["deg", "deg"]
    prm.crpix = [values["CRPIX1"], values["CRPIX2"]]
    prm.crval = [values["CRVAL1"], values["CRVAL2"]]
    if any(k in values for k in ("CD1_1", "CD1_2", "CD2_1", "CD2_2")):
        prm.cd = np.array(
            [[values.get("CD1_1", 0.0), values.get("CD1_2", 0.0)],
             [values.get("CD2_1", 0.0), values.get("CD2_2", 0.0)]], dtype=float)
    else:
        prm.cdelt = [values.get("CDELT1", 1.0), values.get("CDELT2", 1.0)]
        if any(k in values for k in ("PC1_1", "PC1_2", "PC2_1", "PC2_2")):
            prm.pc = np.array(
                [[values.get("PC1_1", 1.0), values.get("PC1_2", 0.0)],
                 [values.get("PC2_1", 0.0), values.get("PC2_2", 1.0)]], dtype=float)
        if "CROTA1" in values or "CROTA2" in values:
            prm.crota = [values.get("CROTA1", 0.0), values.get("CROTA2", 0.0)]
    for keyword, attr in (("LONPOLE", "lonpole"), ("LATPOLE", "latpole"),
                          ("EQUINOX", "equinox"), ("MJD-OBS", "mjdobs")):
        if keyword in values:
            setattr(prm, attr, values[keyword])
    if "MJDREF" in values:
        prm.mjdref = [values["MJDREF"], 0.0]
    if "RADESYS" in values:
        prm.radesys = str(values["RADESYS"])
    if "DATE-OBS" in values:
        prm.dateobs = str(values["DATE-OBS"])
    try:
        prm.set()
    except Exception:  # noqa: BLE001 — a header we can't set up goes the slow way
        return None
    if "NAXIS1" in dims and "NAXIS2" in dims:
        wcs.pixel_shape = (int(dims["NAXIS1"]), int(dims["NAXIS2"]))
    return wcs


def wcs_from_text(text: str | None):
    """Reconstruct a WCS from a stored text blob. Returns None on failure.

    Takes :func:`_wcs_from_plain_tan_text`'s fast path for the plain equatorial
    TAN headers this app stores (every ASTAP solve and everything
    :func:`wcs_to_text` writes), and astropy's full read for anything else —
    including a blob with no WCS keys at all, which still yields a
    ``has_celestial=False`` WCS rather than ``None`` (see
    :func:`wcs_text_is_usable`, which depends on that).
    """
    if not text:
        return None
    import warnings

    from astropy.io.fits import Header
    from astropy.wcs import FITSFixedWarning, WCS

    try:
        fast = _wcs_from_plain_tan_text(text)
        if fast is not None:
            return fast
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


def wcs_image_center_deg_from_text(
    text: str | None, *, width: int, height: int,
) -> tuple[float, float] | None:
    """The RA/Dec (deg) of a ``width``×``height`` image's **centre pixel**, from
    its own WCS — the honest centre when CRPIX is *not* at the image centre.

    :func:`wcs_center_deg_from_text` reads CRVAL, which is the frame centre only
    under ASTAP's own convention of putting CRPIX there. A WCS built by *offsetting
    CRPIX* — which is exactly what :func:`seestack.solve.bootstrap.propagate_wcs`
    does to give each rescued sub its own solution — deliberately keeps the
    reference frame's CRVAL, so CRVAL is then the *reference* sub's centre, not
    this one's. Reading it back as this frame's centre puts every rescued member's
    stored ``ra_center_deg``/``dec_center_deg`` at the reference's pointing, off by
    the registration shift (measured at Seestar scale: ~15″ at a 6 px shift, >10′
    near the 200 px registration cap).

    Uses ``all_pix2world`` so any SIP/distortion in the solution is honoured, and
    the 0-based array-centre convention ``((w−1)/2, (h−1)/2)``. Returns ``None``
    when the text carries no usable celestial solution or the projection can't be
    evaluated there.
    """
    wcs = wcs_from_text(text)
    if wcs is None or width <= 0 or height <= 0:
        return None
    try:
        cel = wcs.celestial
        if not cel.has_celestial:
            return None
        x = (float(width) - 1.0) / 2.0
        y = (float(height) - 1.0) / 2.0
        ra, dec = (float(v) for v in cel.all_pix2world([[x, y]], 0)[0])
        if not (math.isfinite(ra) and math.isfinite(dec)):
            return None
        return ra % 360.0, dec
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "no centre"
        log.warning("WCS image-centre extraction failed: %s", exc)
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


def wcs_text_from_raw(raw: str | None) -> str | None:
    """Normalise the raw contents of an ASTAP ``.wcs`` sidecar into header text.

    Split out from :func:`wcs_text_from_sidecar` so a caller that already holds
    the bytes can normalise them the same way — :meth:`ASTAPSolver.solve` reads
    its sidecars inside the scratch directory it solved in and hands back their
    content, because writing them next to the source would mean writing into the
    owner's read-only ``incoming/`` tree (``AGENTS.md`` §10).
    """
    if not raw:
        return None
    from astropy.io.fits import Header

    try:
        # The header is padded to multiples of 2880 bytes by FITS convention,
        # but astropy's ``Header.fromstring`` handles that gracefully.
        return str(Header.fromstring(raw))
    except Exception:  # noqa: BLE001
        return None


def wcs_text_from_sidecar(wcs_path: str | Path) -> str | None:
    """Read an ASTAP ``.wcs`` sidecar file and return its FITS header as text."""
    wcs_path = Path(wcs_path)
    if not wcs_path.exists():
        return None
    try:
        # ASTAP writes a tiny FITS header file (no data block).
        with open(wcs_path, "rb") as f:
            return wcs_text_from_raw(f.read().decode("ascii", errors="replace"))
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


def wcs_text_after_pixel_steps(wcs_text: str | None, steps) -> str | None:  # noqa: ANN001
    """Move a WCS onto a canvas that has been cropped and/or rescaled.

    ``steps`` is what :func:`seestack.edit.ops.geometry.geometry_pixel_steps`
    returns: ``("crop", x0, y0)`` and ``("resize", in_w, in_h, out_w, out_h)``
    entries, in the order they were applied. A crop is a pure translation of the
    reference pixel; a resize also rescales the pixel→world matrix, per axis,
    using the same corner-aligned sampling ``scipy.ndimage.zoom`` does
    (``x_in = x_out · (n_in − 1)/(n_out − 1)``).

    Returns ``None`` — "no WCS", never a guess — when the input has no usable
    solution, when a resize would invalidate SIP distortion coefficients (they
    are polynomials in *source* pixels; a crop only shifts their origin, which
    they are already expressed relative to, but a rescale does not), or when the
    header is too legacy to rewrite safely (``CROTA``).
    """
    if not wcs_text or not wcs_text_is_usable(wcs_text):
        return None
    steps = list(steps or [])
    if not steps:
        return wcs_text
    import warnings

    import numpy as np
    from astropy.io.fits import Header
    from astropy.wcs import WCS, FITSFixedWarning

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FITSFixedWarning)
            wcs = WCS(Header.fromstring(wcs_text)).celestial
        if not wcs.has_celestial or wcs.naxis != 2:
            return None
        resizes = [s for s in steps if s[0] == "resize"]
        if resizes and (wcs.sip is not None or wcs.wcs.has_crota()):
            return None
        crpix = [float(v) for v in wcs.wcs.crpix]
        fx_total, fy_total = 1.0, 1.0
        for step in steps:
            if step[0] == "crop":
                _, x0, y0 = step
                crpix[0] -= float(x0)
                crpix[1] -= float(y0)
            else:
                _, in_w, in_h, out_w, out_h = step
                fx = (in_w - 1.0) / (out_w - 1.0) if out_w > 1 else 1.0
                fy = (in_h - 1.0) / (out_h - 1.0) if out_h > 1 else 1.0
                if fx <= 0 or fy <= 0:
                    return None
                crpix[0] = (crpix[0] - 1.0) / fx + 1.0
                crpix[1] = (crpix[1] - 1.0) / fy + 1.0
                fx_total *= fx
                fy_total *= fy
        wcs.wcs.crpix = crpix
        if resizes:
            # Scale the *columns* of the linear transform — a column is one pixel
            # axis, and it is the pixel axes that changed length. (Scaling CDELT
            # would scale the world *rows* instead, which is only the same thing
            # when the two axis factors are equal and the matrix is diagonal.)
            if wcs.wcs.has_cd():
                m = np.array(wcs.wcs.cd, dtype=float, copy=True)
                m[:, 0] *= fx_total
                m[:, 1] *= fy_total
                wcs.wcs.cd = m
            else:
                pc = np.array(wcs.wcs.get_pc(), dtype=float, copy=True)
                pc[:, 0] *= fx_total
                pc[:, 1] *= fy_total
                wcs.wcs.pc = pc
        text = str(wcs.to_header(relax=True))
    except Exception as exc:  # noqa: BLE001 — a WCS we can't rewrite is dropped, not guessed
        log.warning("WCS geometry rewrite failed: %s", exc)
        return None
    return text if wcs_text_is_usable(text) else None


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


def arcsec_per_px(wcs) -> float | None:  # noqa: ANN001
    """The local plate scale (arcsec/px) of a stack's celestial WCS — the mean of
    the two axis scales, which is exact for the square, unrotated Seestar grid
    and a sane average for a mosaic canvas. ``None`` when there is no usable WCS
    or the scale can't be measured, so every caller can omit its answer cleanly
    rather than working from a made-up number.

    Lives here rather than beside any one caller because several surfaces ask the
    same question of the same header — the scale bar baked onto a share, the
    "did I frame it well?" verdict, the annotation overlay — and they must not
    drift into two definitions of the picture's scale."""
    if wcs is None:
        return None
    try:
        from astropy.wcs.utils import proj_plane_pixel_scales

        scales_deg = proj_plane_pixel_scales(wcs)  # deg/px per axis
        scale = float(sum(scales_deg) / len(scales_deg)) * 3600.0
    except Exception:  # noqa: BLE001 — a degenerate WCS just means "no answer"
        return None
    return scale if scale > 0 else None


def _crop_matrix_inputs(crop, crpix, full_w: int, full_h: int):
    """Shift a canvas WCS's reference pixel into a cropped rectangle and return
    the cropped dimensions — the "the stored preview shows only part of the
    canvas" composition, shared by the two preview helpers below.

    ``crop`` is a :class:`~seestack.previewcrop.PreviewCrop` (or ``None`` for the
    whole canvas, which is a no-op). A crop is a pure integer-pixel translation of
    the grid, so shifting ``CRPIX`` by the crop's origin is exact in either the
    0- or 1-based convention."""
    from seestack.previewcrop import crop_pixel_box

    if crop is None:
        return crpix, full_w, full_h
    x0, y0, x1, y1 = crop_pixel_box(crop, full_w, full_h)
    return ([float(crpix[0]) - x0, float(crpix[1]) - y0], x1 - x0, y1 - y0)


def wcs_dict_rescaled_to_preview(
    fits_path: str | Path, preview_w: int, preview_h: int,
    *, north_up_deg: float = 0.0, crop=None,  # noqa: ANN001 — PreviewCrop | None
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

    ``crop`` is the *other* way a stored preview stops being a plain downscale: the
    "Process target" auto-edit's border trim (:mod:`seestack.previewcrop`). Pass it
    and the canvas grid is cut to that rectangle before the rescale, so the tile is
    placed at the size **and centre** the cropped picture actually has instead of
    being stretched over the whole canvas footprint. ``None`` — every ordinary run
    — composes nothing.
    """
    if preview_w <= 0 or preview_h <= 0:
        return None
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        m = wcs.pixel_scale_matrix  # 2×2 CD matrix (deg/px), includes sign + rotation
        crpix, full_w, full_h = _crop_matrix_inputs(
            crop, wcs.wcs.crpix, full_w, full_h)
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
    fits_path: str | Path, *, north_up_deg: float = 0.0, crop=None,  # noqa: ANN001
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

    ``crop`` describes a stored preview the "Process target" auto-edit trimmed
    (:mod:`seestack.previewcrop`); pass it and the extent is that of the visible
    rectangle, so the tile isn't drawn stretched over the un-cropped footprint.
    ``None`` is the whole canvas exactly as before.
    """
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        m = wcs.pixel_scale_matrix
        crpix, full_w, full_h = _crop_matrix_inputs(
            crop, wcs.wcs.crpix, full_w, full_h)
        if north_up_deg:
            rotated = _rotate_matrix_and_crpix(
                m, crpix, full_w, full_h, north_up_deg)
            if rotated is None:
                return None
            m, _crpix, full_w, full_h = rotated
        return _extent_from_scale_matrix(m, full_w, full_h)
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "fall back"
        log.warning("WCS extent from FITS failed (%s): %s", fits_path, exc)
        return None


def cropped_center_radec_from_fits(fits_path: str | Path, crop
                                   ) -> tuple[float, float] | None:  # noqa: ANN001
    """Where the centre of a *cropped* stored preview sits on the sky.

    A tile is placed by its centre, and the Sky map uses the library target's own
    RA/Dec for that — fine while the picture is the whole canvas (the target is
    what the canvas was built around), wrong once the "Process target" auto-edit
    trims a ragged border off one side. Projects the crop rectangle's centre pixel
    through the canvas WCS instead. ``None`` (caller keeps the target position)
    when there's no crop or no usable celestial WCS. A rotation about the picture
    centre doesn't move it, so this needs no ``north_up_deg``."""
    from seestack.previewcrop import PreviewCrop, crop_pixel_box

    if not isinstance(crop, PreviewCrop):
        return None
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        x0, y0, x1, y1 = crop_pixel_box(crop, full_w, full_h)
        ra, dec = wcs.all_pix2world((x0 + x1 - 1) / 2.0, (y0 + y1 - 1) / 2.0, 0)
        ra, dec = float(ra), float(dec)
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "fall back"
        log.warning("Cropped centre from FITS failed (%s): %s", fits_path, exc)
        return None
    if ra != ra or dec != dec:  # NaN
        return None
    return (ra, dec)


def _is_plain_radec(wcs) -> bool:
    """True for a 2-axis WCS whose world axes are plainly RA then Dec.

    That is every WCS this app stores — ASTAP solves to ``RA---TAN``/``DEC--TAN``
    and :func:`wcs_to_text` round-trips it — and it is the precondition for
    reading :meth:`all_pix2world`'s output as ``(ra, dec)`` directly. A galactic
    (``GLON``/``GLAT``) or otherwise non-equatorial WCS would hand back
    longitude/latitude in the same two slots, which is why the caller below only
    takes the fast path when this holds.
    """
    try:
        ctype = list(wcs.wcs.ctype)
    except Exception:  # noqa: BLE001 — no wcs sub-object; not our fast path
        return False
    return (
        getattr(wcs, "naxis", 0) == 2
        and len(ctype) == 2
        and str(ctype[0]).upper().startswith("RA")
        and str(ctype[1]).upper().startswith("DEC")
    )


def footprint_radec_deg(wcs, width_px: int, height_px: int) -> list[tuple[float, float]] | None:
    """
    Return the four corners of the frame in RA/Dec degrees, in image order
    (TL, TR, BR, BL). Useful for footprint plotting and mosaic detection.

    **Transformed in one vectorised call, not four.** ``pixel_to_world`` builds a
    whole ``SkyCoord`` (frame + representation objects) per corner, which is
    ~1.3 ms a frame — and ``seestack.stack.mosaic.compute_mosaic_canvas`` calls
    this once per *sub*, so on the §1 owner's 5,477-sub target it was **9.1 s of
    the 13.9 s** one mosaic-canvas computation took, paid again by
    `/stack-estimate` and `/rejection-outlook` on every Stack- and Target-page
    load (measured: the same canvas now comes back in **4.8 s**).
    ``all_pix2world`` is the same transform ``pixel_to_world`` applies (distortions
    included) without the object wrapping: **0.011 ms**, and bit-identical on the
    equatorial WCSs this app stores. A WCS that is anything else keeps the
    original per-corner path, so nothing silently reads a galactic longitude as
    an RA.
    """
    if wcs is None:
        return None
    if _is_plain_radec(wcs):
        try:
            import numpy as np

            xs = np.array([0, width_px - 1, width_px - 1, 0], dtype=float)
            ys = np.array([0, 0, height_px - 1, height_px - 1], dtype=float)
            ra, dec = wcs.all_pix2world(xs, ys, 0)
            return [(float(a), float(d)) for a, d in zip(ra, dec, strict=True)]
        except Exception:  # noqa: BLE001 — fall through to the general path,
            pass           # which answers ``None`` for a frame with no size
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
