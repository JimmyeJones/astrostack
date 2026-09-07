"""My wishlist — the objects the owner said they want to shoot, and when they're up.

``GET /api/wishlist`` returns the saved objects resolved against the bundled
catalog, each marked captured or not (the life list's own matching, so the two
screens can never disagree); ``POST``/``DELETE /api/wishlist/{catalog_id}`` are
the star toggle. ``GET /api/wishlist/tonight`` runs the planner's existing
dark-window scoring over *just* those objects, which is the half that turns a
saved list into a reason to go outside.

Only ids the bundled catalog actually knows can be saved — the client never
supplies coordinates or names, so a wishlist row can't become a way to inject
arbitrary sky positions into the planner. Everything here is offline: the catalog
ships with the app, and the only writes are one tiny registry table.

Distinct from ``/api/life-list`` (a *fixed* catalogue of famous objects with the
ones you have ticked off) and from ``/api/plan/suggest`` (a *generic* ranking of
showpieces you haven't shot): this is the list **you** built.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from seestack.nightplan import load_catalog
from seestack.wishlist import wishlist_objects, wishlist_summary
from webapp import deps

router = APIRouter(tags=["wishlist"])


class WishlistItem(BaseModel):
    catalog_id: str
    #: Popular name, or ``""`` for the many catalog entries without one — every
    #: surface falls back to the id rather than showing a blank row.
    name: str
    type: str
    con: str
    blurb: str
    size_arcmin: float | None
    added_utc: str
    captured: bool
    safe_name: str | None
    target_name: str | None
    #: The captured target's picture, when it has one. ``None`` for an object not
    #: captured *and* for one captured but not stacked yet.
    thumbnail_url: str | None


class WishlistCounts(BaseModel):
    saved: int
    captured: int


class WishlistResponse(BaseModel):
    items: list[WishlistItem]
    counts: WishlistCounts


def _catalog_object(catalog_id: str):  # noqa: ANN202 — CatalogObject | None
    """The bundled catalog object for ``catalog_id``, or ``None`` if unknown.

    The whitelist for what may be saved: an id the app can't render is an id the
    owner can't have meant, and validating here (rather than trusting the client)
    keeps the wishlist's coordinates the catalog's own."""
    for obj in load_catalog():
        if obj.id == catalog_id:
            return obj
    return None


def _resolved(request: Request) -> WishlistResponse:
    """The current wishlist, resolved and counted — the response every route here
    returns, so a toggle's answer is already the new list and the UI needs no
    follow-up fetch."""
    lib = deps.open_library(request)
    try:
        saved = lib.list_wishlist()
        targets = lib.list_targets()
    finally:
        lib.close()

    objects = wishlist_objects(saved, load_catalog(), targets)
    # Which captured targets actually have a picture, from the registry's own
    # stamp — so a row never offers a thumbnail URL that 404s (the same existence
    # test ``/api/life-list`` and ``/api/targets`` do).
    previews = {
        t.safe_name: bool(t.last_stack_preview and Path(t.last_stack_preview).exists())
        for t in targets
    }
    return WishlistResponse(
        items=[
            WishlistItem(
                catalog_id=o.catalog_id,
                name=o.name,
                type=o.type,
                con=o.con,
                blurb=o.blurb,
                size_arcmin=o.size_arcmin,
                added_utc=o.added_utc,
                captured=o.captured,
                safe_name=o.safe_name,
                target_name=o.target_name,
                thumbnail_url=(
                    f"/api/targets/{o.safe_name}/thumbnail"
                    if o.safe_name is not None and previews.get(o.safe_name)
                    else None
                ),
            )
            for o in objects
        ],
        counts=WishlistCounts(**wishlist_summary(objects)),
    )


@router.get("/api/wishlist", response_model=WishlistResponse)
def get_wishlist(request: Request) -> WishlistResponse:
    """Everything the owner saved, oldest first, with capture status.

    Empty on a library that has never had one, so every surface that draws it
    self-hides and a first-run install sees nothing new. Read-only and offline."""
    return _resolved(request)


@router.post("/api/wishlist/{catalog_id}", response_model=WishlistResponse)
def add_wishlist(catalog_id: str, request: Request) -> WishlistResponse:
    """Save one catalog object ("☆ Add to wishlist").

    Idempotent — starring something already saved keeps its original place in the
    list rather than moving it to the end. 404 on an id the bundled catalog
    doesn't define. Returns the whole new list, so the star's answer *is* the
    refreshed state."""
    obj = _catalog_object(catalog_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Unknown object")
    lib = deps.open_library(request)
    try:
        lib.add_to_wishlist(
            obj.id, name=obj.name, ra_deg=obj.ra_deg, dec_deg=obj.dec_deg,
        )
    finally:
        lib.close()
    return _resolved(request)


@router.delete("/api/wishlist/{catalog_id}", response_model=WishlistResponse)
def remove_wishlist(catalog_id: str, request: Request) -> WishlistResponse:
    """Un-star one object. Removing something already gone is not an error (the
    star is a toggle, and two tabs can both untick it), so this never 404s."""
    lib = deps.open_library(request)
    try:
        lib.remove_from_wishlist(catalog_id)
    finally:
        lib.close()
    return _resolved(request)


class WishlistTonightObject(BaseModel):
    """One wishlisted object that is genuinely usable in tonight's dark window."""

    catalog_id: str
    name: str
    type: str
    con: str
    blurb: str
    captured: bool
    safe_name: str | None
    max_altitude_deg: float
    minutes_above_min_alt: float
    moon_separation_deg: float
    moon_up_fraction: float | None
    usable_start_utc: str | None
    usable_end_utc: str | None
    transit_utc: str | None
    score: float


