"""
FITS loading and RGGB debayering for Seestar raw subs.

Seestar raws are single-extension FITS, BITPIX=16 (unsigned via BZERO=32768),
with a Bayer mosaic in the data array and an ``BAYERPAT`` header (usually 'RGGB').

We keep this module focused on *loading* — no QC, no warping. The output of
``load_seestar_raw`` is either:
  - the raw 2D Bayer array (default, what the QC pipeline wants — star detection
    works fine on the green channel via the mosaic), or
  - a debayered (H, W, 3) float32 image (when ``debayer=True``, what the
    thumbnail / preview wants).

The bilinear debayer here is deliberately simple and pure-numpy. It's good enough
for previews and stacking — better demosaicers (VNG, AHD) cost a lot more time
for a marginal quality gain on 10s subs that are going to be stacked anyway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class FitsHeaderInfo:
    """Subset of FITS header values we care about."""

    timestamp_utc: str | None
    exposure_s: float | None
    gain: float | None
    sensor_temp_c: float | None
    width_px: int
    height_px: int
    bayer_pattern: str | None  # 'RGGB' / 'BGGR' / 'GRBG' / 'GBRG'
    # Telescope target the mount was pointed at (degrees), read from the raw
    # header. Used as a plate-solve search hint; None if the header lacks it.
    ra_target_deg: float | None
    dec_target_deg: float | None
    raw_header: dict[str, Any]


def _first_image_hdu(hdul):
    """The first HDU that carries a ≥2D image array, or ``None``.

    Seestar raws put the mosaic in the primary HDU, but a compressed
    (``CompImageHDU``) or multi-extension FITS keeps an empty primary HDU and
    the image in a later extension. Selecting the first data-bearing HDU lets us
    read those too — and, crucially, avoids crashing on the empty primary (an
    ``IndexError`` from ``None.shape[-1]``) before the clear "expected 2D" error
    can fire. ``.shape`` is read without forcing decompression of the pixels.
    """
    for hdu in hdul:
        shape = getattr(hdu, "shape", None)
        if shape is not None and len(shape) >= 2:
            return hdu
    return None


def load_header(path: str | Path) -> FitsHeaderInfo:
    """Read just the FITS header — fast, no pixel data."""
    from astropy.io import fits

    path = Path(path)
    with fits.open(path, memmap=True) as hdul:
        hdu = _first_image_hdu(hdul)
        if hdu is None:
            h = hdul[0].header
            data_shape: tuple = ()
        else:
            h = hdu.header
            data_shape = hdu.shape  # (H, W) for 2D raw

    height, width = (data_shape[-2], data_shape[-1]) if len(data_shape) >= 2 else (0, 0)
    return FitsHeaderInfo(
        timestamp_utc=_parse_timestamp(h),
        exposure_s=_get_float(h, ("EXPTIME", "EXPOSURE")),
        gain=_get_float(h, ("GAIN",)),
        sensor_temp_c=_get_float(h, ("CCD-TEMP", "TEMP", "SET-TEMP")),
        width_px=int(width),
        height_px=int(height),
        bayer_pattern=_get_str(h, ("BAYERPAT", "BAYRPAT")),
        ra_target_deg=_target_ra_deg(h),
        dec_target_deg=_target_dec_deg(h),
        raw_header=dict(h),
    )


def load_seestar_raw(
    path: str | Path,
    *,
    debayer: bool = False,
    out_dtype: np.dtype | type = np.float32,
) -> tuple[np.ndarray, FitsHeaderInfo]:
    """
    Load a Seestar FITS file.

    Parameters
    ----------
    path
        Path to the FITS file (local or UNC).
    debayer
        If True, return an (H, W, 3) RGB float array. Otherwise return the raw
        2D Bayer mosaic.
    out_dtype
        dtype of the returned image. float32 is the right default — debayered
        outputs need to be float, and float32 matches what the rest of the
        pipeline uses.

    Returns
    -------
    image, header_info
    """
    from astropy.io import fits

    path = Path(path)
    with fits.open(path, memmap=False) as hdul:
        hdu = _first_image_hdu(hdul)
        if hdu is None:
            raise ValueError("no image data found in FITS (expected a 2D Bayer array)")
        data = np.asarray(hdu.data)
        h = hdu.header
        info = FitsHeaderInfo(
            timestamp_utc=_parse_timestamp(h),
            exposure_s=_get_float(h, ("EXPTIME", "EXPOSURE")),
            gain=_get_float(h, ("GAIN",)),
            sensor_temp_c=_get_float(h, ("CCD-TEMP", "TEMP", "SET-TEMP")),
            width_px=int(data.shape[-1]),
            height_px=int(data.shape[-2]),
            bayer_pattern=_get_str(h, ("BAYERPAT", "BAYRPAT")),
            ra_target_deg=_target_ra_deg(h),
            dec_target_deg=_target_dec_deg(h),
            raw_header=dict(h),
        )

    if data.ndim != 2:
        raise ValueError(f"expected 2D Bayer array, got shape {data.shape}")

    img = data.astype(out_dtype, copy=False)

    if debayer:
        pattern = (info.bayer_pattern or "RGGB").upper()
        img = bilinear_debayer(img, pattern=pattern)

    return img, info


# ---- debayer ------------------------------------------------------------


def bilinear_debayer(mosaic: np.ndarray, pattern: str = "RGGB") -> np.ndarray:
    """
    Bilinear RGGB-style debayering, pure numpy.

    Parameters
    ----------
    mosaic
        2D array (H, W) of the raw Bayer mosaic. H and W must be even.
    pattern
        One of 'RGGB', 'BGGR', 'GRBG', 'GBRG'. The Seestar uses 'RGGB'.

    Returns
    -------
    rgb
        3D array (H, W, 3), same dtype as input.
    """
    if mosaic.ndim != 2:
        raise ValueError("mosaic must be 2D")
    h, w = mosaic.shape
    if h % 2 or w % 2:
        # Pad by one to keep math simple; we crop back at the end.
        pad_h = h % 2
        pad_w = w % 2
        mosaic = np.pad(mosaic, ((0, pad_h), (0, pad_w)), mode="edge")
        h, w = mosaic.shape
        crop = (pad_h, pad_w)
    else:
        crop = (0, 0)

    # Build R, G, B planes, zero where the pixel doesn't belong to that channel.
    r = np.zeros_like(mosaic)
    g = np.zeros_like(mosaic)
    b = np.zeros_like(mosaic)

    pattern = pattern.upper()
    # 2x2 layout: top-left, top-right, bottom-left, bottom-right
    layouts = {
        "RGGB": (("r", "g"), ("g", "b")),
        "BGGR": (("b", "g"), ("g", "r")),
        "GRBG": (("g", "r"), ("b", "g")),
        "GBRG": (("g", "b"), ("r", "g")),
    }
    if pattern not in layouts:
        raise ValueError(f"unsupported bayer pattern {pattern!r}")
    (tl, tr), (bl, br) = layouts[pattern]
    plane = {"r": r, "g": g, "b": b}
    plane[tl][0::2, 0::2] = mosaic[0::2, 0::2]
    plane[tr][0::2, 1::2] = mosaic[0::2, 1::2]
    plane[bl][1::2, 0::2] = mosaic[1::2, 0::2]
    plane[br][1::2, 1::2] = mosaic[1::2, 1::2]

    # Bilinear interpolation for the missing values in each plane.
    # R and B have a 50% sparse grid — interpolate from 4 nearest neighbours.
    # G has a 50% checkerboard — interpolate from 4 cross neighbours.
    r_full = _interp_rb(r, layouts[pattern], "r")
    b_full = _interp_rb(b, layouts[pattern], "b")
    g_full = _interp_g(g)

    rgb = np.stack([r_full, g_full, b_full], axis=-1)

    if crop != (0, 0):
        rgb = rgb[: rgb.shape[0] - crop[0], : rgb.shape[1] - crop[1], :]
    return rgb


def _shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Shift by (dy, dx) with **zero fill** at the vacated edge.

    Matches ``np.roll``'s element mapping (``out[i] = a[i - dy]``) but *drops*
    the wrapped-around samples instead of replicating or wrapping them. ``np.roll``
    wrapped the opposite sensor edge into the bilinear-debayer neighbour average,
    contaminating the outermost pixel ring of every frame; edge replication (the
    previous fix) was no better here, because the colour planes are *sparse* (zero
    at every non-sample site), so replicating the border replicated a **zero line**
    and a genuine edge sample got averaged against 0 — darkening the outermost ring
    ~50% on edges and ~75% at the corners. Zero fill instead lets the interpolators
    (which divide by a same-channel sample *count*, not a fixed factor) simply
    exclude any contributor that falls off the frame, so the border averages only
    real in-frame samples. The align path insets 3 px so it never showed there, but
    the drizzle path stacks the full frame, so its results acquired a dark seam."""
    h, w = a.shape[:2]
    pad = [(max(dy, 0), max(-dy, 0)), (max(dx, 0), max(-dx, 0))]
    if a.ndim == 3:
        pad.append((0, 0))
    padded = np.pad(a, pad, mode="constant")
    y0, x0 = max(-dy, 0), max(-dx, 0)
    return padded[y0:y0 + h, x0:x0 + w]


