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


def applied_rotation_deg(angle_deg: float) -> float:
    """The rotation :func:`rotate_image_north_up` will *actually* apply.

    Near-orthogonal angles are snapped to an exact 90° step so the common case
    stays lossless, which leaves the pixels up to :data:`_SNAP_TOL_DEG` away
    from the requested angle. Anything that has to follow the pixels — the
    North/East rose baked on by :mod:`seestack.skymarks`, say — needs the angle
    that was applied, not the one that was asked for, so both read it here
    rather than each re-deriving the snap rule."""
    snapped = round(angle_deg / 90.0) * 90.0
    return snapped if abs(angle_deg - snapped) <= _SNAP_TOL_DEG else angle_deg


def north_up_pixel_transform(
    width: int, height: int, angle_deg: float,
) -> tuple[np.ndarray, np.ndarray, int, int] | None:
    """The exact pixel-grid geometry :func:`rotate_image_north_up` produces.

    Returns ``(M, t, new_w, new_h)`` where ``p_in = M @ p_out + t`` maps a pixel
    of the **rotated** image back to the pixel of the original it came from (both
    0-based ``(x, y)`` indices), and ``(new_w, new_h)`` is the rotated image's
    size. ``None`` for a degenerate size.

    Anything that has to follow the rotated pixels *analytically* — placing the
    rotated picture on the sky, say — needs this rather than re-deriving it, and
    the two rotation paths are genuinely different: the lossless ``np.rot90`` snap
    works in pixel-**centre** coordinates (``(n−1)/2``), while ``PIL.Image.rotate``
    with ``expand=True`` rotates about ``n/2`` and sizes the canvas from a
    ``ceil``/``floor`` bounding box. Both are replicated here exactly, so a caller
    is never half a pixel — or a whole flipped axis — out.
    """
    if width <= 0 or height <= 0:
        return None
    snapped = round(angle_deg / 90.0) * 90.0
    if abs(angle_deg - snapped) <= _SNAP_TOL_DEG:
        # np.rot90 CCW by k·90°, about the image's pixel-centre midpoint.
        k = int(snapped / 90.0) % 4
        alpha = math.radians(90.0 * k)
        m = np.array([[math.cos(alpha), -math.sin(alpha)],
                      [math.sin(alpha), math.cos(alpha)]], dtype=float)
        new_w, new_h = (height, width) if k % 2 else (width, height)
        c_in = np.array([(width - 1) / 2.0, (height - 1) / 2.0])
        c_out = np.array([(new_w - 1) / 2.0, (new_h - 1) / 2.0])
        return m, c_in - m @ c_out, int(new_w), int(new_h)

    # PIL.Image.rotate(angle, expand=True): an affine that maps *output* pixel
    # indices to input ones, built about (w/2, h/2), then re-centred on a
    # ceil/floor bounding box. Replicated statement-for-statement so the WCS a
    # caller derives lands on the same pixels the image actually has.
    alpha = math.radians(angle_deg)
    cos_a, sin_a = math.cos(alpha), math.sin(alpha)
    a, b, d, e = cos_a, -sin_a, sin_a, cos_a
    cx, cy = width / 2.0, height / 2.0
    c = -a * cx - b * cy + cx
    f = -d * cx - e * cy + cy
    xs, ys = [], []
    for x, y in ((0.0, 0.0), (width, 0.0), (width, height), (0.0, height)):
        xs.append(a * x + b * y + c)
        ys.append(d * x + e * y + f)
    new_w = int(math.ceil(max(xs)) - math.floor(min(xs)))
    new_h = int(math.ceil(max(ys)) - math.floor(min(ys)))
    shift_x, shift_y = -(new_w - width) / 2.0, -(new_h - height) / 2.0
    c, f = a * shift_x + b * shift_y + c, d * shift_x + e * shift_y + f
    # PIL's affine is evaluated on pixel *corners* (it maps output index → input
    # index and truncates), so re-expressing it centre-to-centre — which is what
    # a 1-based FITS CRPIX means by "pixel" — shifts it by half a pixel each way:
    # p_in + ½ = M·(p_out + ½) + (c, f). Measured: without this the derived
    # position is up to ~1.7 px out at 123°, with it the residual is pure
    # nearest-neighbour rounding.
    m = np.array([[a, b], [d, e]], dtype=float)
    half = np.array([0.5, 0.5])
    return m, np.array([c, f], dtype=float) + m @ half - half, new_w, new_h


