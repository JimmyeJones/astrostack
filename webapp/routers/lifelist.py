"""My life list — the famous objects you've captured, and the ones still to get.

``GET /api/life-list`` returns the bundled catalog (110 Messier + the curated
popular NGC/IC) with each object marked captured or not, matched against the
library's plate-solved target centres, plus the counts for the plain-language
header.

Everything about it is read-only and offline: the catalog ships with the app,
and the match reads only the target registry — no project DB is opened and no
network is touched, so it is cheap enough to answer on every page load.

Distinct from ``/api/plan/tonight`` (what is *up tonight*) and from a target's
own progress (one object's integration): this is the **collection** view — the
"which of the 110 have I got?" question a beginner is actually counting.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from seestack.lifelist import catalog_capture_status, is_messier, life_list_summary
from seestack.nightplan import load_catalog
from webapp import deps

router = APIRouter(tags=["life-list"])


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
