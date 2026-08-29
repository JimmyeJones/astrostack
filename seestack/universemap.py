"""Your universe — the objects you have photographed, placed in true 3D.

The Sky Map answers *"where did I point the scope?"*: every picture on the same
imaginary dome, direction only. This answers a different question — **"how far
out is each of these things, compared to the others?"** Two smudges a finger's
width apart on the sky can be a nebula a thousand light-years off and a galaxy
sixty million light-years behind it, and nothing in the app has ever shown that.

Pure, offline and free of any webapp import: it takes the targets the owner has
actually captured, looks each one up in the bundled deep-sky catalog, and returns
a **radial coordinate** per object plus the distance shells to draw around them.
The renderer just multiplies each object's direction vector by that radius.

Three rules keep it honest — they are the whole reason this module exists rather
than the placement being done ad hoc in the viewer:

  * **Never guess a distance.** A target with no vetted ``distance_ly`` in the
    bundled catalog is *not* placed at a made-up depth; it comes back in
    :attr:`UniverseMap.unplaced` so the viewer can say "these are yours too, we
    just don't have a distance for them" rather than silently dropping them. This
    is the same discipline :mod:`seestack.lighttravel` already uses.
  * **Log-scaled depth, always.** Real distances here span 444 ly to 83 Mly —
    more than five decades. On a linear scale every nebula in the collection
    collapses into one dot beside Andromeda and the map says nothing. The log
    scale is what keeps near and far structure legible at the same time, which is
    exactly why the "fly through your universe" maps a beginner has seen all use
    one.
  * **Say where the numbers come from.** The owner's own data decides *which*
    objects are here and *which way* they lie (their captured target list and its
    plate-solved positions). The *distance* is a published catalog fact — no
    single amateur scope can measure it — and :data:`PROVENANCE` is the sentence
    that says so, so the map can't be mistaken for a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from seestack.lighttravel import friendly_light_years
from seestack.nightplan import CatalogObject
from seestack.objectinfo import identify_object

#: The plain-language provenance line. Rendered next to the map, never omitted —
#: see the third rule in the module docstring.
PROVENANCE = (
    "Your own pictures decide which objects are here and which way they lie. "
    "The distance to each one comes from a published catalogue — that is a "
    "measurement no backyard telescope can make."
)

#: The smallest span, in decades, the depth scale is ever compressed into. A
#: collection that happens to sit inside one decade would otherwise be stretched
#: across the whole scene and imply a spread it hasn't got.
_MIN_DECADES = 1.0

#: Fraction of the log span left empty at each end, so the nearest object is
#: clearly off the origin and the furthest is clearly inside the outer shell.
_PAD_FRAC = 0.15

#: Most distance shells to draw. More than this and the labels collide.
_MAX_SHELLS = 6


@dataclass(frozen=True)
class CapturedTarget:
    """One target the owner has captured, as the map's input."""

    safe: str
    name: str
    ra_deg: float | None = None
    dec_deg: float | None = None


@dataclass(frozen=True)
class UniverseObject:
    """A captured target placed in depth, ready to render."""

    safe: str
    name: str               # the owner's own target name, as the library has it
    object_id: str          # catalog designation, e.g. "M31"
    object_name: str        # catalog common name, "" if it has none
    type: str               # plain-language type, e.g. "galaxy"
    ra_deg: float
    dec_deg: float
    distance_ly: float
    distance_text: str      # "2.5 million ly"
    years_text: str         # "2.5 million years" — how long the light travelled
    depth: float            # 0..1 radial coordinate on the log scale


@dataclass(frozen=True)
class UniverseShell:
    """One labelled distance shell — the map's scale reference."""

    distance_ly: float
    depth: float
    label: str


@dataclass(frozen=True)
class UnplacedTarget:
    """A captured target that has no vetted distance, and why."""

    safe: str
    name: str
    reason: str


@dataclass(frozen=True)
class UniverseMap:
    """Everything the viewer needs to draw the owner's slice of the universe."""

    objects: tuple[UniverseObject, ...] = ()
    shells: tuple[UniverseShell, ...] = ()
    unplaced: tuple[UnplacedTarget, ...] = ()
    near_ly: float = 0.0     # distance at depth 0 (the scale's inner bound)
    far_ly: float = 0.0      # distance at depth 1 (the scale's outer bound)
    provenance: str = PROVENANCE


