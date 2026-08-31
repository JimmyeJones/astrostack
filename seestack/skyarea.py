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

Across *several* pictures the honest total is a **union**, not a sum: two library
targets aimed at the same patch (a wider mosaic re-framed over an earlier single
field, or the two folder spellings of one object) are one patch of sky, and
adding them told the owner they had seen sky they had only seen twice. See
:func:`sky_area_union_deg2` — each picture keeps its own exact WCS area, and a
coarse sky grid decides only what share of it was already reached.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: The whole celestial sphere in square degrees (4π sr). The denominator for
#: "what fraction of the sky have I seen".
WHOLE_SKY_DEG2 = 41252.96124941928

#: Sky-grid resolution (degrees) the union measurement buckets footprints into.
#: Coarse on purpose: the grid is only ever asked "have I already counted this
#: patch?", never "how big is it" — each picture keeps its own exact WCS area —
#: so its coarseness costs accuracy only along the boundary of a *real* overlap,
#: well under a percent of a Seestar field and far inside the precision this
#: number is ever read at. Coarse also keeps the bookkeeping small on a library
#: of deep mosaics (a 20 deg² mosaic is ~8 000 cells, not millions).
_UNION_CELL_DEG = 0.05

#: Cell key packing: ``lat_index * _RA_CELLS_MAX + ra_index``. The widest band
#: holds ``360 / _UNION_CELL_DEG`` = 7 200 cells, so this leaves an order of
#: magnitude of headroom and keeps a cell key one small int.
_RA_CELLS_MAX = 100_000

#: How many pixel blocks span one cell. A picture's area is attributed to the
#: cell its block *centre* lands in, so the blocks must be comfortably finer
#: than the cells or a picture's own edge would be filed in the wrong one.
_BLOCKS_PER_CELL = 4


def _read_master(fits_path: str | Path):  # noqa: ANN202 — (wcs, mask, per_px) | None
    """A master's celestial WCS, well-covered mask and per-pixel solid angle.

    ``None`` when there is no honest area to report: the file is missing or
    unreadable, it carries no celestial WCS, its pixel-scale matrix is
    degenerate, or nothing on the canvas is well covered.
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
    if int(np.count_nonzero(mask)) <= 0:
        return None
    return wcs, mask, per_px


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
    read = _read_master(fits_path)
    if read is None:
        return None
    _wcs, mask, per_px = read
    return int(np.count_nonzero(mask)) * per_px


def _sky_cell_keys(ra_deg: np.ndarray, dec_deg: np.ndarray,
                   cell_deg: float) -> np.ndarray:
    """Bucket sky positions into cells of roughly ``cell_deg`` on a side.

    Bands are uniform in declination and each band is split into
    ``360·cos(dec)/cell`` cells, so a cell stays roughly square all the way to
    the pole instead of degenerating into a thin sliver. The cells are *not*
    exactly equal-area, and deliberately need not be: nothing measures an area
    from a cell count — a cell is only an identity for "this patch is already
    counted".
    """
    n_lat = max(1, int(round(180.0 / cell_deg)))
    band_deg = 180.0 / n_lat
    lat = np.clip(
        np.floor((np.asarray(dec_deg, dtype=float) + 90.0) / band_deg).astype(np.int64),
        0, n_lat - 1,
    )
    lat_centre = -90.0 + (lat + 0.5) * band_deg
    n_ra = np.maximum(
        1, np.round(360.0 * np.cos(np.radians(lat_centre)) / cell_deg),
    ).astype(np.int64)
    ra = np.mod(np.asarray(ra_deg, dtype=float), 360.0)
    ra_idx = np.mod(np.floor(ra / 360.0 * n_ra).astype(np.int64), n_ra)
    return lat * _RA_CELLS_MAX + ra_idx


def _mask_weights_by_cell(mask: np.ndarray, wcs, per_px: float,  # noqa: ANN001
                          cell_deg: float) -> dict[int, int]:
    """How many of ``mask``'s covered pixels fall in each sky cell.

    Reduced in **blocks** rather than per pixel: a mosaic canvas is tens of
    millions of pixels and the answer is only ever read at cell resolution.
    Every covered pixel is still counted exactly once (the block sums are
    exact); only *where* it is attributed is rounded, by at most half a block —
    which is why a block is a quarter of a cell.
    """
    h, w = mask.shape[:2]
    pix_deg = float(np.sqrt(per_px))
    step = max(1, int(round(cell_deg / (_BLOCKS_PER_CELL * pix_deg))))
    rows = np.arange(0, h, step)
    cols = np.arange(0, w, step)
    counts = np.add.reduceat(
        np.add.reduceat(np.asarray(mask, dtype=bool).astype(np.int64), rows, axis=0),
        cols, axis=1,
    )
    hit = counts > 0
    if not hit.any():
        return {}
    # Block centres in 0-based pixel coordinates. A short edge block centres on
    # what it actually holds, not on where a full block would have ended.
    ys = (rows + np.minimum(rows + step, h) - 1) / 2.0
    xs = (cols + np.minimum(cols + step, w) - 1) / 2.0
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    try:
        ra, dec = wcs.wcs_pix2world(xx[hit], yy[hit], 0)
    except Exception:  # noqa: BLE001 — an unprojectable canvas contributes no cells
        return {}
    ra = np.asarray(ra, dtype=float)
    dec = np.asarray(dec, dtype=float)
    good = np.isfinite(ra) & np.isfinite(dec)
    if not good.any():
        return {}
    keys = _sky_cell_keys(ra[good], dec[good], cell_deg)
    weights = counts[hit][good]
    # Blocks outnumber cells by ~16, so fold them with numpy rather than a
    # Python loop over every block of every master in the library.
    cells, index = np.unique(keys, return_inverse=True)
    totals = np.bincount(index, weights=weights.astype(float))
    return dict(zip(cells.tolist(), (int(t) for t in totals), strict=True))


@dataclass(frozen=True)
class _Footprint:
    """One master's covered sky: its exact WCS area, and where that area sits."""

    area_deg2: float
    #: Covered pixels per sky cell — *weights*, not areas, so a picture's own
    #: exact area can be split across cells without measuring it a second way.
    weight_by_cell: dict[int, int]
    total_weight: int


