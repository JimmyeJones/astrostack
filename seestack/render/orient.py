"""Orient a rendered image so celestial North points up.

A Seestar frames the sky at whatever angle the mount happened to sit, so a
beginner's finished picture often comes out rotated relative to every catalog /
reference photo of the same object — which makes it look "off" and hard to
compare. The app already knows the exact orientation: the stacked master FITS
carries the output celestial WCS. This module turns that WCS into the rotation
that brings North to the top, and applies it to a display image.

Everything here is derived from the image's own WCS via ``astropy`` — we ask the
WCS "which way is North?" and rotate to match, rather than hand-rolling a
``CROTA``/``CD`` sign (the sign hazard the sky-atlas overlay is gated on). The
rotation direction is pinned by an end-to-end marker test that uses ``astropy``
itself as ground truth.
"""

from __future__ import annotations

import math

import numpy as np

#: Below this correction (degrees) the frame is already close enough to North-up
#: that rotating would only add interpolation blur and black corners for nothing,
#: so the option isn't offered / is a no-op.
NORTH_UP_MIN_DEG = 2.0

#: Within this many degrees of an exact 90° step we snap to it, so the common
#: near-orthogonal case is *lossless* (a pure transpose/flip — no resample, no new
#: black corners).
_SNAP_TOL_DEG = 1.0


def north_up_rotation_deg(wcs, width: int, height: int) -> float | None:
    """The counter-clockwise rotation (degrees, in PIL's ``Image.rotate`` sense)
    that brings celestial North to the top of the image.

    Asks the WCS where North (increasing Dec) points in pixel space at the image
    centre, then returns the angle that rotates that direction to screen-up.
    Returns ``None`` when there's no usable WCS or the geometry is degenerate
    (so the caller simply doesn't offer the option). The result is normalised to
    ``(-180, 180]``.
    """
    if wcs is None or width <= 0 or height <= 0:
        return None
    try:
        cx = (width - 1) / 2.0
        cy = (height - 1) / 2.0
        ra0, dec0 = (float(v) for v in wcs.all_pix2world(cx, cy, 0))
        # Step North by a small fraction of the field (but away from the poles).
        step_deg = 0.05
        dec1 = dec0 + step_deg
        if dec1 >= 90.0:
            dec1 = dec0 - step_deg  # near the N pole, step South and flip the vector
            flip = -1.0
        else:
            flip = 1.0
        nx, ny = (float(v) for v in wcs.all_world2pix(ra0, dec1, 0))
        dcol = (nx - cx) * flip
        drow = (ny - cy) * flip
        if not (math.isfinite(dcol) and math.isfinite(drow)):
            return None
        if abs(dcol) < 1e-9 and abs(drow) < 1e-9:
            return None
        # North's on-screen angle, measured CCW from +x with screen-up positive
        # (row increases downward, so up is −drow). Rotating the image CCW by β
        # sends that angle to θ+β; we want North at +90° (screen-up) → β = 90−θ.
        theta = math.degrees(math.atan2(-drow, dcol))
        beta = 90.0 - theta
        # Normalise to (-180, 180].
        beta = (beta + 180.0) % 360.0 - 180.0
        if beta == -180.0:
            beta = 180.0
        return beta
    except Exception:  # noqa: BLE001 — a degenerate WCS just means "can't orient"
        return None


def rotate_image_north_up(rgb: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate an ``(H, W, 3)`` display image CCW by ``angle_deg`` so North is up.

    Exposed corners fill with black — the same value uncovered/NaN pixels already
    render as — so the result looks intentional, not broken. When the angle is
    within ``_SNAP_TOL_DEG`` of a 90° multiple the rotation is done losslessly
    (transpose/flip, no resample); otherwise a bicubic rotate with ``expand`` keeps
    the whole frame. Input is assumed display-space (values in ``[0, 1]``, NaN
    already resolved); pass the stretched pixels, not the linear stack.
    """
    from PIL import Image

    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)

    # Snap near-orthogonal angles to an exact 90° step for a lossless rotate.
    snapped = round(angle_deg / 90.0) * 90.0
    k = int(snapped / 90.0) % 4
    if abs(angle_deg - snapped) <= _SNAP_TOL_DEG:
        # np.rot90 rotates CCW by k·90°, matching PIL.Image.rotate's CCW sense.
        return np.ascontiguousarray(np.rot90(arr, k=k))

    u8 = (np.clip(np.nan_to_num(arr), 0.0, 1.0) * 255.0).astype(np.uint8)
    img = Image.fromarray(u8, mode="RGB").rotate(
        angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0))
    return np.asarray(img, dtype=np.float32) / 255.0
