"""Tonight — an offline deep-sky observability planner.

Given an observer location and a moment in time, rank deep-sky targets by how
*observable* they are during tonight's dark window: how high they climb, how
long they spend above a usable altitude, and how much a bright, nearby Moon will
wash them out. It answers the pre-capture question "what's worth pointing the
Seestar at tonight?" — the complement to the post-capture stack/edit pipeline.

Everything here is **offline and deterministic**: pure ``astropy`` (already a
dependency) over a bundled Messier catalog (``data/messier.json``). No network,
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

log = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).parent / "data" / "messier.json"

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
class CatalogObject:
    """One bundled deep-sky target."""

    id: str
    name: str
    ra_deg: float
    dec_deg: float
    type: str
    con: str


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
class Observability:
    """How observable one target is over a given dark window."""

    max_altitude_deg: float
    transit_utc: datetime | None
    minutes_above_min_alt: float
    moon_separation_deg: float
    score: float  # 0..100, higher = better tonight


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
    # Present only for library targets the user has already shot.
    target_safe: str | None = None
    frames_accepted: int | None = None
    total_exposure_s: float | None = None


@dataclass
class NightPlan:
    """The full ranked plan the API returns."""

    generated_utc: str
    observer: dict
    dark_window: dict | None
    moon_illumination: float
    min_altitude_deg: float
    targets: list[PlannedTarget] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_catalog() -> tuple[CatalogObject, ...]:
    """Load the bundled Messier catalog (cached; static file)."""
    with _CATALOG_PATH.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return tuple(
        CatalogObject(
            id=o["id"], name=o.get("name", ""), ra_deg=float(o["ra_deg"]),
            dec_deg=float(o["dec_deg"]), type=o.get("type", ""), con=o.get("con", ""),
        )
        for o in raw["objects"]
    )


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


def _find_dark_window(observer: Observer, when_utc: datetime) -> DarkWindow | None:
    """Astronomical dark window around the solar midnight following ``when_utc``.

    Scans local-noon → next local-noon so the night sits contiguously in the
    middle (never split across the array ends), then takes the widest contiguous
    span below the deepest reachable Sun-altitude threshold.
    """
    _configure_iers_offline()
    location = observer.earth_location()

    ref = when_utc.astimezone(timezone.utc)
    # Local solar noon nearest the reference: highest Sun altitude in ±12 h.
    noon_stamps, noon_times = _times_grid(ref - timedelta(hours=12),
                                          ref + timedelta(hours=12), 15.0)
    noon_alt = _sun_altitudes(noon_times, location)
    t_noon = noon_stamps[int(np.argmax(noon_alt))]

    # Fine scan across the following 24 h (noon → next noon).
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


def _score(max_alt: float, minutes_above: float, dark_minutes: float,
           moon_sep: float, moon_illum: float, min_alt: float) -> float:
    """Blend altitude, usable-window fraction and a Moon penalty into 0..100.

    * Altitude: rewards a high transit (capped at 70° — above that adds nothing
      meaningful for a small scope).
    * Window: fraction of tonight's darkness the target clears ``min_alt``.
    * Moon: a bright Moon close to the target subtracts up to 40%; a faint or
      far Moon barely matters.
    """
    if minutes_above <= 0 or dark_minutes <= 0:
        return 0.0
    alt_component = float(np.clip((max_alt - min_alt) / (70.0 - min_alt), 0.0, 1.0)) \
        if max_alt > min_alt else 0.0
    window_component = float(np.clip(minutes_above / dark_minutes, 0.0, 1.0))
    base = 0.5 * alt_component + 0.5 * window_component
    proximity = float(np.clip((60.0 - moon_sep) / 60.0, 0.0, 1.0))
    moon_penalty = 0.4 * float(np.clip(moon_illum, 0.0, 1.0)) * proximity
    return round(100.0 * base * (1.0 - moon_penalty), 1)


def _observability_batch(ras_deg, decs_deg, observer: Observer, window: DarkWindow,
                         min_alt_deg: float, moon_illum: float):  # noqa: ANN001, ANN202
    """Vectorised observability for many targets over one dark window.

    Returns a list of :class:`Observability`, one per input coordinate.
    """
    from astropy import units as u
    from astropy.coordinates import AltAz, SkyCoord, get_body

    location = observer.earth_location()
    stamps, times = _times_grid(window.start, window.end, 5.0)
    step_min = 5.0
    altaz_frame = AltAz(obstime=times, location=location)

    coords = SkyCoord(ra=np.asarray(ras_deg) * u.deg,
                      dec=np.asarray(decs_deg) * u.deg, frame="icrs")
    # (n_targets, n_times) altitude grid.
    alt = coords[:, None].transform_to(altaz_frame[None, :]).alt.deg
    alt = np.atleast_2d(np.asarray(alt, dtype=float))

    # Moon separation at the darkest moment (mid-window) — one representative sep.
    mid = stamps[len(stamps) // 2]
    from astropy.time import Time
    # Transform the Moon (GCRS) into the targets' ICRS frame before measuring
    # separation, so astropy doesn't warn about a direction-dependent transform.
    moon = get_body("moon", Time(mid.replace(tzinfo=None), scale="utc"), location).icrs
    moon_sep = coords.separation(moon).deg
    moon_sep = np.atleast_1d(np.asarray(moon_sep, dtype=float))

    out: list[Observability] = []
    dark_minutes = window.duration_minutes
    for i in range(alt.shape[0]):
        row = alt[i]
        imax = int(np.argmax(row))
        max_alt = float(row[imax])
        transit = stamps[imax].astimezone(timezone.utc) if max_alt >= min_alt_deg else None
        minutes_above = float(np.count_nonzero(row >= min_alt_deg) * step_min)
        sep = float(moon_sep[i])
        score = _score(max_alt, minutes_above, dark_minutes, sep, moon_illum, min_alt_deg)
        out.append(Observability(
            max_altitude_deg=round(max_alt, 1),
            transit_utc=transit,
            minutes_above_min_alt=round(minutes_above, 1),
            moon_separation_deg=round(sep, 1),
            score=score,
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
                 include_catalog: bool = True) -> NightPlan:
    """Rank tonight's targets for ``observer`` at ``when_utc``.

    Combines the bundled catalog ("not yet targeted") with the user's library
    targets ("already targeted", annotated with what they've captured). A library
    target that matches a catalog object by position is shown once, as the
    already-targeted entry. Returns targets sorted best-first (score desc), then
    highest transit; targets that never clear ``min_altitude_deg`` tonight sort
    to the bottom with score 0.
    """
    _configure_iers_offline()
    library_targets = library_targets or []
    window = _find_dark_window(observer, when_utc)
    illum = moon_illumination(when_utc)

    plan = NightPlan(
        generated_utc=when_utc.astimezone(timezone.utc).isoformat(),
        observer=asdict(observer),
        dark_window=None,
        moon_illumination=round(illum, 3),
        min_altitude_deg=min_altitude_deg,
    )
    if window is None:
        return plan  # Sun never sets — nothing to plan.
    plan.dark_window = {
        "start_utc": window.start.isoformat(),
        "end_utc": window.end.isoformat(),
        "duration_minutes": round(window.duration_minutes, 1),
        "sun_alt_threshold_deg": window.sun_alt_threshold_deg,
    }

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

    obs = _observability_batch(ras, decs, observer, window, min_altitude_deg, illum)
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
            ))

    plan.targets.sort(key=lambda p: (-p.score, -p.max_altitude_deg))
    return plan


def _angular_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle angular separation (deg) between two RA/Dec points."""
    r1, d1, r2, d2 = map(np.radians, (ra1, dec1, ra2, dec2))
    cos_sep = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    return float(np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0))))
