"""My wishlist — the objects *you* said you want to shoot.

The app already knows two kinds of "what next": the **life list** (a fixed
catalogue of famous objects, with the ones you've captured ticked off) and the
**Tonight planner** (a generic ranking of what is up). Neither of them can hold
the single most natural planning thought a beginner has — *"I want to shoot the
Andromeda Galaxy next"* — so that intent went nowhere: the life list can't be
added to, and the planner ranks the whole catalogue the same way for everyone.

This module is the pure, offline half of the wishlist: take the ids the owner
saved (:class:`seestack.io.library.WishlistEntry`), resolve them against the
bundled catalog, and say for each whether it has been captured yet. No network,
no new data — the catalog ships with the app, the capture matching is the life
list's own, and the "is it up tonight?" half is the planner's
:func:`~seestack.nightplan.well_placed_tonight`.

Read-only and side-effect free, so it is safe to call on every page load.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from seestack.lifelist import MATCH_RADIUS_DEG, catalog_capture_status
from seestack.nightplan import CatalogObject


@dataclass(frozen=True)
class WishlistObject:
    """One saved object, resolved against the catalog and the library."""

    catalog_id: str
    #: Popular name ("Andromeda Galaxy"), or ``""`` for the many catalog entries
    #: that have none — every surface falls back to the id.
    name: str
    type: str
    con: str
    ra_deg: float
    dec_deg: float
    size_arcmin: float | None
    blurb: str
    #: When the owner saved it (UTC ISO) — the list's order.
    added_utc: str
    #: Has it been captured yet? Same match as the life list, so the two screens
    #: can never disagree about whether you've "got" something.
    captured: bool
    safe_name: str | None = None
    target_name: str | None = None
    #: True when the saved id is no longer in the bundled catalog and the row was
    #: rebuilt from the snapshot stored beside it. Nothing renders differently
    #: today; it exists so a caller can tell a stale row from a live one rather
    #: than silently dropping something the owner explicitly saved.
    from_snapshot: bool = False


def _synthetic(entry: Any) -> CatalogObject | None:
    """A stand-in catalog object for a saved id the catalog no longer knows.

    The owner asked for this object by name; a catalog revision that renames or
    drops an id must not quietly delete their list. Needs a position to be worth
    anything (the capture match and every planning surface are coordinate-based),
    so an entry saved without one — which the add path never writes — is the one
    case we do drop.
    """
    if entry.ra_deg is None or entry.dec_deg is None:
        return None
    return CatalogObject(
        id=entry.catalog_id,
        name=entry.name or "",
        ra_deg=float(entry.ra_deg),
        dec_deg=float(entry.dec_deg),
        type="",
        con="",
    )


def wishlist_objects(
    saved: Sequence[Any],
    catalog: Sequence[CatalogObject],
    targets: Iterable[Any],
    *,
    radius_deg: float = MATCH_RADIUS_DEG,
) -> list[WishlistObject]:
    """Resolve the saved ids into full objects, in the order they were saved.

    ``saved`` is any sequence of rows carrying ``catalog_id``, ``name``,
    ``ra_deg``, ``dec_deg`` and ``added_utc`` (the real one is
    :class:`~seestack.io.library.WishlistEntry`, duck-typed so this stays a pure
    function testable without a database); ``targets`` is the library registry,
    exactly as :func:`seestack.lifelist.catalog_capture_status` wants it.

    The capture half is *delegated* to that function rather than re-derived, so
    "have I got this?" means precisely the same thing on the wishlist, the life
    list and the Dashboard tally — three screens quietly disagreeing about
    whether you've captured M31 would make all three untrustworthy.

    ``saved``'s order is preserved exactly (the life list's Messier-first display
    order is wrong here — this is the owner's own queue, not a catalogue).
    """
    by_id = {obj.id: obj for obj in catalog}
    objects: list[CatalogObject] = []
    stale: set[str] = set()
    for entry in saved:
        live = by_id.get(entry.catalog_id)
        if live is not None:
            objects.append(live)
            continue
        synth = _synthetic(entry)
        if synth is not None:
            objects.append(synth)
            stale.add(entry.catalog_id)

    status = {
        e.catalog_id: e
        for e in catalog_capture_status(objects, targets, radius_deg=radius_deg)
    }
    added = {e.catalog_id: e.added_utc for e in saved}

    out: list[WishlistObject] = []
    for obj in objects:
        e = status[obj.id]
        out.append(WishlistObject(
            catalog_id=obj.id,
            name=obj.name,
            type=obj.type,
            con=obj.con,
            ra_deg=obj.ra_deg,
            dec_deg=obj.dec_deg,
            size_arcmin=obj.size_arcmin,
            blurb=obj.blurb,
            added_utc=added.get(obj.id, ""),
            captured=e.captured,
            safe_name=e.safe_name,
            target_name=e.target_name,
            from_snapshot=obj.id in stale,
        ))
    # No sort: ``objects`` was built by walking ``saved``, so the result is
    # already in the caller's order. (``catalog_capture_status`` sorts its own
    # return into catalog display order, which is why the status lookup above
    # goes through a dict rather than zipping.)
    return out


def wishlist_summary(objects: Sequence[WishlistObject]) -> dict[str, int]:
    """Counts for the plain-language line ("2 of the 5 you saved, captured")."""
    return {
        "saved": len(objects),
        "captured": sum(1 for o in objects if o.captured),
    }
