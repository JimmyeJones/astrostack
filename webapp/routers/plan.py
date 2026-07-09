"""'Tonight' night-planner endpoint.

``GET /api/plan/tonight`` returns an offline, ranked list of deep-sky targets
worth pointing the scope at tonight: the user's own library targets ("already
targeted", annotated with what they've captured) plus bundled catalogs — the
Messier objects and a curated set of popular non-Messier NGC/IC targets — ("not
yet targeted"), each scored by altitude, usable window and Moon proximity
(see :mod:`seestack.nightplan`).

The observer location comes from Settings when set, otherwise it's read
best-effort from a solved frame's FITS header (``SITELAT``/``SITELONG`` — the
Seestar writes these), so a Seestar owner usually needs to configure nothing.
Everything is read-only: this never touches stacks, frames or settings.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from seestack.nightplan import HorizonProfile, LibraryTarget, Observer, plan_tonight
from webapp import deps

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plan", tags=["plan"])

# Cap how many frames we probe for a site location so a big library with no
# SITELAT header anywhere can't turn one request into thousands of header reads.
_MAX_SITE_PROBE_FRAMES = 24


def _parse_angle(value: Any) -> float | None:
    """Parse a FITS angle that may be a float (deg) or a 'DD:MM:SS' string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    # Sexagesimal 'DD:MM:SS' / 'DD MM SS'.
    parts = s.replace(":", " ").split()
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if not nums:
        return None
    sign = -1.0 if nums[0] < 0 or s.lstrip().startswith("-") else 1.0
    deg = abs(nums[0])
    if len(nums) > 1:
        deg += nums[1] / 60.0
    if len(nums) > 2:
        deg += nums[2] / 3600.0
    return sign * deg


def _site_from_header(header: dict) -> tuple[float, float] | None:
    """(lat, lon) in degrees from a raw FITS header, or None if absent/bad."""
    lat = _parse_angle(header.get("SITELAT"))
    lon = _parse_angle(header.get("SITELONG") or header.get("SITELONG "))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _detect_site_from_fits(request: Request) -> tuple[float, float] | None:
    """Best-effort observer lat/lon from a recent frame's FITS header.

    Reads headers only (fast, no pixel data), tries the cached copy before the
    original NAS path, and bails after a bounded number of probes. Any read
    error is swallowed — a missing site just means the caller must configure one.
    """
    from seestack.io.fits_loader import load_header
    from seestack.io.project import Project

    lib = deps.open_library(request)
    probed = 0
    try:
        for entry in lib.list_targets():
            proj = None
            try:
                proj = Project.open(lib.target_dir(entry))
                for frame in proj.iter_frames(accepted_only=True):
                    if probed >= _MAX_SITE_PROBE_FRAMES:
                        return None
                    for path in (frame.cached_path, frame.source_path):
                        if not path:
                            continue
                        probed += 1
                        try:
                            info = load_header(path)
                        except Exception:  # noqa: BLE001 — unreadable frame, move on
                            continue
                        site = _site_from_header(info.raw_header)
                        if site is not None:
                            return site
                        break  # one readable path per frame is enough
            except Exception:  # noqa: BLE001 — a broken project must not 500 the plan
                continue
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()
    return None


def _library_targets(request: Request) -> list[LibraryTarget]:
    """Library targets that have a position, for the 'already targeted' set."""
    lib = deps.open_library(request)
    try:
        out: list[LibraryTarget] = []
        for t in lib.list_targets():
            if t.ra_deg is None or t.dec_deg is None:
                continue
            out.append(LibraryTarget(
                safe=t.safe_name, name=t.name,
                ra_deg=float(t.ra_deg), dec_deg=float(t.dec_deg),
                frames_accepted=int(t.n_frames_accepted or 0),
                total_exposure_s=float(t.total_exposure_s or 0.0),
            ))
        return out
    finally:
        lib.close()


@router.get("/tonight")
def get_tonight(
    request: Request,
    when: str | None = Query(default=None, description="ISO-8601 UTC time; defaults to now"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
) -> dict[str, Any]:
    """Ranked observability plan for tonight (see module docstring)."""
    settings = deps.get_settings(request)

    if when:
        try:
            ref = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = datetime.now(timezone.utc)

    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)

    # Resolve the observer: explicit Settings location wins; otherwise sniff a
    # frame header (the common Seestar case). None → the UI prompts for a site.
    location_source = "none"
    observer: Observer | None = None
    if settings.site_lat is not None and settings.site_lon is not None:
        observer = Observer(lat_deg=float(settings.site_lat),
                            lon_deg=float(settings.site_lon),
                            elevation_m=float(settings.site_elevation_m or 0.0))
        location_source = "settings"
    else:
        site = _detect_site_from_fits(request)
        if site is not None:
            observer = Observer(lat_deg=site[0], lon_deg=site[1],
                                elevation_m=float(settings.site_elevation_m or 0.0))
            location_source = "fits"

    if observer is None:
        return {
            "location_source": "none",
            "observer": None,
            "generated_utc": ref.astimezone(timezone.utc).isoformat(),
            "dark_window": None,
            "moon_illumination": None,
            "min_altitude_deg": min_altitude,
            "targets": [],
        }

    plan = plan_tonight(
        observer, ref, min_altitude_deg=float(min_altitude),
        library_targets=_library_targets(request),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
    )
    payload = asdict(plan)
    payload["location_source"] = location_source
    return payload
