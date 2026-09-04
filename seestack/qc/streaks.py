"""
Streak detector — flags frames containing satellite trails, aircraft, or meteors.

Approach: build a bright-pixel mask, mask out the detected stars (which are
small and round), and look for long straight lines in the residual using a
probabilistic Hough transform. Real streaks span tens to hundreds of pixels in
a single frame and that's hard to confuse with anything else once point sources
are removed.

This is layer 1 of streak handling. Layer 2 is the pixel-level sigma clipping
during stacking (handled in seestack.stack). Most streaks get rejected by
clipping; this layer's job is to flag frames where streaks are *severe enough
that whole-frame rejection is the right call* (e.g. Starlink trains crossing
the entire field).

Returns ``(streak_detected, streak_count)``. ``streak_count`` is the number of
distinct line segments found — useful for the Tips sidebar to surface "frame N
has 4 satellites".

:func:`detect_streaks_with_shape` additionally reports *where* in the frame the
dominant flagged feature sits. Shape alone cannot tell a satellite trail from an
edge-on galaxy, but position across a session can: a trail lands somewhere
different in every sub, while a tracked extended object sits in the same place
all night. See :func:`seestack.qc.runner.stationary_streak_frames`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreakShape:
    """Where the dominant flagged component sits in the frame.

    ``cx``/``cy`` are the component's centroid in **normalised** image
    coordinates (0..1 across the width / height of the plane it was measured
    on), so the numbers mean the same thing regardless of sensor size or
    whether the detector ran on a half-resolution plane.
    """

    cx: float
    cy: float

# Minimum line length, in pixels, to count as a streak. Tuned for the half-res
# green channel of a Seestar (~960×540). ~80px on the half-res image is ~160px
# on the full frame — well under typical satellite trails (which often cross
# the whole frame).
DEFAULT_MIN_LINE_LENGTH = 80
DEFAULT_LINE_GAP = 8

# ``probabilistic_hough_line`` is a Monte-Carlo transform; with no fixed seed it
# returns a different set of line segments run-to-run, so ``streak_count`` (which
# is written to the DB) would change every time the same frame is re-QC'd —
# breaking QC idempotency (``test_qc_idempotent``) and, on a marginal streak, the
# ``streak_detected`` boolean too. Seed it so QC is deterministic.
_HOUGH_SEED = 0


def detect_streaks(
    image: np.ndarray,
    *,
    sky_median: float,
    sky_std: float,
    bright_sigma: float = 6.0,
    min_line_length: int = DEFAULT_MIN_LINE_LENGTH,
    line_gap: int = DEFAULT_LINE_GAP,
) -> tuple[bool, int]:
    """Detect streak-like features in a frame — see
    :func:`detect_streaks_with_shape`, of which this is the historical
    two-value form."""
    detected, count, _shape = detect_streaks_with_shape(
        image, sky_median=sky_median, sky_std=sky_std,
        bright_sigma=bright_sigma, min_line_length=min_line_length,
        line_gap=line_gap,
    )
    return detected, count


def detect_streaks_with_shape(
    image: np.ndarray,
    *,
    sky_median: float,
    sky_std: float,
    bright_sigma: float = 6.0,
    min_line_length: int = DEFAULT_MIN_LINE_LENGTH,
    line_gap: int = DEFAULT_LINE_GAP,
) -> tuple[bool, int, StreakShape | None]:
    """
    Detect streak-like features in a frame.

    Parameters
    ----------
    image
        2D image, ideally the half-res green channel from ``green_channel``.
    sky_median, sky_std
        Sky stats. Already computed in the metrics pipeline; passing them in
        avoids recomputing.
    bright_sigma
        Pixels above ``sky_median + bright_sigma * sky_std`` go into the bright
        mask. A streak is bright by definition; this throws away the noise.
    min_line_length, line_gap
        Hough parameters. ``min_line_length`` rejects short segments;
        ``line_gap`` lets a single physical streak survive small dropouts.

    Returns
    -------
    (streak_detected, streak_count, shape)
        ``shape`` is the :class:`StreakShape` of the **largest** qualifying
        component (``None`` when nothing was flagged). Largest-by-area because a
        frame carrying both a bright extended object and a satellite should be
        described by the object: the reconciliation that reads these positions
        only ever *un*-rejects, so mis-picking the smaller feature costs a
        cluster that doesn't form, never a wrong re-accept.
    """
    from skimage.measure import label, regionprops
    from skimage.morphology import dilation, disk
    from skimage.transform import probabilistic_hough_line

    threshold = sky_median + bright_sigma * sky_std
    bright = image > threshold
    if not bright.any():
        return False, 0, None

    # Mask out compact bright blobs (stars). For each connected component,
    # compare the major and minor axis lengths from the pixel covariance —
    # this correctly handles diagonal streaks whose bounding box is square.
    labels = label(bright)
    if labels.max() == 0:
        return False, 0, None

    keep = np.zeros_like(bright, dtype=bool)
    dominant = None  # (area, region) of the biggest qualifying component
    for region in regionprops(labels):
        if region.area < 8:
            continue
        major = float(region.axis_major_length)
        minor = float(region.axis_minor_length) or 1.0
        elongation = major / minor
        if major >= min_line_length and elongation >= 4.0:
            for y, x in region.coords:
                keep[y, x] = True
            if dominant is None or region.area > dominant[0]:
                dominant = (region.area, region)

    if not keep.any():
        return False, 0, None

    # Dilate slightly so Hough has a thicker line to fit.
    keep = dilation(keep, footprint=disk(1))

    lines = probabilistic_hough_line(
        keep, threshold=10, line_length=min_line_length, line_gap=line_gap,
        rng=_HOUGH_SEED,
    )
    n_lines = len(lines)
    if n_lines <= 0:
        return False, 0, None
    shape = _shape_of(dominant[1], image.shape) if dominant is not None else None
    return True, n_lines, shape


def _shape_of(region, shape: tuple[int, ...]) -> StreakShape | None:
    """A component's centroid as :class:`StreakShape`, or ``None`` if the frame
    is degenerate (a zero-width/height plane can't be normalised)."""
    h, w = int(shape[0]), int(shape[1])
    if h <= 0 or w <= 0:
        return None
    cy, cx = (float(v) for v in region.centroid[:2])
    return StreakShape(cx=cx / w, cy=cy / h)
