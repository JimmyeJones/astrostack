"""Tonight — an offline deep-sky observability planner.

Given an observer location and a moment in time, rank deep-sky targets by how
*observable* they are during tonight's dark window: how high they climb, how
long they spend above a usable altitude, and how much a bright, nearby Moon will
wash them out. It answers the pre-capture question "what's worth pointing the
Seestar at tonight?" — the complement to the post-capture stack/edit pipeline.

Everything here is **offline and deterministic**: pure ``astropy`` (already a
dependency) over bundled catalogs (``data/messier.json`` plus a curated set of
popular non-Messier NGC/IC targets in ``data/deepsky_popular.json``). No network,
no heavy dependency. Every entry point takes the reference time explicitly, so a
fixed date + site always yields the same plan (which is what the tests pin).

Design notes
------------
* The dark window is astronomical twilight (Sun below −18°). If the site never
  gets that dark tonight (short summer nights at high latitude) it degrades to
  nautical (−12°), then to Sun-below-horizon, so the planner still returns a
  usable window rather than nothing. ``None`` only when the Sun never sets.
* Coordinates are catalog J2000 (ICRS); transforming to Alt/Az at the real
  observation time lets astropy handle precession/refraction. The bundled
  coordinates are accurate to a fraction of a degree — ample for ranking, which
  only cares about altitude and window length.
* This module never imports from :mod:`webapp` (engine layer stays pure).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from seestack.framing import (
    FramingHint,
    MosaicPlan,
    RecentreNudge,
    framing_hint,
    mosaic_plan,
)
from seestack.target_difficulty import DifficultyHint, target_difficulty

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
# Bundled deep-sky catalogs, loaded and concatenated in order. Messier first (its
# ids/names are canonical), then a curated set of popular non-Messier NGC/IC
# targets so "start something new" can suggest the well-known objects a Seestar
# owner actually shoots (Double Cluster, Veil, North America, …). Static files,
# no network. A later file never overrides an id an earlier one already defined.
_CATALOG_FILES = ("messier.json", "deepsky_popular.json")

# Altitude thresholds (deg) for the dark window, tried in order. Astronomical
# dark is ideal; the fallbacks keep short summer nights usable rather than empty.
_DARK_THRESHOLDS = (-18.0, -12.0, -6.0, -0.833)

# Curated "showpiece" whitelist for the "what should I shoot next?" suggester
# (:func:`suggest_targets`). These are the famous, bright, large crowd-pleasers a
# beginner Seestar owner actually enjoys — deliberately *not* the whole catalog,
# so a discovery suggestion is always something genuinely easy and rewarding
# rather than a faint 12th-magnitude smudge. Spread across the sky (galaxies,
# nebulae and clusters at a range of right ascensions) so something here is
# well-placed on any clear night, north or south. Ids must match the bundled
# catalogs exactly; any id not present is simply skipped, so the list is safe to
# curate independently of the catalog files.
_SHOWPIECE_IDS = frozenset({
    # Galaxies
    "M31", "M33", "M51", "M81", "M82", "M101", "M104", "M63", "M106",
    "NGC 253", "NGC 4565", "NGC 891",
    # Nebulae
    "M42", "M8", "M20", "M16", "M17", "M27", "M57", "M97",
    "NGC 7000", "NGC 6992", "NGC 7293", "NGC 7635", "IC 1805", "IC 5070", "NGC 3372",
    # Star clusters
    "M13", "M45", "M44", "M11", "M22", "M4", "M92", "NGC 869", "NGC 457", "M52",
})


def _configure_iers_offline() -> None:
    """Keep all time/earth-orientation maths offline and non-fatal.

    Without this astropy may try to *download* the IERS-A table (blocked/slow on
    a headless NAS) and, for dates past the bundled IERS-B table, *raise* instead
    of extrapolating. Our sub-degree ranking tolerates the extrapolation, so we
    disable the download and downgrade the past-table error to a silent
    extrapolation. Idempotent; called before any ``Time`` conversion.
    """
    from astropy.utils import iers

    iers.conf.auto_download = False
    iers.conf.iers_degraded_accuracy = "ignore"
    # The bundled IERS-A predictive table goes "stale" after auto_max_age days
    # (default 30). Once a deployed image's astropy data ages past that — or when
    # planning a date >30 days out — astropy *raises* ("predictive values that are
    # more than 30.0 days old") rather than use the stale table, which would 500
    # the planner on an offline NAS. Disable the staleness check: the IERS
    # correction is sub-arcsecond, far below this planner's degree-level ranking.
    iers.conf.auto_max_age = None


@dataclass(frozen=True)
class Observer:
    """Where the telescope is. Elevation is metres above sea level."""

    lat_deg: float
    lon_deg: float
    elevation_m: float = 0.0

    def earth_location(self):  # noqa: ANN201 — astropy EarthLocation
        from astropy import units as u
        from astropy.coordinates import EarthLocation

        return EarthLocation(
            lat=self.lat_deg * u.deg,
            lon=self.lon_deg * u.deg,
            height=self.elevation_m * u.m,
        )


@dataclass(frozen=True)
class HorizonProfile:
    """An azimuth→minimum-unobstructed-altitude mask (trees / buildings / house).

    ``points`` is a tuple of ``(azimuth_deg, min_altitude_deg)`` samples; the
    lowest *clear* altitude at any azimuth is linear-interpolated between them,
    wrapping around 360°. An **empty** profile means a flat, unobstructed horizon
    — the planner then uses only the numeric ``min_altitude_deg`` floor, exactly
    as before this feature existed. Build one from user input with
    :meth:`from_pairs`, which sanitises and orders the points.
    """

    points: tuple[tuple[float, float], ...] = ()

    @classmethod
    def from_pairs(cls, pairs) -> HorizonProfile:  # noqa: ANN001
        """Sanitise raw ``[[az, alt], …]`` input into a stable profile.

        Drops malformed / non-finite entries, wraps azimuth into ``[0, 360)``,
        clamps altitude into ``[0, 90]``, de-duplicates repeated azimuths (keeping
        the *taller* obstruction — a tree is a tree), and sorts by azimuth so
        :meth:`altitude_at` can interpolate.
        """
        import math

        cleaned: dict[float, float] = {}
        for pair in pairs or ():
            try:
                az = float(pair[0]) % 360.0
                alt = float(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            if not (math.isfinite(az) and math.isfinite(alt)):
                continue
            alt = max(0.0, min(90.0, alt))
            az = round(az, 3)
            cleaned[az] = max(alt, cleaned.get(az, 0.0))
        return cls(points=tuple(sorted(cleaned.items())))

    def is_empty(self) -> bool:
        return not self.points

    def altitude_at(self, az_deg):  # noqa: ANN001, ANN201
        """Interpolated obstruction altitude(s) at the given azimuth(s), in deg.

        Accepts a scalar or an array; returns the same shape. An empty profile
        reports 0° everywhere (nothing blocks the sky).
        """
        az = np.asarray(az_deg, dtype=float) % 360.0
        if not self.points:
            return np.zeros_like(az)
        azs = np.array([p[0] for p in self.points], dtype=float)
        alts = np.array([p[1] for p in self.points], dtype=float)
        # ``period`` makes np.interp wrap 350°→10° through the seam correctly.
        return np.interp(az, azs, alts, period=360.0)


@dataclass(frozen=True)
class CatalogObject:
    """One bundled deep-sky target."""

    id: str
    name: str
    ra_deg: float
    dec_deg: float
    type: str
    con: str
    # Major-axis angular size in arcminutes, when the catalog records it — used by
    # the "will it fit in one frame?" framing hint (:mod:`seestack.framing`).
    # ``None`` for the many entries without a vetted size (we never guess a size).
    size_arcmin: float | None = None
    # Minor-axis angular size in arcminutes, vetted for the objects that are
    # bigger than one Seestar frame — the "how big a mosaic?" panel-count plan
    # (:func:`seestack.framing.mosaic_plan`) needs it, because an elongated
    # object needs far fewer panels than its major axis alone implies. ``None``
    # everywhere else, where the plan falls back to a square (worst-case) box.
    size_minor_arcmin: float | None = None
    # A plain-language, beginner-friendly one-liner about the object ("what am I
    # looking at?"), curated for the popular targets; ``""`` when the catalog has
    # none (the object-info card then reads fine from type + constellation alone).
    blurb: str = ""
    # Distance in light-years — which *is* the light-travel time in years, so it
    # drives the "how far did you see?" line (:mod:`seestack.lighttravel`).
    # ``None`` for an entry without a vetted distance (we never guess one).
    distance_ly: float | None = None


@dataclass
class DarkWindow:
    """Tonight's usable-darkness interval (UTC) and how it was defined."""

    start: datetime
    end: datetime
    # The Sun-altitude threshold (deg) that actually defined this window — −18 in
    # the normal case, a shallower fallback for short summer nights.
    sun_alt_threshold_deg: float

    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0


@dataclass
class MoonWindow:
    """When the Moon rises/sets *during* tonight's dark window (UTC ISO strings).

    The illuminated fraction and waxing/waning direction say *how bright* the Moon
    is and roughly *which half* of the night it disturbs; this pins the concrete
    time. ``set_utc`` is a setting crossing inside the dark window (the sky clears
    after it), ``rise_utc`` a rising crossing (the sky is clean before it). When
    the Moon never crosses the horizon during the darkness, exactly one of
    ``up_all_night`` / ``down_all_night`` is true and both times are ``None``.
    """

    rise_utc: str | None
    set_utc: str | None
    up_all_night: bool
    down_all_night: bool


@dataclass
class Observability:
    """How observable one target is over a given dark window."""

    max_altitude_deg: float
    transit_utc: datetime | None
    minutes_above_min_alt: float
    moon_separation_deg: float
    score: float  # 0..100, higher = better tonight
    # Share (0..1) of the target's *usable* window during which the Moon is above
    # the horizon — the same overlap that weights the score's Moon penalty. Lets
    # the UI explain *why* a bright-Moon night still ranked a target well (the
    # Moon was down while it was up). ``None`` when the target has no usable
    # window (score 0), so the UI shows no misleading cue.
    moon_up_fraction: float | None = None
    # The clock bounds of the target's usable window tonight — the first and last
    # sampled moment it clears the floor (and any horizon mask). These answer
    # "*when* tonight can I actually shoot this?", which the single transit time
    # can't: a target up for 7 h could clear the floor at 21:00 or not until 01:00.
    # Both ``None`` when the target is never usable. With a horizon mask a window
    # can have gaps; these are the *enclosing* bounds (``minutes_above_min_alt``
    # stays the honest usable total), so the common no-mask case is exact.
    usable_start_utc: datetime | None = None
    usable_end_utc: datetime | None = None


