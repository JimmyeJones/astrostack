"""My life list — the famous objects you've captured, and the ones still to get.

``GET /api/life-list`` returns the bundled catalog (110 Messier + the curated
popular NGC/IC) with each object marked captured or not, matched against the
library's plate-solved target centres, plus the counts for the plain-language
header.

``GET /api/life-list/grid.jpg`` renders that same list as one shareable poster —
the squares you have filled with your own pictures, the rest still to shoot.

Everything about it is read-only and offline: the catalog ships with the app,
and the match reads only the target registry — no project DB is opened and no
network is touched, so it is cheap enough to answer on every page load.

Distinct from ``/api/plan/tonight`` (what is *up tonight*) and from a target's
own progress (one object's integration): this is the **collection** view — the
"which of the 110 have I got?" question a beginner is actually counting.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from seestack.lifelist import catalog_capture_status, is_messier, life_list_summary
from seestack.nightplan import load_catalog
from webapp import deps

router = APIRouter(tags=["life-list"])

#: How many nearly-finished constellations to check against tonight's sky.
#:
#: Only the closest few can plausibly win — the ranking is fewest-missing first —
#: and each extra one costs astropy work on a page load for a nudge nobody would
#: see. Four is comfortably past the point where a further candidate could beat
#: the ones ahead of it on "closest with something up tonight".
_NEARLY_THERE_CANDIDATES = 4


class LifeListItem(BaseModel):
    catalog_id: str
    #: Popular name, or ``""`` for the many catalog entries without one — the UI
    #: falls back to the id rather than showing a blank tile.
    name: str
    type: str
    con: str
    blurb: str
    size_arcmin: float | None
    captured: bool
    safe_name: str | None
    target_name: str | None
    sep_deg: float | None
    #: The captured target's picture, when it has one. ``None`` for an object
    #: never captured *and* for one captured but not yet stacked — the tile
    #: still lights up in the second case, it just shows no image yet.
    thumbnail_url: str | None


class LifeListCounts(BaseModel):
    messier_captured: int
    messier_total: int
    other_captured: int
    other_total: int


class LifeListResponse(BaseModel):
    messier: list[LifeListItem]
    other: list[LifeListItem]
    counts: LifeListCounts


def _item(entry, previews: dict[str, bool]) -> LifeListItem:
    safe = entry.safe_name
    return LifeListItem(
        catalog_id=entry.catalog_id,
        name=entry.name,
        type=entry.type,
        con=entry.con,
        blurb=entry.blurb,
        size_arcmin=entry.size_arcmin,
        captured=entry.captured,
        safe_name=safe,
        target_name=entry.target_name,
        sep_deg=entry.sep_deg,
        thumbnail_url=(
            f"/api/targets/{safe}/thumbnail"
            if safe is not None and previews.get(safe)
            else None
        ),
    )


class NearlyThereObject(BaseModel):
    """One object still missing from a nearly-finished constellation."""

    catalog_id: str
    name: str
    type: str
    blurb: str
    #: Tonight's placement, when this object is genuinely usable in tonight's
    #: dark window — ``None`` for a missing object that isn't up (or when no
    #: observing location is known, in which case *no* object carries one).
    max_altitude_deg: float | None = None
    minutes_above_min_alt: float | None = None
    usable_start_utc: str | None = None
    usable_end_utc: str | None = None


class NearlyThereOut(BaseModel):
    """"You're one away from finishing Orion — and it's up tonight."

    The life list says *how many* of the famous objects you have; this says what
    to point at **next**, which is the half that gets someone outside. ``null``
    when no constellation is close, so the card self-hides.
    """

    con: str
    #: Full constellation name ("Orion"), or the abbreviation when unknown.
    constellation: str
    captured: int
    total: int
    missing: list[NearlyThereObject]
    #: The missing object that's best placed tonight, or ``null`` when none of
    #: them is up (or no location is known). Its ``catalog_id`` is one of
    #: ``missing``, so the UI can highlight the same row.
    tonight_catalog_id: str | None = None
    #: How the observing site was resolved: "settings" / "fits" / "none" — lets
    #: the UI explain a missing tonight pick rather than silently omitting it.
    location_source: str = "none"


@router.get("/api/life-list/nearly-there", response_model=NearlyThereOut | None)
def get_nearly_there(
    request: Request,
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference; defaults to now"),
) -> NearlyThereOut | None:
    """The constellation the owner is closest to finishing, and whether one of
    its missing objects is up tonight.

    "You've captured 42 of 110" is a number you look at; "you're one object away
    from finishing Orion, and it's up until 02:10" is a plan. Both halves come
    from data the app already has — the life list's capture matching and the
    planner's dark-window observability — so this adds no new data, no network
    and no settings.

    Prefers a constellation with a missing object genuinely usable tonight, so
    the nudge is actionable rather than a to-do note; falls back to the closest
    constellation with no tonight pick when nothing is up (or no location is
    known). ``null`` when nothing is close (see
    :func:`seestack.lifelist.nearly_complete_constellations`) — the card then
    self-hides. Read-only and offline.
    """
    from seestack.lifelist import nearly_complete_constellations
    from seestack.nightplan import HorizonProfile, well_placed_tonight
    from seestack.objectinfo import CONSTELLATION_NAMES
    from webapp.routers.plan import _resolve_observer

    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
    finally:
        lib.close()

    entries = catalog_capture_status(load_catalog(), targets)
    candidates = nearly_complete_constellations(entries)
    if not candidates:
        return None

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    settings = deps.get_settings(request)
    observer, location_source = _resolve_observer(request, settings)
    by_id = {obj.id: obj for obj in load_catalog()}

    # Prefer the closest constellation that has a missing object actually up
    # tonight — an actionable nudge beats a marginally closer but un-shootable
    # one. With no location (or nothing up) we still show the closest
    # constellation, just without the "tonight" half.
    #
    # One observability pass over the top few candidates' missing objects, not
    # one per candidate: the astropy batch is the expensive part of this
    # endpoint, and it is the same dark window either way.
    chosen, best = candidates[0], None
    if observer is not None:
        top = candidates[:_NEARLY_THERE_CANDIDATES]
        objects = [by_id[e.catalog_id] for cand in top for e in cand.missing
                   if e.catalog_id in by_id]
        placed = well_placed_tonight(
            observer, start, objects,
            min_altitude_deg=float(settings.min_target_altitude_deg),
            horizon=HorizonProfile.from_pairs(settings.horizon_profile),
        )  # best-first
        for cand in top:
            ids = {e.catalog_id for e in cand.missing}
            hit = next((p for p in placed if p.id in ids), None)
            if hit is not None:
                chosen, best = cand, hit
                break

    up = {} if best is None else {best.id: best}
    return NearlyThereOut(
        con=chosen.con,
        constellation=CONSTELLATION_NAMES.get(chosen.con, chosen.con),
        captured=chosen.captured,
        total=chosen.total,
        missing=[
            NearlyThereObject(
                catalog_id=e.catalog_id,
                name=e.name,
                type=e.type,
                blurb=e.blurb,
                max_altitude_deg=(up[e.catalog_id].max_altitude_deg
                                  if e.catalog_id in up else None),
                minutes_above_min_alt=(up[e.catalog_id].minutes_above_min_alt
                                       if e.catalog_id in up else None),
                usable_start_utc=(up[e.catalog_id].usable_start_utc
                                  if e.catalog_id in up else None),
                usable_end_utc=(up[e.catalog_id].usable_end_utc
                                if e.catalog_id in up else None),
            )
            for e in chosen.missing
        ],
        tonight_catalog_id=(best.id if best is not None else None),
        location_source=location_source,
    )


@router.get("/api/life-list/counts", response_model=LifeListCounts)
def get_life_list_counts(request: Request) -> LifeListCounts:
    """Just the tally — "42 of the 110 Messier objects" — with no catalog rows.

    Exactly the ``counts`` block of ``GET /api/life-list``, from the same
    :func:`~seestack.lifelist.life_list_summary` over the same
    :func:`~seestack.lifelist.catalog_capture_status`, so the Dashboard's line
    and the life-list page can never quote two different numbers.

    It exists as its own route because the Dashboard asks on every visit and
    only wants the tally: the full response carries ~160 catalog rows with
    blurbs and thumbnail URLs, and it also has to stat every captured target's
    preview file to decide those URLs — work worth doing for the page that draws
    the tiles and worth skipping for one sentence. The library read itself is the
    same registry walk (no project DB, no network), which is why the module
    docstring can call it cheap enough for a page load.
    """
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
    finally:
        lib.close()
    entries = catalog_capture_status(load_catalog(), targets)
    return LifeListCounts(**life_list_summary(entries))


@router.get("/api/life-list", response_model=LifeListResponse)
def get_life_list(request: Request) -> LifeListResponse:
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
    finally:
        lib.close()

    # Which captured targets actually have a picture to show. Checked here, from
    # the registry's own stamp, so a tile never offers a thumbnail URL that
    # 404s — the same existence test ``/api/targets`` does for ``has_preview``.
    previews = {
        t.safe_name: bool(t.last_stack_preview and Path(t.last_stack_preview).exists())
        for t in targets
    }

    entries = catalog_capture_status(load_catalog(), targets)
    return LifeListResponse(
        messier=[_item(e, previews) for e in entries if is_messier(e.catalog_id)],
        other=[_item(e, previews) for e in entries if not is_messier(e.catalog_id)],
        counts=LifeListCounts(**life_list_summary(entries)),
    )


@router.get("/api/life-list/grid.jpg")
def get_life_list_grid(request: Request):
    """Download "My Messier grid" — the whole life list as one shareable JPEG.

    The page above shows the same thing, but only to whoever is looking at the
    app. This is the version you can post: all 110 Messier squares in catalog
    order, your own picture in the ones you have and a dim numbered square in the
    ones you haven't, under a strip saying how far along you are. The empty
    squares are deliberately drawn — they are what makes it a life list rather
    than a gallery.

    Rendered on demand from the previews the app already keeps, exactly like the
    montage wall (``/api/gallery/montage.jpg``) and the recap poster
    (``/api/recap.jpg``): nothing is written to the library and no project is
    modified. 404s until at least one object is captured, so the offer can
    self-hide on a fresh install rather than handing someone a wall of grey.
    """
    import io

    from fastapi.responses import Response
    from PIL import Image

    from seestack.lifelistcard import (
        TILE_SOURCE_MAX_PX,
        GridCell,
        build_life_list_grid,
        grid_subtitle,
        grid_title,
    )
    from seestack.stack.output import save_display_jpeg

    # Package-private helper, shared rather than re-implemented so the grid shows
    # the same picture the life-list tile does: a pinned cover wins, else the
    # newest stack's preview, else the newest run that still has one.
    from webapp.routers.targets import current_picture_path

    lib = deps.open_library(request)
    try:
        targets = list(lib.list_targets())
        entries = [e for e in catalog_capture_status(load_catalog(), targets)
                   if is_messier(e.catalog_id)]
        # Resolve a picture only for the targets that actually hold a captured
        # object, and only once each — several Messier objects can match the same
        # target (a mosaic across M65/M66), and a Seestar owner's library has far
        # more targets than the list has squares.
        wanted = {e.safe_name for e in entries if e.captured and e.safe_name}
        paths: dict[str, Path | None] = {}
        for t in targets:
            if t.safe_name in wanted:
                paths[t.safe_name] = current_picture_path(lib, t)
    finally:
        lib.close()

    # Load each picture once, downscaled on the way in. A full library fills 110
    # squares, and holding 110 full previews (a megabyte-plus of pixels each) to
    # build one poster is exactly the kind of peak this app's RAM-capped NAS
    # cannot afford — the tile is ~114 px, so anything past TILE_SOURCE_MAX_PX is
    # thrown away by the cover-crop anyway.
    loaded: dict[str, Any] = {}
    for safe, path in paths.items():
        if path is None:
            continue
        try:
            with Image.open(path) as img:
                small = img.convert("RGB")
                small.thumbnail((TILE_SOURCE_MAX_PX, TILE_SOURCE_MAX_PX), Image.BOX)
                loaded[safe] = small
        except Exception:  # noqa: BLE001 — a bad preview must not sink the grid
            continue

    cells = [
        GridCell(
            label=e.catalog_id,
            captured=e.captured,
            image=(loaded.get(e.safe_name) if e.captured and e.safe_name else None),
        )
        for e in entries
    ]
    counts = life_list_summary(entries)
    n_captured, n_total = counts["messier_captured"], counts["messier_total"]
    image = build_life_list_grid(
        cells,
        title=grid_title(n_captured, n_total),
        subtitle=grid_subtitle(n_captured, n_total),
    )
    if image is None:
        raise HTTPException(
            status_code=404,
            detail="Capture one of the Messier objects and your grid is ready to share.")
    buf = io.BytesIO()
    save_display_jpeg(image, buf, quality=92)
    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Content-Disposition": 'attachment; filename="my-messier-grid.jpg"'},
    )
