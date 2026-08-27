"""My life list — which of the famous objects have I actually captured?

Every beginner knows the Messier list; capturing all 110 is *the* classic
milestone. The app already ranks what is up *tonight* (:mod:`seestack.nightplan`)
and tracks integration on *one* target, but nothing told the owner what their
**collection** looks like: 110 Messier objects (plus the curated popular NGC/IC
we bundle) with the ones they already have lit up and the rest as a to-shoot
list. That turns a pile of folders into a journey.

This module is the pure, offline half: match the bundled catalog against the
library's registered targets and say, per object, whether it has been captured
and which target holds it. No network, no new data — the catalog is already
bundled, and the targets table already carries the plate-solved centre.

Read-only and side-effect free, so it is safe to call on every page load.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from seestack.io.library import _angular_separation_deg
from seestack.nightplan import CatalogObject

#: How close a target's plate-solved centre must sit to a catalog object's
#: coordinates before we claim the owner has captured it.
#:
#: One Seestar frame is roughly 1.3° × 0.7°, so 0.35° is comfortably *inside* a
#: single frame: an object that matches is genuinely in the picture, while a
#: different object a frame's width away cannot be falsely claimed. Erring small
#: is the right way round — telling someone they have M65 when they pointed at
#: M66 next door would make the whole list untrustworthy, whereas a miss just
#: leaves one tile grey until they solve that target.
MATCH_RADIUS_DEG = 0.35


@dataclass(frozen=True)
class LifeListEntry:
    """One catalog object and whether the owner has captured it."""

    catalog_id: str
    #: The object's popular name ("Crab Nebula"), or ``""`` for the many
    #: catalog entries that have none — the UI falls back to the id.
    name: str
    type: str
    con: str
    ra_deg: float
    dec_deg: float
    size_arcmin: float | None
    blurb: str
    captured: bool
    #: The target holding it, when captured — the safe name is what every
    #: ``/api/targets/{safe}`` route resolves, so a tile can link straight to
    #: the picture. Both ``None`` when it hasn't been captured.
    safe_name: str | None = None
    target_name: str | None = None
    #: How far the matched target's centre sits from the catalog position, in
    #: degrees. ``None`` when not captured. Useful for "is this really it?".
    sep_deg: float | None = None


def _sort_key(catalog_id: str) -> tuple[int, int, str]:
    """Messier first in numeric order, then everything else alphabetically.

    ``M9`` must come before ``M10``, which a plain string sort gets wrong — and
    a beginner reads the list as "M1, M2, M3…", so numeric order is the only one
    that looks right. Anything unparseable falls to the back rather than
    raising, so a future catalog entry can never break the page.
    """
    if catalog_id.startswith("M") and catalog_id[1:].isdigit():
        return (0, int(catalog_id[1:]), "")
    return (1, 0, catalog_id)


def is_messier(catalog_id: str) -> bool:
    """True for the 110 ``M<n>`` ids — the list a beginner is actually counting."""
    return catalog_id.startswith("M") and catalog_id[1:].isdigit()


def catalog_capture_status(
    catalog: Sequence[CatalogObject],
    targets: Iterable[Any],
    *,
    radius_deg: float = MATCH_RADIUS_DEG,
) -> list[LifeListEntry]:
    """Match every catalog object against the library's targets.

    ``targets`` is any iterable of objects carrying ``name``, ``safe_name``,
    ``ra_deg``, ``dec_deg`` and ``n_frames`` — :class:`seestack.io.library.
    TargetEntry` is the real one, but it is duck-typed so this stays a pure
    function that can be tested without a database.

    A target counts only when it has been **plate-solved** (it needs a centre to
    match on) and actually holds frames. A registered-but-empty target is not a
    capture: the point of the list is "have I got a picture of this?", and
    lighting up a tile for a folder with nothing in it would be a lie the owner
    would catch immediately.

    When several targets sit near one object — the Seestar writes a new folder
    per night, so three nights on M31 is three targets until they are merged —
    the **closest** wins, so the list shows one capture rather than an arbitrary
    one. Returned in display order: Messier numerically, then the rest.
    """
    solved = [
        t for t in targets
        if getattr(t, "ra_deg", None) is not None
        and getattr(t, "dec_deg", None) is not None
        and int(getattr(t, "n_frames", 0) or 0) > 0
    ]

    entries: list[LifeListEntry] = []
    for obj in catalog:
        best = None
        best_sep = float(radius_deg)
        for t in solved:
            sep = _angular_separation_deg(
                obj.ra_deg, obj.dec_deg, float(t.ra_deg), float(t.dec_deg),
            )
            if sep <= best_sep:
                best_sep, best = sep, t
        entries.append(LifeListEntry(
            catalog_id=obj.id,
            name=obj.name,
            type=obj.type,
            con=obj.con,
            ra_deg=obj.ra_deg,
            dec_deg=obj.dec_deg,
            size_arcmin=obj.size_arcmin,
            blurb=obj.blurb,
            captured=best is not None,
            safe_name=(getattr(best, "safe_name", None) if best is not None else None),
            target_name=(getattr(best, "name", None) if best is not None else None),
            sep_deg=(round(best_sep, 4) if best is not None else None),
        ))

    entries.sort(key=lambda e: _sort_key(e.catalog_id))
    return entries


#: How many of a constellation's catalog objects may still be missing before we
#: stop calling it "nearly finished".
#:
#: At 2 the nudge stays a genuine "one or two more and it's done"; at 3+ it turns
#: into a to-do list, and a beginner who is told they're "close" to five separate
#: constellations learns to ignore the line. One is the best version of the
#: sentence ("you're one away from finishing Orion"), so the ranking below always
#: puts the closest constellation first.
MAX_MISSING_FOR_NEARLY = 2


@dataclass(frozen=True)
class ConstellationProgress:
    """How far through one constellation's catalog objects the owner is."""

    #: IAU three-letter abbreviation, as the catalog spells it ("Ori").
    con: str
    captured: int
    total: int
    #: The objects still to get, in catalog display order.
    missing: tuple[LifeListEntry, ...]