def _log_bounds(distances: list[float]) -> tuple[float, float]:
    """Inner/outer bounds of the log scale, in log10 light-years.

    Widened to :data:`_MIN_DECADES` when the collection is tighter than that, then
    padded at both ends so no object lands exactly on a bound.
    """
    lo = math.log10(min(distances))
    hi = math.log10(max(distances))
    if hi - lo < _MIN_DECADES:
        mid = (lo + hi) / 2.0
        lo, hi = mid - _MIN_DECADES / 2.0, mid + _MIN_DECADES / 2.0
    pad = _PAD_FRAC * (hi - lo)
    return lo - pad, hi + pad


def _depth(distance_ly: float, lo: float, hi: float) -> float:
    """Where ``distance_ly`` sits on the 0..1 log scale spanned by ``lo``/``hi``."""
    span = hi - lo
    if span <= 0:  # pragma: no cover — _log_bounds always widens to a real span
        return 0.5
    return min(1.0, max(0.0, (math.log10(distance_ly) - lo) / span))


def _shells(lo: float, hi: float, distances: list[float]) -> tuple[UniverseShell, ...]:
    """Labelled decade shells inside the scale, or the collection's own extremes.

    Round decades (1,000 ly / 10,000 ly / 1 million ly …) are the rungs a reader
    already understands, so they are preferred. A collection tight enough to hold
    fewer than two of them gets its own nearest and furthest object instead — a
    scale reference with one rung tells you nothing about spacing. (A collection
    of *one* object is the exception that proves it: there is no spacing to show,
    so it gets a single rung at its own distance and the caption beside the map
    says nothing about steps.)
    """
    first = math.ceil(lo)
    # Never draw a rung beyond the furthest thing the owner has actually shot:
    # the padding exists to keep that object clear of the scene's edge, not to
    # buy an empty shell that makes the collection look shallower than it is.
    last = min(math.floor(hi), math.floor(math.log10(max(distances))))
    decades = [10.0 ** k for k in range(first, last + 1)]
    if len(decades) > _MAX_SHELLS:
        # Thin evenly rather than dropping the far end — the outermost rung is
        # the one that gives "far" its felt sense.
        step = math.ceil(len(decades) / _MAX_SHELLS)
        decades = decades[::step]
    if len(decades) < 2:
        decades = sorted({min(distances), max(distances)})
    return tuple(
        UniverseShell(distance_ly=d, depth=_depth(d, lo, hi),
                      label=friendly_light_years(d))
        for d in decades
    )


def build_universe_map(
    targets: list[CapturedTarget] | tuple[CapturedTarget, ...],
    *,
    catalog: tuple[CatalogObject, ...] | None = None,
) -> UniverseMap:
    """Place ``targets`` in depth by their catalog distance.

    Targets the bundled catalog can't identify — or identifies without a vetted
    ``distance_ly`` — are returned under :attr:`UniverseMap.unplaced` rather than
    guessed into the scene. With nothing placeable at all the result is an empty
    map (no shells, no bounds), which the viewer renders as its empty state.
    """
    identified: list[tuple[CapturedTarget, object]] = []
    unplaced: list[UnplacedTarget] = []
    for t in targets:
        info = identify_object(t.name, t.ra_deg, t.dec_deg, catalog=catalog)
        if info is None:
            unplaced.append(UnplacedTarget(
                safe=t.safe, name=t.name,
                reason="not in the built-in catalogue, so there's no distance for it",
            ))
            continue
        if info.light_travel is None:
            unplaced.append(UnplacedTarget(
                safe=t.safe, name=t.name,
                reason="the catalogue has no distance for this one",
            ))
            continue
        identified.append((t, info))

    if not identified:
        return UniverseMap(unplaced=tuple(unplaced))

    distances = [info.light_travel.distance_ly for _t, info in identified]
    lo, hi = _log_bounds(distances)
    objects = tuple(
        UniverseObject(
            safe=t.safe,
            name=t.name,
            object_id=info.id,
            object_name=info.name,
            type=info.type,
            # The catalog position, not the solved centre: this map is about
            # *which object* is out there and how far, so all of a target's
            # pictures belong at the one place the object actually is.
            ra_deg=info.ra_deg,
            dec_deg=info.dec_deg,
            distance_ly=info.light_travel.distance_ly,
            distance_text=friendly_light_years(info.light_travel.distance_ly),
            years_text=info.light_travel.years,
            depth=_depth(info.light_travel.distance_ly, lo, hi),
        )
        for t, info in identified
    )
    # Nearest first: the natural reading order for a depth map, and it makes the
    # list beside the scene double as a "how far out have I got?" ladder.
    objects = tuple(sorted(objects, key=lambda o: o.distance_ly))
    return UniverseMap(
        objects=objects,
        shells=_shells(lo, hi, distances),
        unplaced=tuple(unplaced),
        near_ly=10.0 ** lo,
        far_ly=10.0 ** hi,
    )
