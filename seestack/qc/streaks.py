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
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

# Minimum line length, in pixels, to count as a streak. Tuned for the half-res
# green channel of a Seestar (~960×540). ~80px on the half-res image is ~160px
# on the full frame — well under typical satellite trails (which often cross
# the whole frame).
DEFAULT_MIN_LINE_LENGTH = 80
DEFAULT_LINE_GAP = 8


def detect_streaks(
    image: np.ndarray,
    *,
    sky_median: float,
    sky_std: float,
    bright_sigma: float = 6.0,
    min_line_length: int = DEFAULT_MIN_LINE_LENGTH,
    line_gap: int = DEFAULT_LINE_GAP,
) -> tuple[bool, int]:
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
    (streak_detected, streak_count)
    """
    from skimage.measure import label, regionprops
    from skimage.morphology import dilation, disk
    from skimage.transform import probabilistic_hough_line

    threshold = sky_median + bright_sigma * sky_std
    bright = image > threshold
    if not bright.any():
        return False, 0

    # Mask out compact bright blobs (stars). For each connected component,
    # compare the major and minor axis lengths from the pixel covariance —
    # this correctly handles diagonal streaks whose bounding box is square.
    labels = label(bright)
    if labels.max() == 0:
        return False, 0

    keep = np.zeros_like(bright, dtype=bool)
    for region in regionprops(labels):
        if region.area < 8:
            continue
        major = float(region.axis_major_length)
        minor = float(region.axis_minor_length) or 1.0
        elongation = major / minor
        if major >= min_line_length and elongation >= 4.0:
            for y, x in region.coords:
                keep[y, x] = True

    if not keep.any():
        return False, 0

    # Dilate slightly so Hough has a thicker line to fit.
    keep = dilation(keep, footprint=disk(1))

    lines = probabilistic_hough_line(
        keep, threshold=10, line_length=min_line_length, line_gap=line_gap
    )
    n_lines = len(lines)
    return n_lines > 0, n_lines