def nearly_complete_constellations(
    entries: Sequence[LifeListEntry],
    *,
    max_missing: int = MAX_MISSING_FOR_NEARLY,
    min_captured: int = 1,
) -> list[ConstellationProgress]:
    """Which constellations is the owner nearly finished with?

    The life list answers "how many of the 110 have I got?", which is a number
    you look at. This answers "what should I point at *next*?", which is a plan —
    and "you're one object away from finishing Orion" is a far better reason to
    go outside than "you're on 42 of 110".

    Counts every bundled catalog object (Messier *and* the curated popular
    NGC/IC) in each constellation, because a beginner reads "finishing Orion" as
    the whole famous set, not the Messier subset. Constellations the owner has
    not started (``captured < min_captured``) are excluded — those aren't
    "nearly done", they're just unshot sky, which is what the existing "start
    something new tonight" suggestions are for. Entries with no constellation
    recorded are skipped rather than grouped under a blank name.

    Returned closest-first: fewest missing, then most already captured, then
    alphabetically so the order is stable run to run. Pure and offline.
    """
    by_con: dict[str, list[LifeListEntry]] = {}
    for entry in entries:
        con = (entry.con or "").strip()
        if not con:
            continue
        by_con.setdefault(con, []).append(entry)

    out: list[ConstellationProgress] = []
    for con, group in by_con.items():
        missing = tuple(e for e in group if not e.captured)
        captured = len(group) - len(missing)
        if captured < min_captured or not missing or len(missing) > max_missing:
            continue
        out.append(ConstellationProgress(
            con=con, captured=captured, total=len(group), missing=missing,
        ))
    out.sort(key=lambda p: (len(p.missing), -p.captured, p.con))
    return out


def life_list_summary(entries: Sequence[LifeListEntry]) -> dict[str, int]:
    """Counts for the plain-language header ("You've captured 42 of 110…").

    Messier and the curated NGC/IC are counted separately because they mean
    different things to a beginner: the Messier list is a *finite, famous*
    milestone worth a progress bar, while the popular-NGC set is a suggestion
    list we happen to bundle and could grow at any time.
    """
    messier = [e for e in entries if is_messier(e.catalog_id)]
    other = [e for e in entries if not is_messier(e.catalog_id)]
    return {
        "messier_captured": sum(1 for e in messier if e.captured),
        "messier_total": len(messier),
        "other_captured": sum(1 for e in other if e.captured),
        "other_total": len(other),
    }
