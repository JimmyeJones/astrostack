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

**…except on a run recorded before that column existed, which is the other half
of the same problem** (:func:`recovered_preview_crop`). ``preview_crop_json`` is
written by ``webapp.pipeline._preview_crop_json_for_recipe``, which postdates a
great many runs — the owner's library has it NULL on **all 614** while 42 of the
stored PNGs are demonstrably crops of their canvas (observer issue #877, 2026-09-14,
each reconciled to its run's saved crop rectangle to within a pixel). NULL is
contractually "a plain full-canvas downscale", so every consumer places its
geometry on the whole canvas and lands off by the trim's offset and scale — the
exact failure the column was added to prevent, on every run older than it.

The same reasoning that recovers an unrecorded turn recovers *this*: a plain
downscale keeps the canvas's shape, so a stored preview whose **aspect ratio**
is not the canvas's (nor the turned canvas's) is provably not one. That earns
:data:`~seestack.previewcrop.UNKNOWN` — "decline to place geometry" — and never
a fabricated rectangle: the bounds are not recoverable from a PNG header, only
the fact that the plain-downscale contract is broken. Shape rather than size on
purpose, so a preview merely rendered at some other width is never accused.
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

    This is the **run-row form** of
    :func:`~seestack.render.thumbnail.preview_north_up_remainder_deg`, which is
    where the arithmetic actually lives (and which the renderer and the rejection
    tint already go through). All this adds is the half that helper cannot know:
    what a run's stored bytes already carry, which is :func:`baked_north_up_deg`'s
    recorded-or-recovered answer. Deliberately a delegation and not a second
    implementation — two ways to ask "is there a turn left?" is exactly the drift
    the backlog flagged at merge time.

    No master FITS to read a WCS from reads as "nothing to do", the same as an
    unusable one does inside that helper.
    """
    if not run.fits_path:
        return 0.0
    from seestack.render.thumbnail import preview_north_up_remainder_deg

    try:
        return preview_north_up_remainder_deg(
            run.fits_path, already_deg=baked_north_up_deg(run))
    except Exception:  # noqa: BLE001 — an unreadable master simply offers nothing
        return 0.0


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


#: How far a stored preview's aspect ratio may sit from its canvas's before the
#: "plain full-canvas downscale" contract is treated as broken.
#:
#: A downscale's only infidelity is the integer rounding of two independently
#: rounded sides, which on the ≥1-px-per-side grids this app writes is well under
#: 0.1 %. One percent is therefore ~10× the largest honest disagreement, and is
#: deliberately loose: a false ``UNKNOWN`` silently withdraws a working overlay
#: from an ordinary run, which is a worse trade than missing the rare crop that
#: happens to preserve its canvas's shape.
PREVIEW_ASPECT_TOLERANCE = 0.01


def _same_aspect(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether two pixel grids have the same shape, within
    :data:`PREVIEW_ASPECT_TOLERANCE`. Degenerate sides answer ``True`` — an
    unmeasurable grid must not be read as evidence of anything."""
    if a[1] <= 0 or b[1] <= 0 or a[0] <= 0 or b[0] <= 0:
        return True
    ar_a, ar_b = a[0] / a[1], b[0] / b[1]
    return abs(ar_a - ar_b) <= PREVIEW_ASPECT_TOLERANCE * max(ar_a, ar_b)


def recovered_preview_crop(run):  # noqa: ANN001, ANN201
    """What a run's stored preview shows of its canvas — recorded, or recovered
    from the bytes when the column predates the run (see the module docstring).

    The run-row companion to :func:`~seestack.previewcrop.parse_preview_crop`,
    and shaped like :func:`baked_north_up_deg`: a **recorded** value wins outright,
    and only a NULL/blank column falls through to the check.

    Unlike the North-up angle, this column has **no positive "on the canvas grid"
    state** — :func:`~seestack.previewcrop.preview_crop_json` deliberately stores
    NULL for a full-canvas crop as well as for no crop, so that a re-render which
    stops cropping clears the column rather than leaving a stale rectangle. That
    is what makes the check safe to run on *every* NULL: the column never says
    "I checked, and it is the whole canvas", so reading the bytes is the only way
    anyone can know, and a shape that disagrees is evidence either way.

    The check can return :data:`~seestack.previewcrop.UNKNOWN` but never a
    rectangle: a PNG header says what *shape* the picture is, which is enough to
    disprove "plain full-canvas downscale" and nowhere near enough to say which
    part of the canvas survived. Every consumer already refuses to place geometry
    on ``UNKNOWN``, so this hands a legacy cropped run to paths that are written
    and tested — rather than inventing a new one.

    Costs one PNG header read on a NULL-column run, and nothing more on the
    overwhelmingly common answer (a preview that is exactly the canvas grid short-
    circuits before any WCS is touched). Callers that also want the turn should
    ask :func:`baked_north_up_deg`; the two memoise nothing between them, but the
    turn is only consulted here when the sizes already disagree.
    """
    from seestack.previewcrop import UNKNOWN, parse_preview_crop

    stored_json = getattr(run, "preview_crop_json", None)
    if stored_json:
        return parse_preview_crop(stored_json)

    flat = _flat_preview_size(run)
    preview_path = getattr(run, "preview_path", None)
    stored = _png_size(preview_path) if preview_path else None
    if flat is None or stored is None:
        return None                      # unmeasurable — today's behaviour exactly
    if stored == flat:
        return None                      # a plain downscale: the ordinary answer

    # The sizes disagree. A baked North-up turn is the one thing other than a crop
    # that legitimately changes them, so ask what the bytes carry before accusing
    # them — a 90° turn swaps the canvas's shape, and reading that as a crop would
    # withdraw the overlay from every run the owner ever saved North-up.
    expected = flat
    baked = baked_north_up_deg(run)
    if baked:
        from seestack.render.orient import north_up_pixel_transform

        transform = north_up_pixel_transform(flat[0], flat[1], baked)
        if transform is not None:
            expected = (transform[2], transform[3])
    if stored == expected or _same_aspect(stored, expected):
        # Same shape, different size: a preview rendered at some other width is
        # still a faithful downscale, and the arithmetic cannot say otherwise.
        return None
    log.debug("run %s: stored preview %s is not a downscale of %s — declining to "
              "place geometry on it", getattr(run, "id", "?"), stored, expected)
    return UNKNOWN