@dataclass
class PlannedTarget:
    """A catalog/library candidate plus its observability, for the API/UI."""

    id: str
    name: str
    ra_deg: float
    dec_deg: float
    type: str
    con: str
    already_targeted: bool
    max_altitude_deg: float
    transit_utc: str | None
    minutes_above_min_alt: float
    moon_separation_deg: float
    score: float
    # Share (0..1) of this target's usable window the Moon is above the horizon
    # (see :attr:`Observability.moon_up_fraction`); ``None`` when the target has
    # no usable window. Old backends omit it, so the UI treats absent as unknown.
    moon_up_fraction: float | None = None
    # Clock bounds (UTC ISO) of the usable window tonight — *when* the target is
    # shootable, complementing the peak ``transit_utc``. Both ``None`` when it's
    # never usable; old backends omit them. See :class:`Observability`.
    usable_start_utc: str | None = None
    usable_end_utc: str | None = None
    # Present only for library targets the user has already shot.
    target_safe: str | None = None
    frames_accepted: int | None = None
    total_exposure_s: float | None = None
    # The user's own integration goal for this target (seconds), when they set
    # one — so the row's readiness hint uses the same goal as every other screen.
    # ``None`` for a catalog row, for a target with no goal set, and on an older
    # backend; the per-object-type default then applies as before.
    goal_s: float | None = None
    # This target's recent productive pace (median kept integration per clear
    # night, seconds), so the row can say how many more clear nights would
    # finish it rather than only that it is "Nearly there". ``None`` for a
    # catalog row, for a target without enough night history, and on an older
    # backend — the row then falls back to the readiness badge as before.
    recent_pace_s: float | None = None
    # "Will it fit in one Seestar frame?" — major-axis size (arcmin) and the
    # verdict derived from it, for catalog candidates the bundled catalog has a
    # size for; ``None`` otherwise (library rows carry none — the Target page
    # already shows their framing, and a mosaic result would confuse the
    # single-frame catalog verdict). See :mod:`seestack.framing`.
    size_arcmin: float | None = None
    framing: FramingHint | None = None
    # "How big a mosaic?" — the panel grid this object's span needs, so the row
    # answers the question the framing hint provokes ("shoot it in mosaic mode"
    # → *how big a mosaic?*) while the user is still choosing what to point at.
    # ``None`` when it fits one frame or has no vetted size.
    mosaic: MosaicPlan | None = None
    # "How hard is this target for a Seestar?" — easy/moderate/challenging, so a
    # beginner sees the difficulty *while choosing* what to point at, not only
    # after they've shot it. For catalog candidates the vetted table/type-rule has
    # a verdict for; ``None`` otherwise (library rows and un-vetted objects carry
    # none). See :func:`seestack.target_difficulty.target_difficulty`.
    difficulty: DifficultyHint | None = None
    # "Last time it landed off-centre — nudge about 1.0° south before you start."
    # The framing advice from this target's newest finished picture, repeated
    # here because this is the screen someone is looking at *while pointing the
    # scope*, and the card that says it today is read the morning after.
    # Library rows only, and only when that picture really needs a re-point;
    # ``None`` otherwise and on an older backend. See
    # :func:`seestack.framing.recentre_nudge`.
    recentre_nudge: RecentreNudge | None = None


@dataclass
class NightPlan:
    """The full ranked plan the API returns."""

    generated_utc: str
    observer: dict
    dark_window: dict | None
    moon_illumination: float
    # Whether the Moon is waxing (sets in the evening) or waning (rises after
    # midnight) tonight — the illuminated fraction alone can't tell them apart.
    # ``None`` only when no location/plan could be computed.
    moon_waxing: bool | None
    min_altitude_deg: float
    # When the Moon rises/sets during tonight's dark window (or that it stays up /
    # down all night) — the concrete time to complement the phase. ``None`` only
    # when no dark window could be computed. See :class:`MoonWindow`.
    moon_window: dict | None = None
    # True when a non-empty horizon/tree mask shaped the usable windows below, so
    # the UI can explain that low-altitude obstructions were accounted for.
    horizon_active: bool = False
    targets: list[PlannedTarget] = field(default_factory=list)


def _load_catalog_file(path: Path) -> list[CatalogObject]:
    """Parse one bundled catalog JSON file into :class:`CatalogObject` records."""
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return [
        CatalogObject(
            id=o["id"], name=o.get("name", ""), ra_deg=float(o["ra_deg"]),
            dec_deg=float(o["dec_deg"]), type=o.get("type", ""), con=o.get("con", ""),
            size_arcmin=(float(o["size_arcmin"]) if o.get("size_arcmin") is not None
                         else None),
            size_minor_arcmin=(float(o["size_minor_arcmin"])
                               if o.get("size_minor_arcmin") is not None else None),
            blurb=o.get("blurb", ""),
            distance_ly=(float(o["distance_ly"]) if o.get("distance_ly") is not None
                         else None),
        )
        for o in raw["objects"]
    ]


@lru_cache(maxsize=1)
def load_catalog() -> tuple[CatalogObject, ...]:
    """Load the bundled deep-sky catalogs, concatenated (cached; static files).

    Messier plus a curated set of popular non-Messier NGC/IC targets (see
    ``_CATALOG_FILES``). Ids are de-duplicated across files — the first file to
    define an id wins — so a target can never appear twice in the plan.
    """
    objects: list[CatalogObject] = []
    seen: set[str] = set()
    for fname in _CATALOG_FILES:
        for obj in _load_catalog_file(_DATA_DIR / fname):
            if obj.id in seen:
                continue
            seen.add(obj.id)
            objects.append(obj)
    return tuple(objects)


def _times_grid(start: datetime, end: datetime, step_minutes: float):  # noqa: ANN202
    """A UTC ``Time`` array from ``start`` to ``end`` inclusive at a fixed step.

    The grid never leaves ``[start, end]``: the step count rounds *up* and the
    final stamp is clipped to ``end``, so a window whose length isn't a whole
    number of steps still gets a sample at its very end without sampling past it.
    (Rounding to the nearest step used to put the last stamp up to half a step
    *after* ``end`` — which surfaced as a planner telling you to keep shooting a
    couple of minutes after astronomical dark was over.) A window that *is* an
    exact multiple of the step is unchanged, sample for sample.
    """
    from astropy.time import Time

    total_min = max((end - start).total_seconds() / 60.0, step_minutes)
    # -1e-9: an exact multiple mustn't gain a spurious step to floating-point dust.
    n = int(math.ceil(total_min / step_minutes - 1e-9)) + 1
    stamps = [start + timedelta(minutes=step_minutes * i) for i in range(n)]
    if stamps[-1] > end > stamps[-2]:
        stamps[-1] = end
    return stamps, Time([s.astimezone(timezone.utc).replace(tzinfo=None) for s in stamps],
                        scale="utc")


def _sample_minutes(stamps: list[datetime], step_minutes: float) -> np.ndarray:
    """Minutes of the window each :func:`_times_grid` sample stands for.

    Every sample is worth one whole step except the last, which :func:`_times_grid`
    clips to the window end and which therefore stands for only what is left of a
    step. On a window that is an exact multiple of the step that remainder *is* a
    full step, so the weights are uniform and every total is unchanged.
    """
    weights = np.full(len(stamps), float(step_minutes), dtype=float)
    if len(stamps) >= 2:
        weights[-1] = min((stamps[-1] - stamps[-2]).total_seconds() / 60.0,
                          float(step_minutes))
    return weights


def _sun_altitudes(stamps_time, location):  # noqa: ANN001, ANN202
    from astropy.coordinates import AltAz, get_sun

    sun = get_sun(stamps_time)
    altaz = sun.transform_to(AltAz(obstime=stamps_time, location=location))
    return np.asarray(altaz.alt.deg, dtype=float)


def _dark_window_after_noon(location, t_noon: datetime) -> DarkWindow | None:  # noqa: ANN001
    """Widest astronomical-dark span in the 24 h *after* ``t_noon`` (a local noon).

    Scans local-noon → next local-noon so the night sits contiguously in the
    middle (never split across the array ends), then takes the widest contiguous
    span below the deepest reachable Sun-altitude threshold. Returns ``None`` when
    the Sun never drops far enough (high-summer/polar day).
    """
    stamps, times = _times_grid(t_noon, t_noon + timedelta(hours=24), 4.0)
    sun_alt = _sun_altitudes(times, location)

    for threshold in _DARK_THRESHOLDS:
        below = sun_alt < threshold
        if not below.any():
            continue
        # Widest contiguous run of "below".
        best_lo = best_hi = None
        best_len = 0
        i = 0
        n = len(below)
        while i < n:
            if below[i]:
                j = i
                while j + 1 < n and below[j + 1]:
                    j += 1
                if (j - i) >= best_len:
                    best_len, best_lo, best_hi = (j - i), i, j
                i = j + 1
            else:
                i += 1
        if best_lo is None:
            continue
        return DarkWindow(start=stamps[best_lo].astimezone(timezone.utc),
                          end=stamps[best_hi].astimezone(timezone.utc),
                          sun_alt_threshold_deg=threshold)
    return None  # Sun never sets tonight.


def _find_dark_window(observer: Observer, when_utc: datetime) -> DarkWindow | None:
    """Astronomical dark window that ``when_utc`` sits in, or the next one after it.

    Anchors on the local solar noon nearest ``when_utc`` and scans the darkness
    that *follows* that noon. But if ``when_utc`` falls before that noon — i.e. the
    caller is in the small hours or pre-dawn — they may still be *inside* the
    previous night's darkness (the one that began the evening before). In that case
    return that ongoing window rather than skipping ahead to tomorrow night, so a
    post-midnight user is told about the darkness they can still use *right now*.
    """
    _configure_iers_offline()
    location = observer.earth_location()

    ref = when_utc.astimezone(timezone.utc)
    # Local solar noon nearest the reference: highest Sun altitude in ±12 h.
    noon_stamps, noon_times = _times_grid(ref - timedelta(hours=12),
                                          ref + timedelta(hours=12), 15.0)
    noon_alt = _sun_altitudes(noon_times, location)
    t_noon = noon_stamps[int(np.argmax(noon_alt))]

    # When the reference is before the nearest noon (small hours / pre-dawn), the
    # user may still be inside the *previous* night's darkness; prefer that ongoing
    # window if ``when_utc`` hasn't passed its end yet.
    if ref < t_noon:
        prev = _dark_window_after_noon(location, t_noon - timedelta(hours=24))
        if prev is not None and ref < prev.end:
            return prev

    return _dark_window_after_noon(location, t_noon)


def moon_illumination(when_utc: datetime) -> float:
    """Illuminated fraction of the Moon's disk (0..1) at ``when_utc``.

    Geometric phase from the Sun–Moon elongation; location-independent to the
    precision we need, so no observer is required.
    """
    _configure_iers_offline()
    from astropy.coordinates import get_body, get_sun
    from astropy.time import Time

    t = Time(when_utc.astimezone(timezone.utc).replace(tzinfo=None), scale="utc")
    sun = get_sun(t)
    moon = get_body("moon", t)
    elong = sun.separation(moon).radian
    # Illuminated fraction = (1 + cos(phase_angle)) / 2; phase angle ≈ π − elong
    # for the Sun ≫ Moon distance ratio (adequate for a "how bright is it" cue).
    return float((1.0 + np.cos(np.pi - elong)) / 2.0)


