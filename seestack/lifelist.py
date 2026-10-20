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

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from seestack.io.library import _angular_separation_deg
from seestack.nightplan import CatalogObject

#: How close a target's plate-solved centre must sit to a catalog object's
#: coordinates before we claim the owner has captured it — the **floor**, used
#: when the target's own field is not known (see :func:`match_radius_deg`).
#:
#: Sized for the *smallest* Seestar field — an S50 frame is roughly 1.3° × 0.7°,
#: so 0.35° is comfortably inside it: an object that matches is genuinely in the
#: picture, while a different object a frame's width away cannot be falsely
#: claimed. Erring small is the right way round — telling someone they have M65
#: when they pointed at M66 next door would make the whole list untrustworthy,
#: whereas a miss just leaves one tile grey until they solve that target.
MATCH_RADIUS_DEG = 0.35

#: The share of a target's own half-field (half its measured short side) inside
#: which an object counts as captured.
#:
#: The registry centre is a median over dithered, drifting subs, not the exact
#: middle of any one of them, so the radius stays well inside the frame's
#: inscribed circle rather than on its edge. On the owner's S30 (≈2.1° × 1.2°)
#: that is ≈0.48° — enough for M32, 0.40° from M31 and plainly in his M31 field,
#: which the S50-sized floor left grey. On an S50 it is ≈0.29°, under the floor,
#: so an S50 library matches exactly as before. A mosaic whose panels are known
#: is judged against the panels themselves instead (:func:`footprint_covers`),
#: and the rest of the half-field — ``1 - FIELD_MATCH_FRACTION`` of it — is the
#: most it asks an object to sit inside them by.
FIELD_MATCH_FRACTION = 0.8

#: The least a mosaic's object must sit inside its panels by, in degrees (one
#: arc-minute), however tightly the panels' subs were pointed: the panel centre
#: is still a median, and a catalog position is the middle of an object.
MIN_PANEL_MARGIN_DEG = 1.0 / 60.0

#: How many points on the margin circle :func:`footprint_covers` checks besides
#: the object itself. At 16 they sit at most ≈0.05° apart (an S30's widest
#: ≈0.12° margin), so a gap between panels narrower than that is the most the
#: test can step over — far below a panel step; the gaps a real mosaic leaves
#: are whole panels.
_MARGIN_POINTS = 16

#: The widest step between the position angles a panel's rectangle is tested at,
#: across the rotation range its subs were taken at.
_ROTATION_STEP_DEG = 5.0


def match_radius_deg(target: Any, floor_deg: float = MATCH_RADIUS_DEG) -> float:
    """How far from ``target``'s centre an object may sit and still be in its picture.

    The target's own measured field (``frame_short_deg``, stamped on the registry
    from its plate solve) when known — :data:`FIELD_MATCH_FRACTION` of half its
    short side — and never less than ``floor_deg``, so a target whose field is
    unknown, or an S50's, matches exactly as it always has.
    """
    short = getattr(target, "frame_short_deg", None)
    try:
        short_f = float(short) if short is not None else None
    except (TypeError, ValueError):
        short_f = None
    if short_f is None or not math.isfinite(short_f) or short_f <= 0:
        return float(floor_deg)
    return max(float(floor_deg), FIELD_MATCH_FRACTION * short_f / 2.0)


@dataclass(frozen=True)
class _Panel:
    ra_deg: float
    dec_deg: float
    #: The position angles (radians) the panel's rectangle must hold the point at.
    angles: tuple[float, ...]
    #: How far inside the mosaic an object this panel holds must sit (degrees):
    #: this panel's *own* sub spread, floored and capped (see :func:`parse_footprint`).
    margin_deg: float = MIN_PANEL_MARGIN_DEG


@dataclass(frozen=True)
class Footprint:
    """A mosaic's panels on the sky, parsed from the registry's ``panel_footprint``."""

    half_w_deg: float
    half_h_deg: float
    panels: tuple[_Panel, ...]
    #: The widest panel's margin (degrees). :func:`footprint_covers` asks each
    #: panel's own :attr:`_Panel.margin_deg`; this is the summary.
    margin_deg: float


