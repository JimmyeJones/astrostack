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
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from seestack.framing import FramingHint, framing_hint

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
    # A plain-language, beginner-friendly one-liner about the object ("what am I
    # looking at?"), curated for the popular targets; ``""`` when the catalog has
    # none (the object-info card then reads fine from type + constellation alone).
    blurb: str = ""


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
    # "Will it fit in one Seestar frame?" — major-axis size (arcmin) and the
    # verdict derived from it, for catalog candidates the bundled catalog has a
    # size for; ``None`` otherwise (library rows carry none — the Target page
    # already shows their framing, and a mosaic result would confuse the
    # single-frame catalog verdict). See :mod:`seestack.framing`.
    size_arcmin: float | None = None
    framing: FramingHint | None = None


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
            blurb=o.get("blurb", ""),
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
    """A UTC ``Time`` array from ``start`` to ``end`` inclusive at a fixed step."""
    from astropy.time import Time

    total_min = max((end - start).total_seconds() / 60.0, step_minutes)
    n = int(round(total_min / step_minutes)) + 1
    stamps = [start + timedelta(minutes=step_minutes * i) for i in range(n)]
    return stamps, Time([s.astimezone(timezone.utc).replace(tzinfo=None) for s in stamps],
                        scale="utc")


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
    proximity = float(np.clip((60.0 - moon_sep) / 60.0, 0.0, 1.0))
    moon_penalty = (0.4 * float(np.clip(moon_illum, 0.0, 1.0)) * proximity
                    * float(np.clip(moon_up_fraction, 0.0, 1.0)))
    return round(100.0 * base * (1.0 - moon_penalty), 1)


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
    step_min = 5.0
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
        minutes_above = float(n_usable * step_min)
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
                type="", con="", already_targeted=True,
                max_altitude_deg=o.max_altitude_deg,
                transit_utc=o.transit_utc.isoformat() if o.transit_utc else None,
                minutes_above_min_alt=o.minutes_above_min_alt,
                moon_separation_deg=o.moon_separation_deg, score=o.score,
                moon_up_fraction=o.moon_up_fraction,
                usable_start_utc=o.usable_start_utc.isoformat() if o.usable_start_utc else None,
                usable_end_utc=o.usable_end_utc.isoformat() if o.usable_end_utc else None,
                target_safe=t.safe, frames_accepted=t.frames_accepted,
                total_exposure_s=round(t.total_exposure_s, 1),
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
    _configure_iers_offline()
    start_utc = start_utc.astimezone(timezone.utc)
    # Anchor the per-night scan at local solar noon on the start date, so
    # ``_find_dark_window`` (which takes the darkness *following* its reference)
    # lands on that calendar night regardless of the observer's longitude. Local
    # noon in UTC is 12:00 − lon/15 h (east of Greenwich is earlier in UTC).
    d = start_utc.date()
    anchor = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc) - timedelta(
        hours=observer.lon_deg / 15.0)
    # If the caller is before that date's local noon (small hours / pre-dawn), the
    # night they're currently inside began the *previous* evening — anchor one day
    # earlier so offset 0 lands on that ongoing window, and scan one extra night to
    # keep the same forward horizon. The past-window/clip guards below drop or trim
    # it as needed, so a pre-dawn user still sees the darkness they can use tonight.
    shift = 1 if start_utc < anchor else 0
    anchor -= timedelta(days=shift)

    out: list[NextObservingWindow] = []
    for offset in range(max(0, nights) + shift):
        window = _find_dark_window(observer, anchor + timedelta(days=offset))
        if window is None:
            continue  # Sun never sets that night (high summer) — nothing to plan.
        # Skip a window whose darkness is entirely behind us; clip the first
        # partially-past window so "tonight" reflects only the time still to come.
        if window.end <= start_utc:
            continue
        if window.start < start_utc:
            window = DarkWindow(start=start_utc, end=window.end,
                                sun_alt_threshold_deg=window.sun_alt_threshold_deg)
            if window.duration_minutes <= 0:
                continue
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


def _angular_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle angular separation (deg) between two RA/Dec points."""
    r1, d1, r2, d2 = map(np.radians, (ra1, dec1, ra2, dec2))
    cos_sep = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    return float(np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0))))