def moon_is_waxing(when_utc: datetime) -> bool:
    """True if the Moon is waxing (growing) at ``when_utc``, else waning.

    The illuminated *fraction* alone can't tell a waxing from a waning Moon, but
    for planning it matters *when* the Moon is up: a **waxing** Moon leads the Sun
    across the sky and sets in the evening (so early-night targets are safe),
    while a **waning** Moon trails the Sun and rises after midnight (so late-night
    targets suffer). The two are distinguished by the Moon's ecliptic longitude
    relative to the Sun's: ``0 < (λ_moon − λ_sun) mod 360 < 180`` is waxing
    (new → full), the rest is waning (full → new). Offline and
    location-independent, like :func:`moon_illumination`.
    """
    _configure_iers_offline()
    from astropy.coordinates import GeocentricTrueEcliptic, get_body, get_sun
    from astropy.time import Time

    t = Time(when_utc.astimezone(timezone.utc).replace(tzinfo=None), scale="utc")
    ecl = GeocentricTrueEcliptic(equinox=t)
    sun_lon = float(get_sun(t).transform_to(ecl).lon.deg)
    moon_lon = float(get_body("moon", t).transform_to(ecl).lon.deg)
    return 0.0 < (moon_lon - sun_lon) % 360.0 < 180.0


def _moon_altitudes(stamps_time, location):  # noqa: ANN001, ANN202
    """Topocentric Moon altitude (deg) at each sampled time, for this observer."""
    from astropy.coordinates import AltAz, get_body

    moon = get_body("moon", stamps_time, location)
    altaz = moon.transform_to(AltAz(obstime=stamps_time, location=location))
    return np.asarray(altaz.alt.deg, dtype=float)


def _interp_crossing_iso(t0: datetime, t1: datetime, a0: float, a1: float) -> str:
    """UTC ISO string of the horizon crossing linearly interpolated between two
    samples (altitudes ``a0``→``a1`` straddling 0°), rounded to the nearest minute."""
    frac = 0.0 if a1 == a0 else float(np.clip(-a0 / (a1 - a0), 0.0, 1.0))
    cross = t0 + (t1 - t0) * frac
    cross = cross.astimezone(timezone.utc)
    # Round to the nearest whole minute — a "~23:40" cue needs no more precision.
    cross = (cross + timedelta(seconds=30)).replace(second=0, microsecond=0)
    return cross.isoformat()


def moon_window(observer: Observer, window: DarkWindow) -> MoonWindow:
    """Moon rise/set crossings *inside* tonight's dark window (see :class:`MoonWindow`).

    Samples the topocentric Moon altitude across the dark window on a 5-minute
    grid and reports the first setting and first rising crossing of the horizon
    (altitude 0°) within it. If the Moon stays above (or below) the horizon for
    the whole window it reports ``up_all_night`` (``down_all_night``) instead and
    leaves both times ``None`` — so the UI shows no misleading time. Offline and
    deterministic, like the rest of the planner.
    """
    _configure_iers_offline()
    location = observer.earth_location()
    stamps, times = _times_grid(window.start, window.end, 5.0)
    alt = _moon_altitudes(times, location)
    above = alt >= 0.0

    rise_utc: str | None = None
    set_utc: str | None = None
    for i in range(len(alt) - 1):
        a0, a1 = float(alt[i]), float(alt[i + 1])
        if a0 < 0.0 <= a1 and rise_utc is None:  # rising through the horizon
            rise_utc = _interp_crossing_iso(stamps[i], stamps[i + 1], a0, a1)
        elif a0 >= 0.0 > a1 and set_utc is None:  # setting through the horizon
            set_utc = _interp_crossing_iso(stamps[i], stamps[i + 1], a0, a1)

    up_all = bool(above.all())
    down_all = bool((~above).all())
    return MoonWindow(rise_utc=rise_utc, set_utc=set_utc,
                      up_all_night=up_all, down_all_night=down_all)


@dataclass
class MoonInterference:
    """A plain-language "is the Moon going to wash this out tonight?" readout for
    one target, evaluated at the darkest moment of tonight's dark window.

    The single biggest avoidable reason a beginner's faint-nebula night comes out
    disappointing is a bright Moon nearby flooding the sky background — and a
    non-expert has no intuition for it. This turns the ephemeris into one honest
    verdict + sentence. Offline and deterministic (see :func:`moon_interference`)."""

    # Illuminated fraction of the Moon's disk (0..1) tonight.
    illumination: float
    # Waxing (evening Moon, sets before midnight) vs waning (rises after midnight).
    waxing: bool
    # A friendly phase name ("Full Moon", "waxing crescent", …).
    phase_name: str
    # Topocentric Moon altitude at the darkest moment (deg); < 0 = below the
    # horizon, so it can't affect the shot however bright it is.
    moon_altitude_deg: float
    # Angular separation between the Moon and this target at that moment (deg).
    separation_deg: float
    # Coarse verdict: "good" (Moon down / thin / far) | "ok" | "poor" (bright & near).
    level: str
    # One plain-language sentence for the card.
    text: str
    # The darkest moment used for the readout (UTC ISO), so the UI can caption it.
    at_utc: str


def _moon_phase_name(illum: float, waxing: bool) -> str:
    """A friendly Moon-phase name from the illuminated fraction + waxing sense."""
    if illum < 0.02:
        return "New Moon"
    if illum > 0.98:
        return "Full Moon"
    if illum < 0.45:
        return "waxing crescent" if waxing else "waning crescent"
    if illum <= 0.55:
        return "first quarter" if waxing else "last quarter"
    return "waxing gibbous" if waxing else "waning gibbous"


def _moon_verdict(illum: float, moon_alt_deg: float, sep_deg: float) -> tuple[str, str]:
    """Blend illumination, Moon altitude and target separation into a coarse level
    + a plain-language sentence. Pure so it's unit-testable on its own."""
    pct = round(illum * 100)
    sep = round(sep_deg)
    if moon_alt_deg < 0:
        return "good", ("The Moon is below the horizon during tonight's dark hours, "
                        "so it won't wash out your shot.")
    if illum < 0.25:
        return "good", (f"Only a thin crescent Moon ({pct}% lit) is up tonight — it "
                        "adds very little skyglow.")
    if sep_deg >= 90:
        return "ok", (f"A {pct}%-lit Moon is up, but it's well away from this target "
                      f"(~{sep}° off), so it should be manageable.")
    if illum < 0.65:
        return "ok", (f"A {pct}%-lit Moon sits ~{sep}° from this target — you'll lose "
                      "some of the faintest detail, but bright targets are fine.")
    return "poor", (f"A bright {pct}%-lit Moon is only ~{sep}° from this target — faint "
                    "nebulae will wash out tonight. A bright galaxy, star cluster or "
                    "double star would show much better.")


def _moon_geometry(observer: Observer, ra_deg: float, dec_deg: float,
                   at: datetime) -> tuple[float, float, float]:
    """``(illuminated fraction, Moon altitude °, target separation °)`` at ``at``.

    The one place the Moon's position is turned into the three numbers every
    verdict is built from, so the forward-looking "tonight" readout and the
    backward-looking "was the Moon washing this out?" note can never disagree
    about the same instant. ``at`` must already be timezone-aware UTC."""
    _configure_iers_offline()
    from astropy import units as u
    from astropy.coordinates import AltAz, SkyCoord, get_body
    from astropy.time import Time

    illum = moon_illumination(at)
    location = observer.earth_location()
    t = Time(at.replace(tzinfo=None), scale="utc")
    moon = get_body("moon", t, location)
    moon_alt = float(moon.transform_to(AltAz(obstime=t, location=location)).alt.deg)
    # Transform the Moon into the target's ICRS frame before measuring separation,
    # so astropy doesn't warn about a direction-dependent transform (as the batch
    # observability path does).
    target = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    sep = float(target.separation(moon.icrs).deg)
    return illum, moon_alt, sep


@dataclass(frozen=True)
class SessionMoon:
    """"Was the Moon washing this out?" — a *retrospective* moonlight verdict.

    The planner already warns about the Moon **before** a night. Nothing told the
    beginner afterwards, so someone who shot a faint nebula under a full Moon saw
    a flat, low-contrast picture and concluded their gear or their editing was at
    fault. The real cause was the sky, and the fix — "shoot it again on a
    dark-Moon night" — is something the app knows and never said.

    Deliberately quiet: ``text`` is a finished sentence **only** when the Moon
    genuinely hurt this session (bright, up, and close). On a good or merely
    passable night it is ``None`` and the surface hides itself, so this can never
    become a nag. Never phrased as the user's fault."""

    # Illuminated fraction of the Moon's disk (0..1) at the session's midpoint.
    illumination: float
    # Topocentric Moon altitude then (deg); < 0 = below the horizon, so it can't
    # have affected the shot however bright it was.
    moon_altitude_deg: float
    # Angular separation between the Moon and the target then (deg).
    separation_deg: float
    # Coarse verdict, from the same table the forward-looking readout uses:
    # "good" | "ok" | "poor".
    level: str
    # The plain-language sentence, or None on anything but a "poor" night.
    text: str | None
    # The instant the readout describes (UTC ISO) — the session's midpoint.
    at_utc: str


def session_moon(observer: Observer, ra_deg: float, dec_deg: float,
                 start_utc: datetime, end_utc: datetime | None = None) -> SessionMoon:
    """How much the Moon washed out a session that has already been shot.

    Evaluated at the session's **midpoint** (``end_utc`` defaults to
    ``start_utc``, i.e. a single instant). A Seestar session runs for hours and
    the Moon moves ~0.5°/hour plus the sky's rotation, so no single sample is the
    whole truth — the midpoint is the honest one-number summary, and the verdict
    bands are coarse enough (bright/up/within 90°) that a couple of degrees never
    flips them.

    Pure apart from the ephemeris, offline, and deterministic, like the rest of
    the planner. Reuses :func:`_moon_verdict` so the retrospective note and
    tonight's warning grade the same sky the same way."""
    start = start_utc.astimezone(timezone.utc)
    end = (end_utc or start_utc).astimezone(timezone.utc)
    if end < start:
        start, end = end, start
    at = start + (end - start) / 2

    illum, moon_alt, sep = _moon_geometry(observer, ra_deg, dec_deg, at)
    level, _ = _moon_verdict(illum, moon_alt, sep)
    return SessionMoon(
        illumination=round(illum, 3),
        moon_altitude_deg=round(moon_alt, 1),
        separation_deg=round(sep, 1),
        level=level,
        text=_session_moon_text(illum, sep) if level == "poor" else None,
        at_utc=at.isoformat(),
    )