def _interp_g(g_plane: np.ndarray) -> np.ndarray:
    """
    Fill the missing G samples (R and B sites) by averaging the 4 cross
    neighbours of each missing site.

    Uses *normalized convolution*: the average divides by how many of the 4 cross
    neighbours are genuine in-frame G samples, not a fixed 4, so a missing site on
    the frame edge (with a neighbour off the frame) averages only its real
    neighbours instead of being pulled toward 0 by the zero-filled off-frame
    contributor. Interior sites (all 4 neighbours present) are byte-for-byte
    unchanged.
    """
    has_g = g_plane != 0
    m = has_g.astype(np.float32)
    # Sum of the 4 cross neighbours' values, and a matching count of how many were
    # real in-frame samples (off-frame contributors are zero-filled in both).
    num = _shift(g_plane, 1, 0) + _shift(g_plane, -1, 0) \
        + _shift(g_plane, 0, 1) + _shift(g_plane, 0, -1)
    den = _shift(m, 1, 0) + _shift(m, -1, 0) + _shift(m, 0, 1) + _shift(m, 0, -1)
    avg = num / np.maximum(den, 1.0)
    return np.where(has_g, g_plane, avg)


def _interp_rb(plane: np.ndarray, layout: tuple, channel: str) -> np.ndarray:
    """
    Fill R or B plane.

    R (or B) is present on a 2x2 grid; each missing site falls into one of three
    cases that need different interpolations because **only same-channel
    neighbours are valid samples**:

      * Same row as samples, missing column → average horizontal neighbours.
      * Same column as samples, missing row → average vertical neighbours.
      * Both row and column missing → average four diagonal neighbours.

    A naive average of all four axial neighbours (h+v+...)/4 is wrong: half of
    those neighbours are zeros (the wrong-channel sites in the plane). Each average
    is *normalized* by the count of genuine in-frame samples it summed (not a fixed
    0.5/0.25), so a site on the frame edge whose neighbour falls off the frame
    averages only the real in-frame sample(s) rather than being darkened toward 0
    by the zero-filled off-frame contributor. Interior sites are unchanged.
    """
    has = plane != 0
    m = has.astype(np.float32)
    h_avg = ((_shift(plane, 0, 1) + _shift(plane, 0, -1))
             / np.maximum(_shift(m, 0, 1) + _shift(m, 0, -1), 1.0))
    v_avg = ((_shift(plane, 1, 0) + _shift(plane, -1, 0))
             / np.maximum(_shift(m, 1, 0) + _shift(m, -1, 0), 1.0))
    d_num = (_shift(plane, 1, 1) + _shift(plane, 1, -1)
             + _shift(plane, -1, 1) + _shift(plane, -1, -1))
    d_den = (_shift(m, 1, 1) + _shift(m, 1, -1)
             + _shift(m, -1, 1) + _shift(m, -1, -1))
    d_avg = d_num / np.maximum(d_den, 1.0)

    h, w = plane.shape
    yy, xx = np.indices((h, w))
    (tl, tr), (bl, br) = layout
    if channel == tl:
        py, px = 0, 0
    elif channel == tr:
        py, px = 0, 1
    elif channel == bl:
        py, px = 1, 0
    elif channel == br:
        py, px = 1, 1
    else:
        # Channel not in this layout (shouldn't happen for R/B in any RGGB-family
        # pattern). Return as-is.
        return plane
    on_sample_row = (yy % 2) == py
    on_sample_col = (xx % 2) == px
    out = plane.copy()
    # Same row, different col → horizontal interp.
    out = np.where(~has & on_sample_row & ~on_sample_col, h_avg, out)
    # Same col, different row → vertical interp.
    out = np.where(~has & ~on_sample_row & on_sample_col, v_avg, out)
    # Both different → diagonal.
    out = np.where(~has & ~on_sample_row & ~on_sample_col, d_avg, out)
    return out


