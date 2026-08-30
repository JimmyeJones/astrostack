"""How much of the sky a stack actually covers — in real square degrees.

The "My map" view answers *where* you have been; this answers *how much*. It is
the one number every deep-sky imager wants and a beginner understands instantly
("I have photographed 0.04 % of the sky"), and it must not be measured by
counting pixels on the map itself: that map is an **Aitoff** projection (not
equal-area, so a pixel near the rim is worth less sky than one at the centre)
and it deliberately draws every picture several times life size so the pictures
stay visible. A count taken off it would be wrong twice over, and a stat that
silently disagrees with the picture beside it is worse than no stat.

So the area is measured where it is exactly known — each run's **own WCS**. The
determinant of the pixel-scale matrix is the solid angle one pixel subtends, so
covered area is simply "how many pixels did enough frames reach" × that. No
projection is involved and nothing about how the map is drawn can move the
number.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

#: The whole celestial sphere in square degrees (4π sr). The denominator for
#: "what fraction of the sky have I seen".
WHOLE_SKY_DEG2 = 41252.96124941928


def stack_sky_area_deg2(fits_path: str | Path) -> float | None:
    """The solid angle (deg²) a stack's **well-covered** pixels take up on the sky.

    "Well-covered" is :func:`~seestack.render.thumbnail.stack_detail_mask` — the
    app's own existing "did enough frames land here to trust it?" definition, the
    same one that masks a mosaic's ragged fringe out of the map — so the stat and
    the picture agree about what counts as photographed. A run with no
    frame-count sibling falls back to its has-data footprint there, so a legacy
    run still contributes its real shape.

    ``None`` when the master is missing or carries no celestial WCS: there is no
    honest area to report, and guessing one from a nominal field would quietly
    invent sky the owner never pointed at.

    The pixel area is taken at the canvas reference point and applied to the
    whole canvas, which over a Seestar mosaic's few degrees costs well under a
    percent — far inside the precision this number is ever read at.
    """
    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.render.thumbnail import stack_detail_mask

    path = Path(fits_path)
    if not path.exists():
        return None
    try:
        wcs, w, h = celestial_wcs_from_fits(path)
    except Exception:  # noqa: BLE001 — an unreadable header just means "no area"
        return None
    if wcs is None or w <= 0 or h <= 0:
        return None
    try:
        per_px = abs(float(np.linalg.det(wcs.pixel_scale_matrix)))
    except Exception:  # noqa: BLE001 — a degenerate matrix is not an area
        return None
    if not np.isfinite(per_px) or per_px <= 0.0:
        return None
    try:
        mask = stack_detail_mask(path)
    except Exception:  # noqa: BLE001 — one unreadable coverage map isn't fatal
        return None
    n_covered = int(np.count_nonzero(mask))
    if n_covered <= 0:
        return None
    return n_covered * per_px


def sky_fraction(deg2: float) -> float:
    """``deg2`` as a fraction of the whole sky (0–1), clamped so a rounding
    artefact can never claim more than all of it."""
    if not np.isfinite(deg2) or deg2 <= 0.0:
        return 0.0
    return min(1.0, float(deg2) / WHOLE_SKY_DEG2)