def _session_moon_text(illum: float, sep_deg: float) -> str:
    """The one sentence a Moon-hit session earns. Reassurance, not a verdict on
    the user: it names the cause, says it wasn't their setup, and points at the
    thing they can actually do about it."""
    return (
        f"A bright {round(illum * 100)}%-lit Moon was only ~{round(sep_deg)}° from "
        "this target while you were shooting, so the sky background is brighter and "
        "faint detail is harder to pull out. That's the sky, not your setup — the "
        "same target on a dark-Moon night will come out cleaner."
    )


def moon_interference(observer: Observer, ra_deg: float, dec_deg: float,
                      when_utc: datetime) -> MoonInterference:
    """How much the Moon will interfere with imaging ``(ra_deg, dec_deg)`` tonight.

    Evaluated at the **darkest moment of tonight's dark window** (the solar
    midnight after ``when_utc``, or the ongoing window if the caller is already in
    the small hours) — so the reading reflects the sky the user will actually shoot
    in, not the Moon's daytime position when the page happens to load. Falls back to
    ``when_utc`` itself when no dark window can be found (e.g. polar day). Offline
    and deterministic, like the rest of the planner."""
    window = _find_dark_window(observer, when_utc)
    at = (window.start + (window.end - window.start) / 2) if window is not None else when_utc
    at = at.astimezone(timezone.utc)

    illum, moon_alt, sep = _moon_geometry(observer, ra_deg, dec_deg, at)
    waxing = moon_is_waxing(at)

    level, text = _moon_verdict(illum, moon_alt, sep)
    return MoonInterference(
        illumination=round(illum, 3),
        waxing=waxing,
        phase_name=_moon_phase_name(illum, waxing),
        moon_altitude_deg=round(moon_alt, 1),
        separation_deg=round(sep, 1),
        level=level,
        text=text,
        at_utc=at.isoformat(),
    )


def _score(max_alt: float, minutes_above: float, dark_minutes: float,
           moon_sep: float, moon_illum: float, min_alt: float,
           moon_up_fraction: float = 1.0) -> float:
    """Blend altitude, usable-window fraction and a Moon penalty into 0..100.

    * Altitude: rewards a high transit (capped at 70° — above that adds nothing
      meaningful for a small scope).
    * Window: fraction of tonight's darkness the target clears ``min_alt``.
    * Moon: a bright Moon close to the target subtracts up to 40%; a faint or
      far Moon barely matters. ``moon_up_fraction`` is the share of the target's
      *usable* window during which the Moon is actually above the horizon — the
      penalty is scaled by it, so a bright Moon that has already set (or hasn't
      yet risen) while the target is observable does **not** dock the score. It
      defaults to 1.0 (Moon up throughout), which reproduces the old behaviour.
    """
    if minutes_above <= 0 or dark_minutes <= 0:
        return 0.0
    alt_cap = 70.0  # above this a small scope gains nothing meaningful
    if max_alt <= min_alt:
        alt_component = 0.0
    elif min_alt >= alt_cap:
        # The usable floor is already at/above the "good enough" altitude, so any
        # target that clears it is as high as scoring cares about (and the
        # ``alt_cap - min_alt`` denominator below would be zero/negative).
        alt_component = 1.0
    else:
        alt_component = float(np.clip((max_alt - min_alt) / (alt_cap - min_alt), 0.0, 1.0))
    window_component = float(np.clip(minutes_above / dark_minutes, 0.0, 1.0))
    base = 0.5 * alt_component + 0.5 * window_component
    return round(100.0 * base * (1.0 - moon_penalty(moon_sep, moon_illum,
                                              moon_up_fraction)), 1)


def moon_penalty(moon_sep_deg: float, moon_illum: float,
                 moon_up_fraction: float = 1.0) -> float:
    """0..0.4 "how much does the Moon spoil this target tonight?" factor.

    A bright Moon close to the target subtracts up to 40%; a faint or far one
    barely matters. ``moon_up_fraction`` is the share of the target's usable
    window during which the Moon is actually above the horizon, so a bright Moon
    that has already set (or hasn't yet risen) doesn't dock the score.

    Public and single-definition on purpose: both the whole-night plan score and
    the "point here right now" ranking apply the *same* penalty, so the two
    surfaces can never disagree about whether the Moon is in the way.
    """
    proximity = float(np.clip((60.0 - moon_sep_deg) / 60.0, 0.0, 1.0))
    return (0.4 * float(np.clip(moon_illum, 0.0, 1.0)) * proximity
            * float(np.clip(moon_up_fraction, 0.0, 1.0)))


