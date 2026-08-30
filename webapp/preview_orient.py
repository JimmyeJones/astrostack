"""What rotation a run's **stored preview bytes** actually carry.

History's "Adjust → North up → Save" overwrites a run's preview PNG with a
rotated render and records the angle on the run (``preview_north_up_deg``).
Everything that maps between those bytes and the sky — the Sky map's placement
and alpha, the share JPEG, the wallpaper crop, the baked scale bar and compass
rose — has to start from that angle, or it corrects for a turn that isn't there
(or fails to correct for one that is).

The column only exists from v0.288 onwards, and it is written **only** by that
save. So on an install upgraded onto this build, a preview someone saved
North-up *before* the column existed carries a rotation nobody recorded, and
every reader treats ``NULL`` as "not rotated" and misplaces it — until the day
somebody happens to re-save that run.

That is recoverable rather than guessable, because the save is the only thing
that ever rotates a stored preview and its angle is a deterministic function of
the run's own WCS. So a reader can **check**: work out the grid the preview
would sit on if it had never been turned, and believe a rotation only when the
stored PNG's dimensions are exactly what
:func:`~seestack.render.orient.north_up_pixel_transform` produces for that
angle. Anything that doesn't add up reads as un-rotated — which is precisely
what the code did before this module existed, so an unrecognised run is never
placed *more* wrongly than it already was.

Deliberately not detectable, and deliberately left reading as un-rotated:

* **An exact-180° save.** A half-turn leaves the dimensions alone, so there is
  nothing to measure. (A 90° save of a *square* canvas is the same case.)
* **A preview that is a crop of the canvas** (the one-click auto-edit ends its
  recipe with a border trim). Its size is neither grid, so the arithmetic can't
  speak; ``preview_crop_json`` says so and we stop.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _png_size(path: str) -> tuple[int, int] | None:
    """``(width, height)`` of a PNG from its header, without decoding pixels."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return int(im.width), int(im.height)
    except Exception:  # noqa: BLE001 — an unreadable preview simply can't be checked
        return None


def _flat_preview_size(run) -> tuple[int, int] | None:  # noqa: ANN001
    """The grid the run's preview sits on with no North-up turn applied.

    ``save_stack_preview`` renders through ``render_stack_png`` at
    :data:`~seestack.render.thumbnail.PREVIEW_MAX_WIDTH`, so the canvas
    dimensions give it exactly — and the run row already carries them, which
    keeps the common "nothing was rotated" answer free of any file read beyond
    the PNG's own header.
    """
    from seestack.render.thumbnail import preview_grid_size

    w, h = int(run.canvas_w or 0), int(run.canvas_h or 0)
    if w > 0 and h > 0:
        return preview_grid_size(w, h)
    return None


def recovered_north_up_deg(run) -> float:  # noqa: ANN001
    """The North-up rotation a run's stored preview carries but never recorded.

    ``0.0`` — today's behaviour — whenever it can't be established beyond
    arithmetic: no canvas dimensions, no master FITS, a cropped preview, an
    unreadable PNG, a canvas already close enough to North-up that the save
    would have been a no-op, or a stored size that isn't what rotating by that
    angle produces.
    """
    from seestack.previewcrop import parse_preview_crop

    if not run.preview_path or not run.fits_path:
        return 0.0
    if parse_preview_crop(run.preview_crop_json) is not None:
        return 0.0                       # a crop: neither grid explains its size
    flat = _flat_preview_size(run)
    stored = _png_size(run.preview_path)
    if flat is None or stored is None or stored == flat:
        return 0.0                       # untouched — the overwhelmingly common case

    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.render.orient import (
        NORTH_UP_MIN_DEG,
        north_up_pixel_transform,
        north_up_rotation_deg,
    )

    try:
        wcs, _full_w, _full_h = celestial_wcs_from_fits(run.fits_path)
    except Exception:  # noqa: BLE001 — an unreadable master can't answer
        return 0.0
    angle = north_up_rotation_deg(wcs, flat[0], flat[1])
    if angle is None or abs(angle) < NORTH_UP_MIN_DEG:
        # The option was never offered for this run, so nothing baked it in.
        return 0.0
    transform = north_up_pixel_transform(flat[0], flat[1], angle)
    if transform is None:
        return 0.0
    _m, _t, new_w, new_h = transform
    if (new_w, new_h) == flat:
        return 0.0                       # a half-turn: indistinguishable, so no claim
    if (new_w, new_h) != stored:
        return 0.0                       # some other render; don't invent a rotation
    log.debug("recovered an unrecorded North-up save on run %s: %.2f°",
              getattr(run, "id", "?"), angle)
    return float(angle)


def remaining_north_up_deg(run) -> float:  # noqa: ANN001
    """How far a ``?north_up=true`` render would **still** turn this run's stored
    preview — ``0.0`` when asking for North up would hand back what is already on
    screen.

    Not the same question as :func:`~seestack.render.thumbnail.applied_north_up_deg`,
    which answers "how far is this run's *data* from North up?". Every renderer
    that turns the stored bytes passes :func:`baked_north_up_deg` as
    ``already_deg`` and applies only the remainder, so on a run whose preview a
    past "Adjust → North up → Save" already turned, the honest answer is zero
    however far its WCS is from North. A surface deciding whether to *offer* the
    turn needs this one, or it puts up a control that visibly does nothing.

    Mirrors :func:`~seestack.render.thumbnail.orient_preview_north_up`'s own
    arithmetic rather than re-deriving it: the run's total correction, minus what
    the bytes carry, thresholded — with no usable WCS (or no master FITS to read
    one from) reading as "nothing to do", exactly as that renderer does.
    """
    if not run.fits_path:
        return 0.0
    from seestack.render.orient import NORTH_UP_MIN_DEG
    from seestack.render.thumbnail import applied_north_up_deg

    try:
        total = applied_north_up_deg(run.fits_path)
    except Exception:  # noqa: BLE001 — an unreadable master simply offers nothing
        return 0.0
    remaining = total - baked_north_up_deg(run)
    return remaining if abs(remaining) >= NORTH_UP_MIN_DEG else 0.0


def baked_north_up_deg(run) -> float:  # noqa: ANN001
    """The rotation a run's stored preview bytes carry, recorded or recovered.

    The recorded angle wins outright whenever there is one — including an
    explicit ``0.0``, which is a positive statement that the bytes are on the
    canvas grid (the one-click auto-edit writes it after rewriting a preview an
    older save had turned). Only a ``NULL`` — a run from before the column
    existed, or one no save has ever touched — falls through to the check.
    """
    recorded = getattr(run, "preview_north_up_deg", None)
    if recorded is not None:
        return float(recorded)
    return recovered_north_up_deg(run)