# ---- header helpers -----------------------------------------------------


def _get_float(h, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        if k in h:
            try:
                return float(h[k])
            except (TypeError, ValueError):
                pass
    return None


def _get_str(h, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if k in h:
            try:
                return str(h[k]).strip()
            except Exception:  # noqa: BLE001
                pass
    return None


def _coord_to_deg(value, *, is_ra: bool) -> float | None:
    """Parse a FITS coordinate value to degrees.

    Decimal values (e.g. ``RA = 83.6``) are treated as degrees. Sexagesimal
    *strings* (e.g. ``OBJCTRA = '05 35 17.3'``) are parsed — RA in hours
    (→ ×15), Dec in degrees. Out-of-range results are rejected.
    """
    import re

    if value is None:
        return None
    try:
        deg = float(value)  # plain decimal (number or numeric string) → degrees
    except (TypeError, ValueError):
        s = str(value).strip()
        parts = [p for p in re.split(r"[\s:]+", s.lstrip("+")) if p not in ("", "-")]
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if not nums:
            return None
        mag = abs(nums[0]) + (nums[1] / 60 if len(nums) > 1 else 0) \
            + (nums[2] / 3600 if len(nums) > 2 else 0)
        deg = -mag if s.startswith("-") else mag
        if is_ra:
            deg *= 15.0  # sexagesimal RA is in hours
    if is_ra:
        return deg if 0.0 <= deg <= 360.0 else None
    return deg if -90.0 <= deg <= 90.0 else None


def _target_ra_deg(h) -> float | None:
    for k in ("OBJCTRA", "RA", "CRVAL1"):
        if k in h:
            deg = _coord_to_deg(h[k], is_ra=True)
            if deg is not None:
                return deg
    return None


def _target_dec_deg(h) -> float | None:
    for k in ("OBJCTDEC", "OBJCTDE", "DEC", "CRVAL2"):
        if k in h:
            deg = _coord_to_deg(h[k], is_ra=False)
            if deg is not None:
                return deg
    return None


def _parse_timestamp(h) -> str | None:
    """
    Return an ISO-8601 UTC timestamp string, or None.

    Seestar uses ``DATE-OBS`` like '2024-09-12T03:14:55.123'. We normalise to
    timezone-aware UTC ISO format for consistent storage.
    """
    raw = _get_str(h, ("DATE-OBS", "DATE_OBS"))
    if not raw:
        return None
    # Try a few common formats.
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return raw  # fall back to whatever the header had