def _observability_batch(ras_deg, decs_deg, observer: Observer, window: DarkWindow,
                         min_alt_deg: float, moon_illum: float,
                         horizon: HorizonProfile | None = None):  # noqa: ANN001, ANN202
    """Vectorised observability for many targets over one dark window.

    Returns a list of :class:`Observability`, one per input coordinate. When a
    non-empty ``horizon`` is given, a target only counts as *usable* at a moment
    when it clears **both** the numeric ``min_alt_deg`` floor and the obstruction
    altitude at its current azimuth — so a target hidden behind trees/buildings
    for part (or all) of the night has its usable window (and score) reduced.
    """
    from astropy import units as u
    from astropy.coordinates import AltAz, SkyCoord, get_body

    location = observer.earth_location()
    stamps, times = _times_grid(window.start, window.end, 5.0)
    # Minutes each sample stands for — a whole step except the last, which the
    # grid clips to the window end, so "how long is it usable?" can't credit time
    # past the end of darkness.
    sample_min = _sample_minutes(stamps, 5.0)
    altaz_frame = AltAz(obstime=times, location=location)

    coords = SkyCoord(ra=np.asarray(ras_deg) * u.deg,
                      dec=np.asarray(decs_deg) * u.deg, frame="icrs")
    # (n_targets, n_times) altitude + azimuth grids.
    altaz = coords[:, None].transform_to(altaz_frame[None, :])
    alt = np.atleast_2d(np.asarray(altaz.alt.deg, dtype=float))
    use_horizon = horizon is not None and not horizon.is_empty()
    az = np.atleast_2d(np.asarray(altaz.az.deg, dtype=float)) if use_horizon else None

    # Moon separation at the darkest moment (mid-window) — one representative sep.
    mid = stamps[len(stamps) // 2]
    from astropy.time import Time
    # Transform the Moon (GCRS) into the targets' ICRS frame before measuring
    # separation, so astropy doesn't warn about a direction-dependent transform.
    moon = get_body("moon", Time(mid.replace(tzinfo=None), scale="utc"), location).icrs
    moon_sep = coords.separation(moon).deg
    moon_sep = np.atleast_1d(np.asarray(moon_sep, dtype=float))

    # Whether the Moon is actually above the horizon at each sampled moment, so a
    # target's Moon penalty can be weighted by how much of *its* usable window the
    # Moon is up for (a bright Moon that has set, or not yet risen, shouldn't dock
    # a target that's only observable while the Moon is down).
    moon_up = _moon_altitudes(times, location) >= 0.0

    out: list[Observability] = []
    dark_minutes = window.duration_minutes
    for i in range(alt.shape[0]):
        row = alt[i]
        imax = int(np.argmax(row))
        max_alt = float(row[imax])
        # Effective usable floor per sample: the numeric min-altitude, raised to
        # the tree/building obstruction at each moment's azimuth when a horizon
        # mask is set. ``max_altitude_deg`` stays the honest physical peak.
        floor = np.maximum(min_alt_deg, horizon.altitude_at(az[i])) if use_horizon else min_alt_deg
        usable = row >= floor
        n_usable = int(np.count_nonzero(usable))
        minutes_above = float(sample_min[usable].sum())
        transit = stamps[imax].astimezone(timezone.utc) if minutes_above > 0 else None
        # Enclosing clock bounds of the usable window (first→last sample above the
        # floor) — "when tonight can I shoot this?". None when never usable.
        usable_idx = np.flatnonzero(usable)
        if usable_idx.size:
            usable_start = stamps[int(usable_idx[0])].astimezone(timezone.utc)
            usable_end = stamps[int(usable_idx[-1])].astimezone(timezone.utc)
        else:
            usable_start = usable_end = None
        sep = float(moon_sep[i])
        # Share of the target's usable samples during which the Moon is up. For
        # scoring, 1.0 (full penalty, as before) when it has no usable window —
        # the score is 0 there anyway, so it can't matter; for the reported field
        # we surface ``None`` in that case so the UI shows no misleading cue.
        moon_up_fraction = (float(np.count_nonzero(usable & moon_up)) / n_usable
                            if n_usable else None)
        score = _score(max_alt, minutes_above, dark_minutes, sep, moon_illum,
                       min_alt_deg, 1.0 if moon_up_fraction is None else moon_up_fraction)
        out.append(Observability(
            max_altitude_deg=round(max_alt, 1),
            transit_utc=transit,
            minutes_above_min_alt=round(minutes_above, 1),
            moon_separation_deg=round(sep, 1),
            score=score,
            moon_up_fraction=(None if moon_up_fraction is None
                              else round(moon_up_fraction, 3)),
            usable_start_utc=usable_start,
            usable_end_utc=usable_end,
        ))
    return out


@dataclass(frozen=True)
class LibraryTarget:
    """A target the user has already shot (annotated onto the plan)."""

    safe: str
    name: str
    ra_deg: float
    dec_deg: float
    frames_accepted: int
    total_exposure_s: float
    # Catalog-resolved classification (best-effort), so an already-targeted row
    # carries the same object type/constellation as the un-targeted catalog rows
    # and the Dashboard "Target progress" card. Empty when unknown.
    object_type: str = ""
    con: str = ""
    # The user's own integration goal for this target (accepted-sub exposure,
    # seconds), or None when they haven't set one and the per-object-type default
    # applies. Carried so the planner's "have I shot enough of this?" row hint
    # answers with the goal the *user* set, exactly as the Target page and the
    # Dashboard overview do — a target the owner deliberately wants 12 h of must
    # not be labelled "try something new" at 7 h just because the type default is
    # 6 h. Purely annotation: it never affects scoring or ranking.
    goal_s: float | None = None
    # This target's recent productive pace — median kept integration per clear
    # night, in seconds — or None when there isn't enough history to call it a
    # pace. Carried for the same reason as ``goal_s``: it turns the planner's
    # vague "Nearly there" into the figure the user is actually choosing on
    # ("~1 more night finishes this"), in the same words the Dashboard and the
    # Target page use. Purely annotation: it never affects scoring or ranking.
    recent_pace_s: float | None = None
    # "Last time this landed off-centre — nudge a little south before you start."
    # The framing advice from this target's newest finished picture. It exists
    # today only on the card a beginner reads the morning after, by which point
    # the next clear night is a week away and it has been forgotten; the moment
    # it is worth anything is while they are pointing the scope. ``None`` for a
    # target that framed well, has no stacked picture yet, or isn't confidently
    # identified — never a guessed direction. Purely annotation: it never affects
    # scoring or ranking.
    recentre_nudge: RecentreNudge | None = None


def plan_tonight(observer: Observer, when_utc: datetime, *,
                 min_altitude_deg: float = 30.0,
                 library_targets: list[LibraryTarget] | None = None,
                 include_catalog: bool = True,
                 horizon: HorizonProfile | None = None) -> NightPlan:
    """Rank tonight's targets for ``observer`` at ``when_utc``.

    Combines the bundled catalog ("not yet targeted") with the user's library
    targets ("already targeted", annotated with what they've captured). A library
    target that matches a catalog object by position is shown once, as the
    already-targeted entry. Returns targets sorted best-first (score desc), then
    highest transit; targets that never clear ``min_altitude_deg`` tonight sort
    to the bottom with score 0.

    When ``horizon`` is a non-empty :class:`HorizonProfile`, a target's usable
    window (and hence its score) is trimmed to the times it is *above* the local
    tree/building obstruction at its azimuth, not merely above ``min_altitude_deg``
    — so an object that transits high but only clears the trees briefly ranks
    below one that sits lower in an open part of the sky. An empty/absent horizon
    keeps the flat-floor behaviour unchanged.
    """
    _configure_iers_offline()
    library_targets = library_targets or []
    window = _find_dark_window(observer, when_utc)
    illum = moon_illumination(when_utc)

    horizon_active = horizon is not None and not horizon.is_empty()
    plan = NightPlan(
        generated_utc=when_utc.astimezone(timezone.utc).isoformat(),
        observer=asdict(observer),
        dark_window=None,
        moon_illumination=round(illum, 3),
        moon_waxing=moon_is_waxing(when_utc),
        min_altitude_deg=min_altitude_deg,
        horizon_active=horizon_active,
    )
    if window is None:
        return plan  # Sun never sets — nothing to plan.
    plan.dark_window = {
        "start_utc": window.start.isoformat(),
        "end_utc": window.end.isoformat(),
        "duration_minutes": round(window.duration_minutes, 1),
        "sun_alt_threshold_deg": window.sun_alt_threshold_deg,
    }
    plan.moon_window = asdict(moon_window(observer, window))

    # Build the candidate list: library targets first, then catalog objects not
    # already covered by a library target (matched within ~0.75° on the sky).
    lib_coords = [(t.ra_deg, t.dec_deg) for t in library_targets
                  if t.ra_deg is not None and t.dec_deg is not None]

    def _covered(ra: float, dec: float) -> bool:
        return any(_angular_sep_deg(ra, dec, lra, ldec) < 0.75 for lra, ldec in lib_coords)

    ras: list[float] = []
    decs: list[float] = []
    meta: list[dict] = []
    for t in library_targets:
        if t.ra_deg is None or t.dec_deg is None:
            continue
        ras.append(t.ra_deg)
        decs.append(t.dec_deg)
        meta.append({"kind": "library", "target": t})
    if include_catalog:
        for obj in load_catalog():
            if _covered(obj.ra_deg, obj.dec_deg):
                continue
            ras.append(obj.ra_deg)
            decs.append(obj.dec_deg)
            meta.append({"kind": "catalog", "obj": obj})

    if not ras:
        return plan

    obs = _observability_batch(ras, decs, observer, window, min_altitude_deg, illum,
                               horizon=horizon)
    for m, o in zip(meta, obs, strict=True):
        if m["kind"] == "library":
            t: LibraryTarget = m["target"]
            plan.targets.append(PlannedTarget(
                id=t.safe, name=t.name, ra_deg=t.ra_deg, dec_deg=t.dec_deg,
                type=t.object_type, con=t.con, already_targeted=True,
                max_altitude_deg=o.max_altitude_deg,
                transit_utc=o.transit_utc.isoformat() if o.transit_utc else None,
                minutes_above_min_alt=o.minutes_above_min_alt,
                moon_separation_deg=o.moon_separation_deg, score=o.score,
                moon_up_fraction=o.moon_up_fraction,
                usable_start_utc=o.usable_start_utc.isoformat() if o.usable_start_utc else None,
                usable_end_utc=o.usable_end_utc.isoformat() if o.usable_end_utc else None,
                target_safe=t.safe, frames_accepted=t.frames_accepted,
                total_exposure_s=round(t.total_exposure_s, 1),
                goal_s=t.goal_s,
                recent_pace_s=t.recent_pace_s,
                recentre_nudge=t.recentre_nudge,
            ))
        else:
            obj: CatalogObject = m["obj"]
            plan.targets.append(PlannedTarget(
                id=obj.id, name=obj.name, ra_deg=obj.ra_deg, dec_deg=obj.dec_deg,
                type=obj.type, con=obj.con, already_targeted=False,
                max_altitude_deg=o.max_altitude_deg,
                transit_utc=o.transit_utc.isoformat() if o.transit_utc else None,
                minutes_above_min_alt=o.minutes_above_min_alt,
                moon_separation_deg=o.moon_separation_deg, score=o.score,
                moon_up_fraction=o.moon_up_fraction,
                usable_start_utc=o.usable_start_utc.isoformat() if o.usable_start_utc else None,
                usable_end_utc=o.usable_end_utc.isoformat() if o.usable_end_utc else None,
                size_arcmin=obj.size_arcmin,
                framing=framing_hint(obj.size_arcmin),
                mosaic=mosaic_plan(obj.size_arcmin, obj.size_minor_arcmin),
                difficulty=target_difficulty(obj.id, obj.type),
            ))

    plan.targets.sort(key=lambda p: (-p.score, -p.max_altitude_deg))
    return plan


@dataclass
class NextObservingWindow:
    """When a specific target is next well-placed in a night's dark window (UTC).

    The forward-looking companion to :func:`plan_tonight`: instead of ranking
    *what* to shoot tonight, it answers "when should I next point the scope at
    *this* object?" over the coming nights. Times are UTC; the caller formats
    them for the viewer.
    """

    # Bounds of the night's astronomical-dark window (may be clipped to "now" for
    # the first night so a window already mostly past isn't over-promised).
    dark_start: datetime
    dark_end: datetime
    # When the target actually clears the altitude floor within that darkness —
    # the concrete "shoot between" interval. ``None`` only defensively (a window
    # is only returned when the target is usable, so these are normally set).
    usable_start: datetime | None
    usable_end: datetime | None
    max_altitude_deg: float
    minutes_above_min_alt: float
    moon_illumination: float
    # Share (0..1) of the usable window the Moon is above the horizon, or ``None``
    # when unknown — mirrors :attr:`Observability.moon_up_fraction`.
    moon_up_fraction: float | None
    score: float


def upcoming_dark_windows(
    observer: Observer, start_utc: datetime, nights: int,
) -> list[tuple[str, DarkWindow]]:
    """The next ``nights`` astronomical-dark windows, each labelled with the local
    calendar date of the **evening** it belongs to (``"2026-09-04"``).

    Extracted from :func:`next_observing_windows` so anything that walks the nights
    ahead — one target's next sessions, or the whole library's week — anchors,
    clips and labels them identically. A night with no darkness at all (high summer
    at latitude) is simply absent from the list; the labels are therefore *not*
    guaranteed contiguous, which is the honest answer.

    The scan is anchored at local solar noon on ``start_utc``'s date, so
    :func:`_find_dark_window` (which takes the darkness *following* its reference)
    lands on that calendar night regardless of the observer's longitude — local
    noon in UTC is 12:00 − lon/15 h, east of Greenwich being earlier in UTC. A
    caller in the small hours is *inside* the night that began the previous
    evening, so the anchor moves back a day and one extra night is scanned to keep
    the same forward horizon. A window already entirely past is dropped; one
    partially past is clipped to ``start_utc``, so "tonight" only ever promises
    time still to come.
    """
    _configure_iers_offline()
    start_utc = start_utc.astimezone(timezone.utc)
    d = start_utc.date()
    anchor = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc) - timedelta(
        hours=observer.lon_deg / 15.0)
    shift = 1 if start_utc < anchor else 0
    anchor -= timedelta(days=shift)

    out: list[tuple[str, DarkWindow]] = []
    for offset in range(max(0, nights) + shift):
        # The anchor *is* local noon of that evening, so its own date is the local
        # calendar date the night is named after ("Thursday night" = Thu evening).
        evening = anchor + timedelta(days=offset)
        window = _find_dark_window(observer, evening)
        if window is None:
            continue  # Sun never sets that night (high summer) — nothing to plan.
        if window.end <= start_utc:
            continue
        if window.start < start_utc:
            window = DarkWindow(start=start_utc, end=window.end,
                                sun_alt_threshold_deg=window.sun_alt_threshold_deg)
            if window.duration_minutes <= 0:
                continue
        out.append((evening.date().isoformat(), window))
    return out


def next_observing_windows(
    observer: Observer,
    ra_deg: float,
    dec_deg: float,
    *,
    start_utc: datetime,
    min_altitude_deg: float = 30.0,
    horizon: HorizonProfile | None = None,
    nights: int = 14,
    want: int = 3,
    min_usable_minutes: float = 45.0,
) -> list[NextObservingWindow]:
    """The next few nights this target is well-placed in a dark window.

    Walks up to ``nights`` calendar nights forward from ``start_utc`` and, for
    each, finds that night's astronomical-dark window (:func:`_find_dark_window`)
    and how observable the single target is over it (:func:`_observability_batch`).
    A night qualifies when the target clears ``min_altitude_deg`` for at least
    ``min_usable_minutes`` of the darkness. Returns the first ``want`` qualifying
    nights, chronologically (best time to shoot next, and the couple after it when
    the goal needs more than one session).

    Purely offline and read-only, like the rest of the planner. The first night's
    window is clipped to ``start_utc`` so a night already mostly gone isn't
    reported as a fresh opportunity; if a whole night's darkness is already past,
    or the target never rises high enough, that night is simply skipped.
    """
    out: list[NextObservingWindow] = []
    for _label, window in upcoming_dark_windows(observer, start_utc, nights):
        illum = moon_illumination(window.start + (window.end - window.start) / 2)
        o = _observability_batch([ra_deg], [dec_deg], observer, window,
                                 min_altitude_deg, illum, horizon=horizon)[0]
        if o.minutes_above_min_alt < min_usable_minutes:
            continue
        out.append(NextObservingWindow(
            dark_start=window.start,
            dark_end=window.end,
            usable_start=o.usable_start_utc,
            usable_end=o.usable_end_utc,
            max_altitude_deg=o.max_altitude_deg,
            minutes_above_min_alt=o.minutes_above_min_alt,
            moon_illumination=round(illum, 3),
            moon_up_fraction=o.moon_up_fraction,
            score=o.score,
        ))
        if len(out) >= max(1, want):
            break
    return out


#: How many of the library's targets :func:`plan_week` will scan. The per-night
#: work is one vectorised batch over all of them, so the cost is dominated by the
#: number of *nights*, not targets — but the cap keeps a library of hundreds from
#: turning a planning card into a slow request.
WEEK_MAX_TARGETS = 40