class WishlistTonightOut(BaseModel):
    """"Your wishlist target M45 is up and high by 11 pm tonight."

    ``up`` is empty — and the card self-hides — when the wishlist is empty,
    nothing on it clears the altitude floor, or no observing location is known;
    ``saved`` and ``location_source`` let the UI say *which* of those it is
    instead of silently showing nothing.
    """

    saved: int
    up: list[WishlistTonightObject]
    location_source: str = "none"


#: How many wishlisted objects the "up tonight" slice names.
#:
#: The card is a nudge, not a table — the Tonight page below it already ranks
#: everything. Three is enough to cover "and there's a second one up too" without
#: turning a personal shortlist back into the catalogue the user was escaping.
_TONIGHT_LIMIT = 3


@router.get("/api/wishlist/tonight", response_model=WishlistTonightOut)
def get_wishlist_tonight(
    request: Request,
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference; defaults to now"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
) -> WishlistTonightOut:
    """Which of the objects *you* saved are up and well placed tonight.

    The saved list is the intent; this is the payoff. It adds no new data and no
    new scoring: the objects come from the wishlist, and "is it up?" is the same
    dark-window / altitude / Moon blend
    (:func:`seestack.nightplan.well_placed_tonight`) that every other planning
    card on the page uses — so a wishlist row and a Tonight row can never
    disagree about the same object. Read-only and offline."""
    from seestack.nightplan import HorizonProfile, well_placed_tonight
    from webapp.routers.plan import _resolve_observer

    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    lib = deps.open_library(request)
    try:
        saved = lib.list_wishlist()
        targets = lib.list_targets()
    finally:
        lib.close()

    catalog = load_catalog()
    objects = wishlist_objects(saved, catalog, targets)
    observer, location_source = _resolve_observer(request, settings)
    base = WishlistTonightOut(saved=len(objects), up=[],
                              location_source=location_source)
    if observer is None or not objects:
        return base

    by_id = {obj.id: obj for obj in catalog}
    # Only objects the catalog still defines get the astropy pass: a stale
    # snapshot row has a position but no vetted size/type, and a planning line
    # about an object the app can no longer describe would raise more questions
    # than it answers. It stays visible on the wishlist itself either way.
    wanted = [by_id[o.catalog_id] for o in objects if o.catalog_id in by_id]
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    placed = well_placed_tonight(
        observer, start, wanted,
        min_altitude_deg=float(min_altitude),
        limit=_TONIGHT_LIMIT,
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
    )  # best-first

    status: dict[str, Any] = {o.catalog_id: o for o in objects}
    base.up = [
        WishlistTonightObject(
            catalog_id=p.id,
            name=p.name,
            type=p.type,
            con=p.con,
            blurb=p.blurb,
            captured=status[p.id].captured,
            safe_name=status[p.id].safe_name,
            max_altitude_deg=p.max_altitude_deg,
            minutes_above_min_alt=p.minutes_above_min_alt,
            moon_separation_deg=p.moon_separation_deg,
            moon_up_fraction=p.moon_up_fraction,
            usable_start_utc=p.usable_start_utc,
            usable_end_utc=p.usable_end_utc,
            transit_utc=p.transit_utc,
            score=p.score,
        )
        for p in placed
    ]
    return base