def parse_footprint(raw: Any) -> Footprint | None:
    """The registry's ``panel_footprint`` JSON as a :class:`Footprint`, or ``None``.

    ``None`` for anything malformed, non-finite or out of range, so a damaged
    registry value falls back to today's single-circle match rather than raising
    on the page or claiming sky on a nonsense rectangle.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        data = json.loads(raw)
        w, h = float(data["w_deg"]), float(data["h_deg"])
        rows = data["panels"]
        if not isinstance(rows, list) or not rows:
            return None
        rows_ok = []
        for row in rows:
            ra, dec, lo, hi, sp = (float(v) for v in row)
            if not all(math.isfinite(v) for v in (ra, dec, lo, hi, sp)):
                return None
            if not -90.0 <= dec <= 90.0 or hi < lo or sp < 0:
                return None
            n = max(1, math.ceil(min(hi - lo, 180.0) / _ROTATION_STEP_DEG))
            angles = tuple(math.radians(lo + (min(hi - lo, 180.0)) * k / n)
                           for k in range(n + 1))
            rows_ok.append((ra % 360.0, dec, angles, sp))
    except (ValueError, TypeError, KeyError, IndexError):
        return None
    if not (math.isfinite(w) and math.isfinite(h)) or not (0 < w <= 20 and 0 < h <= 20):
        return None
    # Clear of the edges by as far as the panel's own subs spread around its
    # centre — so the object is in (nearly) every sub of the panel holding it,
    # the same ask the single field's circle makes — and never by more than that
    # circle leaves of the half-field. **Per panel:** one re-pointed panel's
    # spread is no reason to doubt an object a tight panel holds in every sub
    # (a single mosaic-wide peak greyed exactly that, Scout 2026-10-20).
    cap = (1.0 - FIELD_MATCH_FRACTION) * min(w, h) / 2.0
    panels = tuple(_Panel(ra, dec, angles, min(cap, max(MIN_PANEL_MARGIN_DEG, sp)))
                   for ra, dec, angles, sp in rows_ok)
    return Footprint(
        half_w_deg=w / 2.0, half_h_deg=h / 2.0, panels=panels,
        margin_deg=max(p.margin_deg for p in panels),
    )


def _tangent_offset_deg(ra: float, dec: float, ra0: float,
                        dec0: float) -> tuple[float, float] | None:
    """Gnomonic offsets (east, north), in degrees, of a point about a frame centre;
    ``None`` for a point on the far side of the sky."""
    d, d0 = math.radians(dec), math.radians(dec0)
    dra = math.radians(ra - ra0)
    cosc = math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(dra)
    if cosc <= 0:
        return None
    xi = math.cos(d) * math.sin(dra) / cosc
    eta = (math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(dra)) / cosc
    return math.degrees(xi), math.degrees(eta)


def _in_panel(ra: float, dec: float, panel: _Panel, fp: Footprint) -> bool:
    """Is the point inside the panel's frame at **every** angle its subs were
    taken at? The axes are those of a solved sub whose ``CROTA2`` is the angle,
    with ``CDELT1 < 0`` as a Seestar header carries."""
    off = _tangent_offset_deg(ra, dec, panel.ra_deg, panel.dec_deg)
    if off is None:
        return False
    xi, eta = off
    for rot in panel.angles:
        c, s = math.cos(rot), math.sin(rot)
        if abs(xi * c + eta * s) > fp.half_w_deg or abs(eta * c - xi * s) > fp.half_h_deg:
            return False
    return True


def _offset_point(ra: float, dec: float, dist_deg: float,
                  bearing: float) -> tuple[float, float]:
    """The point ``dist_deg`` from ``(ra, dec)`` along ``bearing`` (radians, east of north)."""
    d, delta = math.radians(dec), math.radians(dist_deg)
    d2 = math.asin(max(-1.0, min(1.0, math.sin(d) * math.cos(delta)
                                 + math.cos(d) * math.sin(delta) * math.cos(bearing))))
    dra = math.atan2(math.sin(bearing) * math.sin(delta) * math.cos(d),
                     math.cos(delta) - math.sin(d) * math.sin(d2))
    return (ra + math.degrees(dra)) % 360.0, math.degrees(d2)


def footprint_covers(fp: Footprint, ra: float, dec: float) -> bool:
    """Is ``(ra, dec)`` inside the mosaic, by at least the footprint's margin?

    The object must sit in some panel, and :data:`_MARGIN_POINTS` points on a
    circle of *that panel's* :attr:`_Panel.margin_deg` around it must each fall
    inside *some* panel — so an object near where panels meet counts (the overlap
    covers it), while one in the quadrant an L-shaped mosaic never shot, or just
    past the outer edge, does not. The margin is the dither and drift the holding
    panel's subs spread over around its median centre (see
    :func:`parse_footprint`); any panel that holds the object at its own margin
    is enough.
    """
    for holder in fp.panels:
        if not _in_panel(ra, dec, holder, fp):
            continue
        points = [
            _offset_point(ra, dec, holder.margin_deg, 2.0 * math.pi * k / _MARGIN_POINTS)
            for k in range(_MARGIN_POINTS)
        ]
        if all(any(_in_panel(pra, pdec, p, fp) for p in fp.panels)
               for pra, pdec in points):
            return True
    return False


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
    one. Each target is judged against its own field (:func:`match_radius_deg`),
    so a wide-field target can hold a neighbour a narrow one could not — and a
    mosaic whose panels the registry knows (``panel_footprint``) against those
    panels (:func:`footprint_covers`), so it holds what any panel holds and
    never the sky of a panel that was not shot.
    Returned in display order: Messier numerically, then the rest.
    """
    solved = [
        t for t in targets
        if getattr(t, "ra_deg", None) is not None
        and getattr(t, "dec_deg", None) is not None
        and int(getattr(t, "n_frames", 0) or 0) > 0
    ]

    radii = [match_radius_deg(t, radius_deg) for t in solved]
    footprints = [parse_footprint(getattr(t, "panel_footprint", None)) for t in solved]
    # Beyond this distance from a mosaic's centre no panel can reach, so the
    # per-panel test is skipped for every object not near it.
    reaches = [
        None if fp is None else max(
            _angular_separation_deg(p.ra_deg, p.dec_deg, float(t.ra_deg), float(t.dec_deg))
            for p in fp.panels
        ) + math.hypot(fp.half_w_deg, fp.half_h_deg)
        for t, fp in zip(solved, footprints, strict=True)
    ]
    entries: list[LifeListEntry] = []
    for obj in catalog:
        best = None
        best_sep = 0.0
        for t, r, fp, reach in zip(solved, radii, footprints, reaches, strict=True):
            sep = _angular_separation_deg(
                obj.ra_deg, obj.dec_deg, float(t.ra_deg), float(t.dec_deg),
            )
            if fp is None:
                inside = sep <= r
            else:
                inside = sep <= reach and footprint_covers(fp, obj.ra_deg, obj.dec_deg)
            if inside and (best is None or sep <= best_sep):
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