#: Nights ahead :func:`plan_week` looks by default — "this week", the horizon a
#: weekend imager actually plans over.
WEEK_NIGHTS = 7


@dataclass
class WeekTargetPick:
    """One target's showing on one night of the week ahead."""

    safe: str
    name: str
    # When it clears the altitude floor within that night's darkness.
    usable_start_utc: str | None
    usable_end_utc: str | None
    minutes_above_min_alt: float
    max_altitude_deg: float
    #: Share (0..1) of the usable window the Moon is up, or ``None`` when unknown.
    moon_up_fraction: float | None
    score: float


@dataclass
class WeekNight:
    """One night of the week ahead: its darkness, its Moon, and what to point at."""

    #: Local calendar date of the **evening** the night belongs to (``2026-09-04``).
    date: str
    dark_start_utc: str
    dark_end_utc: str
    dark_minutes: float
    moon_illumination: float
    #: How many of the scanned targets are usable at all that night — so the UI can
    #: say "3 other options" without carrying every one of them.
    n_usable: int
    #: The best-placed target, or ``None`` when nothing clears the floor for long
    #: enough (a night worth telling the user to skip).
    best: WeekTargetPick | None


@dataclass
class TargetBestNight:
    """A target's single best night in the range — "M31: Thursday"."""

    safe: str
    name: str
    date: str
    minutes_above_min_alt: float
    score: float


@dataclass
class WeekPlan:
    """The output of :func:`plan_week` — the whole library, over the nights ahead."""

    generated_utc: str
    observer: dict
    min_altitude_deg: float
    horizon_active: bool
    nights_scanned: int
    #: Nights that actually have darkness, chronologically. Not necessarily
    #: contiguous or ``nights_scanned`` long (high-summer nights have none).
    nights: list[WeekNight] = field(default_factory=list)
    #: Every scanned target that is usable on at least one of those nights, best
    #: night first — "your M31 night is Thursday, your M42 night is Saturday".
    targets: list[TargetBestNight] = field(default_factory=list)
    #: Targets considered (after the position filter and the cap), so the UI can
    #: say honestly that it looked at some but not all of a big library.
    n_targets_considered: int = 0
    n_targets_with_position: int = 0


def plan_week(
    observer: Observer,
    library_targets: list[LibraryTarget],
    *,
    start_utc: datetime,
    nights: int = WEEK_NIGHTS,
    min_altitude_deg: float = 30.0,
    horizon: HorizonProfile | None = None,
    min_usable_minutes: float = 45.0,
    max_targets: int = WEEK_MAX_TARGETS,
) -> WeekPlan:
    """Which of *your own* targets to point at, on which of the next few nights.

    The cross-target, multi-night view the other planners don't give:
    :func:`plan_tonight` ranks everything for tonight, and
    :func:`next_observing_windows` plans one target forward. This walks the same
    nights once and asks, for each, *which of the targets you've already started
    is best placed* — the question a beginner who only gets out on clear weekends
    actually has ("your best shot this week is M31 on Thursday").

    Deliberately the **library only**, never the catalog: this is "finish what
    I've got", and :func:`suggest_targets` already covers discovery. Targets with
    no known position are skipped (they can't be planned), and at most
    ``max_targets`` are scanned — :data:`WEEK_MAX_TARGETS`, reported back on the
    result so the UI can be honest about it.

    When that cap *does* bite, the targets it keeps are the ones with the most
    integration already on them. The library arrives ordered by name
    (``Library.list_targets`` is ``ORDER BY name COLLATE NOCASE``), so a plain head
    slice would plan a big library's week around the first forty objects
    alphabetically and silently drop the project the owner has actually spent
    nights on — "finish what I've got" answered with the wrong "got". Total
    exposure is the honest measure of investment, with the accepted-frame count and
    then ``safe`` breaking ties so the choice is deterministic. Under the cap the
    set is the whole library either way, and the returned lists are sorted by
    placement regardless, so nothing about an ordinary install's answer moves.

    One vectorised observability batch per night over all targets at once, so the
    cost scales with ``nights``, not with the size of the library. Purely offline
    and read-only, like the rest of the planner.
    """
    positioned = sorted(
        (t for t in library_targets if t.ra_deg is not None and t.dec_deg is not None),
        key=lambda t: (-(t.total_exposure_s or 0.0), -(t.frames_accepted or 0), t.safe),
    )
    considered = positioned[:max(0, max_targets)]
    plan = WeekPlan(
        generated_utc=start_utc.astimezone(timezone.utc).isoformat(),
        observer=asdict(observer),
        min_altitude_deg=min_altitude_deg,
        horizon_active=horizon is not None and not horizon.is_empty(),
        nights_scanned=max(0, nights),
        n_targets_considered=len(considered),
        n_targets_with_position=len(positioned),
    )
    if not considered:
        return plan

    ras = [float(t.ra_deg) for t in considered]
    decs = [float(t.dec_deg) for t in considered]
    # safe → its best showing so far, as (score, minutes, date, name).
    best_by_target: dict[str, TargetBestNight] = {}

    for label, window in upcoming_dark_windows(observer, start_utc, nights):
        illum = moon_illumination(window.start + (window.end - window.start) / 2)
        obs = _observability_batch(ras, decs, observer, window, min_altitude_deg,
                                   illum, horizon=horizon)
        usable = [(t, o) for t, o in zip(considered, obs, strict=True)
                  if o.minutes_above_min_alt >= min_usable_minutes]
        # Best-first by score, then by how long it's up; ``safe`` last so two
        # equally-placed targets order deterministically rather than by dict order.
        usable.sort(key=lambda p: (-p[1].score, -p[1].minutes_above_min_alt, p[0].safe))

        for t, o in usable:
            prev = best_by_target.get(t.safe)
            if prev is None or (o.score, o.minutes_above_min_alt) > (
                    prev.score, prev.minutes_above_min_alt):
                best_by_target[t.safe] = TargetBestNight(
                    safe=t.safe, name=t.name, date=label,
                    minutes_above_min_alt=o.minutes_above_min_alt,
                    score=o.score,
                )

        pick = None
        if usable:
            t, o = usable[0]
            pick = WeekTargetPick(
                safe=t.safe, name=t.name,
                usable_start_utc=o.usable_start_utc.isoformat() if o.usable_start_utc else None,
                usable_end_utc=o.usable_end_utc.isoformat() if o.usable_end_utc else None,
                minutes_above_min_alt=o.minutes_above_min_alt,
                max_altitude_deg=o.max_altitude_deg,
                moon_up_fraction=o.moon_up_fraction,
                score=o.score,
            )
        plan.nights.append(WeekNight(
            date=label,
            dark_start_utc=window.start.isoformat(),
            dark_end_utc=window.end.isoformat(),
            dark_minutes=round(window.duration_minutes, 1),
            moon_illumination=round(illum, 3),
            n_usable=len(usable),
            best=pick,
        ))

    plan.targets = sorted(
        best_by_target.values(),
        key=lambda b: (b.date, -b.score, -b.minutes_above_min_alt, b.safe))
    return plan


@dataclass
class SuggestedTarget:
    """A not-yet-captured showpiece that's well-placed tonight (for the API/UI).

    The output of :func:`suggest_targets` — the "what should I shoot *new*
    tonight?" companion to :func:`plan_tonight` (which ranks *everything*,
    including the library) and :func:`next_observing_windows` (which plans *one*
    known target forward). Carries the friendly catalog blurb so the UI can say
    *what* the object is in plain language, plus tonight's observability so it can
    say *when* and *how high*.
    """

    id: str
    name: str
    ra_deg: float
    dec_deg: float
    type: str
    con: str
    blurb: str
    max_altitude_deg: float
    transit_utc: str | None
    minutes_above_min_alt: float
    moon_separation_deg: float
    moon_up_fraction: float | None
    usable_start_utc: str | None
    usable_end_utc: str | None
    score: float
    size_arcmin: float | None = None
    framing: FramingHint | None = None
    # The panel grid this object's span needs, for the same reason the planner
    # row carries one; ``None`` when it fits one frame or has no vetted size.
    mosaic: MosaicPlan | None = None
    # "How hard is this target for a Seestar?" — so the discovery suggestion shows
    # difficulty next to the framing hint. ``None`` for un-vetted objects. See
    # :func:`seestack.target_difficulty.target_difficulty`.
    difficulty: DifficultyHint | None = None


def suggest_targets(
    observer: Observer,
    when_utc: datetime,
    *,
    library_coords: list[tuple[float, float]] | None = None,
    min_altitude_deg: float = 30.0,
    limit: int = 3,
    horizon: HorizonProfile | None = None,
    min_usable_minutes: float = 45.0,
) -> list[SuggestedTarget]:
    """Suggest a few not-yet-captured showpiece targets well-placed tonight.

    Answers the single most common beginner question — "what's a good, easy thing
    to point at tonight?" — that the existing planning surfaces don't: they all
    plan a target you're *already* working. This filters the curated showpiece
    whitelist (:data:`_SHOWPIECE_IDS`) to the famous crowd-pleasers you have **not**
    already captured, keeps only those genuinely well-placed in tonight's dark
    window (clearing ``min_altitude_deg`` for at least ``min_usable_minutes``), and
    returns the best ``limit`` — sorted best-first by the same altitude/window/Moon
    blend the other cards use.

    ``library_coords`` are the ``(ra_deg, dec_deg)`` of targets the user has already
    shot; a showpiece within ~0.75° of any of them is treated as "already have it"
    and dropped (position match, so it's robust to however the user named the
    folder). Purely offline and read-only, like the rest of the planner; returns an
    empty list when the Sun never sets, nothing clears the floor, or every
    showpiece is already in the library — so the UI simply self-hides.
    """
    library_coords = library_coords or []

    def _covered(ra: float, dec: float) -> bool:
        return any(_angular_sep_deg(ra, dec, lra, ldec) < 0.75
                   for lra, ldec in library_coords)

    by_id = {obj.id: obj for obj in load_catalog()}
    candidates = [by_id[cid] for cid in _SHOWPIECE_IDS if cid in by_id]
    candidates = [o for o in candidates if not _covered(o.ra_deg, o.dec_deg)]
    return well_placed_tonight(
        observer, when_utc, candidates,
        min_altitude_deg=min_altitude_deg, limit=limit, horizon=horizon,
        min_usable_minutes=min_usable_minutes,
    )