def canvas_width_in_preview_px(
    canvas_w: int, canvas_h: int, preview_w: int, preview_h: int,
    angle_deg: float,
) -> float | None:
    """How many pixels of a *rotated* preview the stack canvas's **width** spans.

    A preview is normally a uniform downscale of the canvas, so its own width is
    that span — but History's "Adjust → North up → Save" rotates it with expand,
    after which the picture's width is a bounding box, not the canvas width. Any
    length held as a fraction of the canvas width — the scale bar's, which
    :func:`seestack.scalebar.scale_bar_for` measures against the FITS grid — has
    to be scaled by this instead, or the bar comes out wrong (on a 90° save it is
    drawn against the canvas's *height*).

    The canvas's own aspect is what makes this well-conditioned: the un-rotated
    preview is ``(canvas_w, canvas_h)`` over one unknown downscale ``k``, and
    ``preview_w = (canvas_w·|cos| + canvas_h·|sin|) / k`` pins it with no
    ill-conditioned inversion. Exact for the lossless snapped case (a pure axis
    swap); elsewhere right to within the expand box's own ``ceil``/``floor``
    pixel. ``None`` for a degenerate size, so the caller can keep the width it
    has rather than work from a made-up number.
    """
    if min(canvas_w, canvas_h, preview_w, preview_h) <= 0:
        return None
    snapped = round(angle_deg / 90.0) * 90.0
    if abs(angle_deg - snapped) <= _SNAP_TOL_DEG:
        # A quarter-turn swaps the axes, so the canvas width is the preview's
        # height; a half-turn (or none) leaves it as the preview's width.
        return float(preview_h if int(snapped / 90.0) % 2 else preview_w)
    alpha = math.radians(angle_deg)
    span = canvas_w * abs(math.cos(alpha)) + canvas_h * abs(math.sin(alpha))
    if span <= 0:
        return None
    return canvas_w * preview_w / span


def rotate_mask_north_up(mask: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate a boolean ``(H, W)`` mask exactly the way
    :func:`rotate_image_north_up` rotates the picture it belongs to.

    The Sky-map overlay keys a stored preview's alpha off the stack's coverage
    mask; when that preview was saved North-up the mask has to make the same
    journey or the transparent footprint lands somewhere the picture isn't.
    Exposed corners fill with ``False`` (uncovered), matching the black the
    picture's own corners fill with. Uses the same snap→``np.rot90`` /
    ``PIL``-rotate split, with nearest resampling so the result stays a hard
    1-bit footprint.
    """
    from PIL import Image

    arr = np.asarray(mask, dtype=bool)
    if arr.ndim != 2:
        raise ValueError("mask must be 2-D")

    snapped = round(angle_deg / 90.0) * 90.0
    if abs(angle_deg - snapped) <= _SNAP_TOL_DEG:
        return np.ascontiguousarray(np.rot90(arr, k=int(snapped / 90.0) % 4))

    img = Image.fromarray(arr.astype(np.uint8) * 255, mode="L").rotate(
        angle_deg, resample=Image.NEAREST, expand=True, fillcolor=0)
    return np.asarray(img, dtype=np.uint8) > 127


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

    # Snap near-orthogonal angles to an exact 90° step for a lossless rotate
    # (`applied_rotation_deg` states the same rule for callers that must follow
    # the pixels — keep the two in step).
    snapped = round(angle_deg / 90.0) * 90.0
    k = int(snapped / 90.0) % 4
    if abs(angle_deg - snapped) <= _SNAP_TOL_DEG:
        # np.rot90 rotates CCW by k·90°, matching PIL.Image.rotate's CCW sense.
        return np.ascontiguousarray(np.rot90(arr, k=k))

    u8 = (np.clip(np.nan_to_num(arr), 0.0, 1.0) * 255.0).astype(np.uint8)
    img = Image.fromarray(u8, mode="RGB").rotate(
        angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0))
    return np.asarray(img, dtype=np.float32) / 255.0