def _stack_footprint(fits_path: str | Path, cell_deg: float) -> _Footprint | None:
    """A master's exact covered area plus how it is spread over the sky grid."""
    read = _read_master(fits_path)
    if read is None:
        return None
    wcs, mask, per_px = read
    n_covered = int(np.count_nonzero(mask))
    return _Footprint(
        area_deg2=n_covered * per_px,
        weight_by_cell=_mask_weights_by_cell(mask, wcs, per_px, cell_deg),
        total_weight=n_covered,
    )


@dataclass(frozen=True)
class SkyCoverage:
    """How much sky a set of masters covers, and how much of it was shared."""

    #: The honest total — an overlapped patch counted once.
    union_deg2: float
    #: What simply adding the pictures up would have said. Never smaller than
    #: ``union_deg2``; the difference is the sky that was counted twice.
    summed_deg2: float
    #: How many masters carried a measurable area at all.
    n_pictures: int


def sky_area_union_deg2(
    fits_paths: Iterable[str | Path], *, cell_deg: float = _UNION_CELL_DEG,
) -> SkyCoverage:
    """Total sky these masters cover, counting an overlapped patch **once**.

    Two library targets aimed at the same patch are ordinary on a real install —
    a wider mosaic re-framed over an earlier single field, or the two folder
    spellings of one object — and simply adding their areas told the owner they
    had photographed sky they had only photographed *twice*.

    Each picture keeps its **own exact WCS area** (:func:`stack_sky_area_deg2`'s
    number, unchanged). The sky grid is used only to work out what share of a
    picture lands where an earlier one already reached, and that share is
    subtracted — so a lone picture, and a library whose pictures never overlap,
    measure bit-for-bit what they did before. The largest picture is taken
    first, so a mosaic keeps its exact area and the single field inside it is the
    one discounted.
    """
    footprints = [
        f for f in (_stack_footprint(p, cell_deg) for p in fits_paths)
        if f is not None
    ]
    footprints.sort(key=lambda f: -f.area_deg2)
    claimed: set[int] = set()
    union = 0.0
    summed = 0.0
    for footprint in footprints:
        summed += footprint.area_deg2
        fresh = 1.0
        if claimed and footprint.total_weight > 0:
            seen = sum(weight for cell, weight in footprint.weight_by_cell.items()
                       if cell in claimed)
            fresh = 1.0 - (seen / footprint.total_weight)
        union += footprint.area_deg2 * min(1.0, max(0.0, fresh))
        claimed.update(footprint.weight_by_cell)
    return SkyCoverage(union_deg2=union, summed_deg2=summed,
                       n_pictures=len(footprints))


def sky_fraction(deg2: float) -> float:
    """``deg2`` as a fraction of the whole sky (0–1), clamped so a rounding
    artefact can never claim more than all of it."""
    if not np.isfinite(deg2) or deg2 <= 0.0:
        return 0.0
    return min(1.0, float(deg2) / WHOLE_SKY_DEG2)
