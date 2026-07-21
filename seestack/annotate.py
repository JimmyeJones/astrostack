"""Label the catalog deep-sky objects that fall inside a solved stack's field.

A beginner who stacks a wide field (or a mosaic) captures more than the one
object they aimed at — a nearby galaxy, an NGC cluster, a named nebula — and has
no idea what the other fuzzy blobs are. Every stack already stores its solved
output WCS (``stack_runs.wcs_json``) and we already ship an offline deep-sky
catalog (:func:`seestack.nightplan.load_catalog`), so we can compute exactly which
catalog objects land inside the field and where, then draw their names on the
result.

Pure and offline: no network, no new dependency (astropy is already a core dep).
Given a stack's output WCS and its canvas pixel dimensions, project every bundled
catalog object into pixel coordinates and keep those whose centre lands inside the
frame. Pixel coordinates are in the WCS's own grid (0-based, top-left origin like
the FITS/preview grid the stacker writes), so a caller can position a label over a
proxy preview by scaling ``x_px / width_px``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass


@dataclass
class FieldObject:
    """One catalog object that falls inside a stack's field, with its pixel spot."""

    catalog_id: str        # catalog designation, e.g. "M31" / "NGC 891"
    name: str              # friendly name when the catalog has one, else ""
    type: str              # "galaxy" / "nebula" / … (catalog ``type``)
    ra_deg: float
    dec_deg: float
    x_px: float            # 0-based pixel x on the WCS grid (left → right)
    y_px: float            # 0-based pixel y on the WCS grid (top → bottom)


def objects_in_field(
    wcs,  # noqa: ANN001 — an astropy WCS (kept dependency-light in the signature)
    width_px: int,
    height_px: int,
    *,
    margin: float = 0.0,
    catalog=None,  # noqa: ANN001 — iterable of nightplan.CatalogObject; None → the bundled one
) -> list[FieldObject]:
    """Return the catalog objects whose centre lands inside a ``width_px`` ×
    ``height_px`` field described by ``wcs``.

    ``margin`` (pixels) widens the accepted box symmetrically — a small positive
    margin keeps an object whose label anchor sits just past the edge. Objects
    behind the projection (more than ~90° from the field centre → a non-finite or
    wildly out-of-range pixel) are dropped, so it is RA-seam and pole safe.

    Returns an empty list when ``wcs`` is ``None`` or the frame has no area, so a
    caller never has to special-case an unsolved run.
    """
    if wcs is None or width_px <= 0 or height_px <= 0:
        return []

    from seestack.nightplan import load_catalog

    objs = tuple(catalog) if catalog is not None else load_catalog()
    if not objs:
        return []

    import numpy as np

    ra = np.array([o.ra_deg for o in objs], dtype=float)
    dec = np.array([o.dec_deg for o in objs], dtype=float)

    # A single vectorised world→pixel projection. astropy warns (not raises) on
    # coordinates behind the projection; those come back non-finite and we filter
    # them out below, so the warning is just noise.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            xs, ys = wcs.world_to_pixel_values(ra, dec)
        except Exception:  # noqa: BLE001 — a degenerate/unsupported WCS → nothing to show
            return []

    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)

    lo_x, hi_x = -margin, (width_px - 1) + margin
    lo_y, hi_y = -margin, (height_px - 1) + margin

    out: list[FieldObject] = []
    for obj, x, y in zip(objs, xs, ys, strict=False):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
            continue
        out.append(
            FieldObject(
                catalog_id=obj.id,
                name=obj.name,
                type=obj.type,
                ra_deg=obj.ra_deg,
                dec_deg=obj.dec_deg,
                x_px=float(x),
                y_px=float(y),
            )
        )
    return out