def well_placed_tonight(
    observer: Observer,
    when_utc: datetime,
    objects: Sequence[CatalogObject],
    *,
    min_altitude_deg: float = 30.0,
    limit: int | None = None,
    horizon: HorizonProfile | None = None,
    min_usable_minutes: float = 45.0,
) -> list[SuggestedTarget]:
    """Rank any set of catalog objects by how well-placed they are tonight.

    The shared engine behind :func:`suggest_targets` (which feeds it the curated
    showpieces the user hasn't shot) and any other surface that has *already*
    chosen which objects it cares about and only needs "…and is one of them up
    tonight?" — e.g. the objects missing from a nearly-finished constellation.

    Keeps only objects genuinely usable in tonight's dark window (clearing
    ``min_altitude_deg`` for at least ``min_usable_minutes``) and returns them
    best-first by the same altitude/window/Moon blend every other planning card
    uses. ``limit=None`` returns all of them. Purely offline and read-only;
    returns an empty list when the Sun never sets, nothing clears the floor, or
    ``objects`` is empty — so a caller's card simply self-hides.
    """
    _configure_iers_offline()
    if not objects:
        return []
    window = _find_dark_window(observer, when_utc)
    if window is None:
        return []  # Sun never sets — nothing to plan.

    illum = moon_illumination(when_utc)
    obs = _observability_batch(
        [o.ra_deg for o in objects], [o.dec_deg for o in objects],
        observer, window, min_altitude_deg, illum, horizon=horizon,
    )

    out: list[SuggestedTarget] = []
    for obj, o in zip(objects, obs, strict=True):
        if o.minutes_above_min_alt < min_usable_minutes:
            continue  # not up long enough tonight to be worth suggesting
        out.append(SuggestedTarget(
            id=obj.id, name=obj.name, ra_deg=obj.ra_deg, dec_deg=obj.dec_deg,
            type=obj.type, con=obj.con, blurb=obj.blurb,
            max_altitude_deg=o.max_altitude_deg,
            transit_utc=o.transit_utc.isoformat() if o.transit_utc else None,
            minutes_above_min_alt=o.minutes_above_min_alt,
            moon_separation_deg=o.moon_separation_deg,
            moon_up_fraction=o.moon_up_fraction,
            usable_start_utc=o.usable_start_utc.isoformat() if o.usable_start_utc else None,
            usable_end_utc=o.usable_end_utc.isoformat() if o.usable_end_utc else None,
            score=o.score,
            size_arcmin=obj.size_arcmin,
            framing=framing_hint(obj.size_arcmin),
            mosaic=mosaic_plan(obj.size_arcmin, obj.size_minor_arcmin),
            difficulty=target_difficulty(obj.id, obj.type),
        ))
    out.sort(key=lambda s: (-s.score, -s.max_altitude_deg))
    return out if limit is None else out[:max(0, limit)]


@dataclass(frozen=True)
class MonthObservability:
    """How well-placed a target is on a representative night of one month.

    One row of :func:`best_months` — the building block of the "best time of year
    to shoot this" seasonal strip. ``max_transit_alt_deg`` is the target's peak
    altitude *during that night's dark window* (not its physical transit, which
    may fall in daylight — a target that only culminates while the Sun is up reads
    as a poor month here, which is exactly right for "when can I actually get
    it?"). ``usable_dark_minutes`` is the darkness it spends above the altitude
    floor; ``dark_minutes`` is the length of the dark window itself (0 in polar
    day, when there is no darkness to shoot in).
    """

    month: int  # 1..12
    max_transit_alt_deg: float
    usable_dark_minutes: float
    dark_minutes: float


def best_months(
    observer: Observer,
    ra_deg: float,
    dec_deg: float,
    *,
    year: int,
    min_altitude_deg: float = 30.0,
    horizon: HorizonProfile | None = None,
) -> list[MonthObservability]:
    """Which months of ``year`` this target is well-placed from ``observer``.

    Answers the most common *plan-ahead* question a beginner asks about a named
    object — "when *this year* can I actually get it?" — that the short-horizon
    :func:`plan_tonight` / :func:`next_observing_windows` don't: they only look a
    night (or ~two weeks) out. Scans the year at monthly cadence: for a
    representative night near the middle of each month it finds that night's
    astronomical-dark window (:func:`_find_dark_window`) and how observable the
    single target is over it (:func:`_observability_batch`), so a winter target
    lights up Nov–Feb and a summer one Jun–Aug.

    Deterministic and offline like the rest of the planner (the Moon is *not*
    folded in — its phase on one representative night is seasonal noise, so this
    is a pure Sun/geometry answer). Always returns 12 rows, ``month`` 1→12; a row
    with ``dark_minutes == 0`` is a polar-day month (no darkness), and one with
    ``usable_dark_minutes == 0`` means the target never clears the floor during
    that month's darkness (too far south from this site, or only up in daylight).
    """
    _configure_iers_offline()
    rows: list[MonthObservability] = []
    for month in range(1, 13):
        # Anchor at local solar noon on the 15th, so ``_find_dark_window`` (which
        # takes the darkness *following* its reference) lands on that month's
        # night regardless of longitude — the same anchoring the forward planner
        # uses. The 15th is a stable mid-month representative for the season.
        anchor = datetime(year, month, 15, 12, 0, 0, tzinfo=timezone.utc) - timedelta(
            hours=observer.lon_deg / 15.0)
        window = _find_dark_window(observer, anchor)
        if window is None:
            # Sun never sets that night (high-latitude summer) — no darkness.
            rows.append(MonthObservability(month, 0.0, 0.0, 0.0))
            continue
        illum = moon_illumination(window.start + (window.end - window.start) / 2)
        o = _observability_batch([ra_deg], [dec_deg], observer, window,
                                 min_altitude_deg, illum, horizon=horizon)[0]
        rows.append(MonthObservability(
            month=month,
            max_transit_alt_deg=o.max_altitude_deg,
            usable_dark_minutes=o.minutes_above_min_alt,
            dark_minutes=round(window.duration_minutes, 1),
        ))
    return rows


def _angular_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle angular separation (deg) between two RA/Dec points."""
    r1, d1, r2, d2 = map(np.radians, (ra1, dec1, ra2, dec2))
    cos_sep = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    return float(np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0))))


# ---- "What's worth pointing at right now?" ----------------------------------
#
# ``plan_tonight`` answers "what's up *tonight*" across the whole catalog. This
# answers the narrower question a beginner actually asks on a suddenly-clear
# evening: *of the targets I already have, which one is up right now and would
# most benefit from another hour?* It only ever ranks the user's own library —
# it's about deepening what you've started, not discovering something new.

# The extra session the recommendation is phrased around. One hour is the unit a
# beginner can actually decide to spend tonight.
_EXTRA_HOURS = 1.0
# A ≥15% noise cut from that extra hour reads as "clearly worth more time"; past
# that the recommendation is already as strong as it gets, so the depth term
# saturates instead of endlessly favouring the emptiest target.
_WORTHWHILE_NOISE_GAIN = 0.15
# Usable dark minutes left that count as a full session's worth of sky. Two hours
# is a good Seestar night; beyond it the window term stops adding.
_FULL_SESSION_MINUTES = 120.0
# Don't suggest starting something with less sky left than this — by the time the
# scope is out and settled the window has closed.
_MIN_USEFUL_MINUTES = 20.0


def noise_gain_from_more_time(total_exposure_s: float,
                              extra_hours: float = _EXTRA_HOURS) -> float:
    """Fractional noise reduction from adding ``extra_hours`` to what's captured.

    Stacked noise falls as ``1/√t``, so going from ``t`` to ``t + h`` multiplies
    the remaining noise by ``√(t / (t + h))`` — a fractional cut of
    ``1 − √(t / (t + h))``. That is the same honest √N language the app already
    uses for "stacking cut your noise ~N×", and it is exactly what makes "would
    more subs help?" answerable in plain words: an hour on a 45-minute target cuts
    its noise by about a third, an hour on a 20-hour target by about 2%.

    Returns 1.0 for a target with nothing usable captured yet (the first hour is
    an unbounded improvement) and clamps into ``[0, 1]``. Pure — no ephemeris, no
    astropy — so the "how much would this help?" half is testable on its own.
    """
    t_h = max(0.0, float(total_exposure_s or 0.0)) / 3600.0
    h = max(0.0, float(extra_hours))
    if h <= 0.0:
        return 0.0
    if t_h <= 0.0:
        return 1.0
    return float(np.clip(1.0 - math.sqrt(t_h / (t_h + h)), 0.0, 1.0))


def _depth_component(total_exposure_s: float) -> float:
    """0..1 "would more subs clearly help?" term (see ``noise_gain_from_more_time``)."""
    gain = noise_gain_from_more_time(total_exposure_s)
    return float(np.clip(gain / _WORTHWHILE_NOISE_GAIN, 0.0, 1.0))


def _sky_component(altitude_now_deg: float | None, minutes_left: float,
                   min_altitude_deg: float) -> float:
    """0..1 "is it worth pointing at *now*?" term.

    Half altitude (how high it is at this moment, ramped from the usable floor to
    the 70° above which a small scope gains nothing more) and half remaining
    window (how much of tonight's darkness it still clears the floor for, capped
    at a full session). Zero when it is below the floor now, or when there isn't
    enough sky left to be worth starting.
    """
    if minutes_left < _MIN_USEFUL_MINUTES:
        return 0.0
    if altitude_now_deg is None or altitude_now_deg < min_altitude_deg:
        return 0.0
    alt_cap = 70.0
    if min_altitude_deg >= alt_cap:
        alt_component = 1.0
    else:
        alt_component = float(np.clip(
            (altitude_now_deg - min_altitude_deg) / (alt_cap - min_altitude_deg),
            0.0, 1.0))
    window_component = float(np.clip(minutes_left / _FULL_SESSION_MINUTES, 0.0, 1.0))
    return 0.5 * alt_component + 0.5 * window_component


def _hours_phrase(hours: float) -> str:
    """"45 min" / "1 h 20 m" / "6 h" — a duration a beginner reads at a glance."""
    total_min = int(round(max(0.0, hours) * 60.0))
    if total_min < 60:
        return f"{total_min} min"
    h, m = divmod(total_min, 60)
    return f"{h} h" if m == 0 else f"{h} h {m} m"


@dataclass
class TonightPick:
    """One of the user's own targets, judged as "worth pointing at right now"."""

    safe: str
    name: str
    ra_deg: float
    dec_deg: float
    # Altitude at the moment the ranking was made. None when no location is known
    # (the depth-only fallback) — never a fabricated number.
    altitude_now_deg: float | None
    # Usable dark minutes left tonight during which it clears the altitude floor.
    minutes_usable_left: float
    hours_captured: float
    frames_accepted: int
    # Fractional noise cut one more hour would buy (see ``noise_gain_from_more_time``).
    noise_gain: float
    score: float
    # One plain-language sentence the UI can show verbatim.
    reason: str


@dataclass
class TonightNow:
    """The "best use of your scope right now" answer for one observer."""

    generated_utc: str
    # None when no observer location could be resolved — the picks are then ranked
    # on depth alone and say so.
    observer: dict | None
    # Whether ``generated_utc`` falls inside tonight's astronomical darkness.
    dark_now: bool
    # Usable darkness left tonight in minutes (0 when unknown / none).
    dark_minutes_left: float
    min_altitude_deg: float
    picks: list[TonightPick] = field(default_factory=list)
    # Why the picks carry no placement, said **once** for the whole answer, or
    # None on the ordinary placed path. It used to be appended to every pick's
    # ``reason`` instead, so a three-pick card printed "Set your location in
    # Settings…" three times under a subtitle that had already said it. The
    # sentence is per-*answer*, not per-target, so it belongs here.
    note: str | None = None


def _altitudes_at(ras_deg, decs_deg, observer: Observer, when_utc: datetime):  # noqa: ANN001, ANN202
    """Altitude (deg) of each target at one instant — the "right now" read."""
    from astropy import units as u
    from astropy.coordinates import AltAz, SkyCoord
    from astropy.time import Time

    t = Time(when_utc.astimezone(timezone.utc).replace(tzinfo=None), scale="utc")
    frame = AltAz(obstime=t, location=observer.earth_location())
    coords = SkyCoord(ra=np.asarray(ras_deg) * u.deg,
                      dec=np.asarray(decs_deg) * u.deg, frame="icrs")
    return np.atleast_1d(np.asarray(coords.transform_to(frame).alt.deg, dtype=float))


def rank_targets_now(
    observer: Observer | None,
    when_utc: datetime,
    library_targets: list[LibraryTarget],
    *,
    min_altitude_deg: float = 30.0,
    horizon: HorizonProfile | None = None,
    limit: int = 3,
) -> TonightNow:
    """Rank the user's *own* targets by "worth pointing at right now".

    The score is ``sky × depth``: how well-placed the target is at this moment
    (:func:`_sky_component` — altitude now, and how much usable darkness it has
    left tonight) multiplied by how much another hour would actually buy
    (:func:`_depth_component`, from the √N noise maths). Both terms matter, and
    multiplying means a target that fails either one drops out rather than being
    averaged up by the other: an already-deep target that's beautifully placed
    isn't tonight's best use of the scope, and neither is a barely-started one
    that's below the trees.

    Degrades rather than erroring:

    * **No observer location** (a fresh install with nothing configured and no
      SITELAT in any header) → the sky term is unavailable, so the list is ranked
      on depth alone, ``altitude_now_deg`` stays ``None``, and each reason says the
      placement isn't known. That's still the useful half of the answer.
    * **No darkness tonight** (high-latitude summer) → the same depth-only
      ranking with ``dark_now`` false.
    * **Before tonight's darkness starts** → ranks against the *whole* coming
      window (there's no "now" altitude worth quoting yet, so the target's best
      altitude in that window is used).

    Read-only and additive: it never starts a capture, changes a setting, or
    writes anything. Returns at most ``limit`` picks, best first, and drops any
    target that scores 0 (below the floor, no usable sky left, or nothing to gain)
    so the caller can simply hide the surface when the list is empty.
    """
    _configure_iers_offline()
    now = when_utc.astimezone(timezone.utc)
    usable = [t for t in library_targets
              if t.ra_deg is not None and t.dec_deg is not None]

    plan = TonightNow(
        generated_utc=now.isoformat(),
        observer=asdict(observer) if observer is not None else None,
        dark_now=False,
        dark_minutes_left=0.0,
        min_altitude_deg=float(min_altitude_deg),
    )
    if not usable:
        return plan

    window = _find_dark_window(observer, now) if observer is not None else None
    if observer is None or window is None:
        # Two different "we can't place these" cases, and the copy must say which:
        # no site configured (fixable in Settings) vs no astronomical darkness at
        # all tonight (high-latitude summer — nothing the user can do about it).
        plan.note = ("Set your location in Settings and this can also tell you "
                     "whether it's up right now."
                     if observer is None else
                     "There's no astronomical darkness where you are tonight, so "
                     "this can't say what's well-placed.")
        plan.picks = _depth_only_picks(usable, limit)
        return plan

    # The part of tonight's darkness that is still ahead. Before dusk this is the
    # whole window ("here's what tonight is for"); mid-night it's what's left.
    rem_start = max(window.start, now)
    plan.dark_now = window.start <= now <= window.end
    plan.dark_minutes_left = round(
        max(0.0, (window.end - rem_start).total_seconds() / 60.0), 1)
    if plan.dark_minutes_left < _MIN_USEFUL_MINUTES:
        return plan  # Night's over (or all but) — nothing worth starting.

    remaining = DarkWindow(start=rem_start, end=window.end,
                           sun_alt_threshold_deg=window.sun_alt_threshold_deg)
    illum = moon_illumination(now)
    ras = [float(t.ra_deg) for t in usable]
    decs = [float(t.dec_deg) for t in usable]
    obs = _observability_batch(ras, decs, observer, remaining, min_altitude_deg,
                               illum, horizon=horizon)
    # "Right now" altitude only means something once it's actually dark; before
    # dusk quote the best altitude the target reaches in the coming window instead.
    alts = _altitudes_at(ras, decs, observer, now) if plan.dark_now else None

    picks: list[TonightPick] = []
    for i, (t, o) in enumerate(zip(usable, obs, strict=True)):
        alt_now = float(alts[i]) if alts is not None else o.max_altitude_deg
        # The same Moon penalty ``/tonight`` applies, so the two surfaces can't
        # disagree: recommending a faint target sitting beside a full Moon over
        # one in clean sky is exactly the advice that loses a beginner's trust.
        spoil = moon_penalty(o.moon_separation_deg, illum,
                             1.0 if o.moon_up_fraction is None else o.moon_up_fraction)
        sky = _sky_component(alt_now, o.minutes_above_min_alt,
                             min_altitude_deg) * (1.0 - spoil)
        depth = _depth_component(t.total_exposure_s)
        score = round(100.0 * sky * depth, 1)
        if score <= 0.0:
            continue
        hours = max(0.0, float(t.total_exposure_s or 0.0)) / 3600.0
        gain = noise_gain_from_more_time(t.total_exposure_s)
        picks.append(TonightPick(
            safe=t.safe, name=t.name, ra_deg=float(t.ra_deg), dec_deg=float(t.dec_deg),
            altitude_now_deg=round(alt_now, 1),
            minutes_usable_left=o.minutes_above_min_alt,
            hours_captured=round(hours, 2),
            frames_accepted=int(t.frames_accepted or 0),
            noise_gain=round(gain, 3),
            score=score,
            reason=_pick_reason(t.name, alt_now, o.minutes_above_min_alt, hours,
                                gain, placed_now=plan.dark_now, moon_spoil=spoil),
        ))
    picks.sort(key=lambda p: (-p.score, -(p.altitude_now_deg or 0.0)))
    plan.picks = picks[:max(0, int(limit))]
    return plan


def _depth_only_picks(targets: list[LibraryTarget], limit: int) -> list[TonightPick]:
    """Rank on "would more subs help?" alone — the no-location / no-darkness path.

    Honest about what it doesn't know: ``altitude_now_deg`` stays ``None`` rather
    than implying the target is up. *Why* it can't be placed is one sentence about
    the whole answer, so it lives on :attr:`TonightNow.note` and is said once —
    each pick's ``reason`` stays about that pick.
    """
    picks: list[TonightPick] = []
    for t in targets:
        depth = _depth_component(t.total_exposure_s)
        if depth <= 0.0:
            continue
        hours = max(0.0, float(t.total_exposure_s or 0.0)) / 3600.0
        gain = noise_gain_from_more_time(t.total_exposure_s)
        picks.append(TonightPick(
            safe=t.safe, name=t.name, ra_deg=float(t.ra_deg), dec_deg=float(t.dec_deg),
            altitude_now_deg=None,
            minutes_usable_left=0.0,
            hours_captured=round(hours, 2),
            frames_accepted=int(t.frames_accepted or 0),
            noise_gain=round(gain, 3),
            score=round(100.0 * depth, 1),
            reason=_depth_sentence(hours, t.name, gain),
        ))
    picks.sort(key=lambda p: (-p.score, -p.hours_captured))
    return picks[:max(0, int(limit))]


# Above this share of the score lost to the Moon, say so — below it the Moon is a
# detail the beginner doesn't need in a one-sentence recommendation.
_MOON_WORTH_MENTIONING = 0.12


def _pick_reason(name: str, altitude_deg: float, minutes_left: float,
                 hours_captured: float, gain: float, *, placed_now: bool,
                 moon_spoil: float = 0.0) -> str:
    """The one plain-language sentence the card shows — no jargon, no numbers the
    user can't act on."""
    where = (f"{name} is {round(altitude_deg)}° up right now" if placed_now
             else f"{name} climbs to {round(altitude_deg)}° tonight")
    window = _hours_phrase(minutes_left / 60.0)
    depth = _depth_sentence(hours_captured, "it", gain, capitalise=False)
    moon = (" The Moon is fairly close to it tonight, so expect a brighter sky."
            if moon_spoil >= _MOON_WORTH_MENTIONING else "")
    return (f"{where} and stays shootable for another {window}. "
            f"So far {depth}{moon}")


def _have_phrase(hours: float, subject: str, *, capitalise: bool = True) -> str:
    """"You've got 45 min on M 31" — or, under a minute, words instead of a "0 min"
    that reads as a bug rather than a fact."""
    if hours <= 0.0:
        text = f"you haven't captured any of {subject} yet"
    elif hours * 60.0 < 1.0:
        text = f"you've barely started on {subject}"
    else:
        text = f"you've got {_hours_phrase(hours)} on {subject}"
    return text[0].upper() + text[1:] if capitalise else text


def _depth_sentence(hours: float, subject: str, gain: float, *,
                    capitalise: bool = True) -> str:
    """"You've got 45 min on M 31 — another hour would cut its noise about 33%."

    One sentence, both halves: what the user has, and what one more hour buys.
    The percentage is only printed where it *means* something, because
    :func:`noise_gain_from_more_time` is a **ranking** score first and a figure
    second, and at both ends of the curve the figure it returns is not a sentence
    a beginner should be shown:

    * **Nothing captured yet** — the helper returns 1.0 ("the first hour is an
      unbounded improvement", which is the right thing to *sort* on), but printed
      it read *"another hour would cut its noise about 100%"*: an hour does not
      remove all the noise, and "another" is the wrong word for someone who has
      none. The frontend's ``readiness.noiseReductionHint`` already stays silent
      at zero integration; the planner claimed 100%.
    * **Very deeply integrated** — past roughly 200 h one more hour rounds to
      zero, so the same sentence claimed *"about 0%"*, which reads as a bug
      rather than the (true, useful) "you're done here".

    Both ends now say the honest thing in words instead of a number.
    """
    have = _have_phrase(hours, subject, capitalise=capitalise)
    if hours <= 0.0:
        return f"{have} — its first hour will do more for it than any hour after."
    pct = round(gain * 100)
    if pct <= 0:
        return f"{have} — it's as deep as another hour can meaningfully make it."
    return f"{have} — another hour would cut its noise about {pct}%."
