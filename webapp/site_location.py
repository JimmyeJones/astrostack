"""Best-effort observer site location shared across webapp surfaces.

The observer's latitude/longitude drive the night planner (``/api/plan``) and the
noon-to-noon bucketing of the imaging calendar (``/api/activity-calendar``). A
Seestar owner rarely fills in a location in Settings, but the Seestar writes
``SITELAT``/``SITELONG`` into every sub's FITS header — so when Settings has no
location we sniff it from a recent frame's header instead. Kept in one module so
every surface resolves the site the same way (and parses the same header quirks).

Everything here is read-only (headers only, never pixel data) and bounded, so a big
library with no site header can't turn one request into thousands of reads.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, NamedTuple

# Cap how many frames we probe for a site location so a big library with no
# SITELAT header anywhere can't turn one request into thousands of header reads.
MAX_SITE_PROBE_FRAMES = 24

# The detected longitude only changes when the library does, so a short app-level
# cache keeps a locationless library from being re-probed on every page load.
SITE_LON_CACHE_TTL_S = 120.0


class SiteProbe(NamedTuple):
    """What the header probe found, and — when it found nothing — *why*.

    "No site" has three genuinely different causes and they want three different
    sentences. The planner used to collapse all of them into ``None`` and every
    surface then said the same thing: *"it reads your location automatically from
    a plate-solved Seestar frame — so once you've solved some subs it'll just
    work."* That is right for an empty library and **false** for a library whose
    subs simply don't carry ``SITELAT`` — solving more of them will never help,
    and a beginner staring at a Library full of "Solved" badges reads the app as
    broken. (Reproduced 2026-09-12 by dogfooding the bundled sample, which is
    plate-solved and carries no site header, so the app said exactly that with 27
    solved subs on screen.)

    ``reason`` is one of:

    ``"found"``
        A frame carried a usable site; ``site`` is it.
    ``"no-frames"``
        Nothing was probed — no targets, or no accepted frame with a path. More
        subs really would fix it.
    ``"no-site-header"``
        Headers were read and none carried a usable ``SITELAT``/``SITELONG``.
        More subs from the same source will not fix it; only Settings will.
    ``"unreadable"``
        Frames exist but not one header could be read (storage offline, files
        moved). Neither more subs nor Settings is the right advice.
    """

    site: tuple[float, float] | None
    reason: str


def parse_angle(value: Any) -> float | None:
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


def site_from_header(header: dict) -> tuple[float, float] | None:
    """(lat, lon) in degrees from a raw FITS header, or None if absent/bad."""
    lat = parse_angle(header.get("SITELAT"))
    lon = parse_angle(header.get("SITELONG") or header.get("SITELONG "))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def detect_site_from_library(lib, *, max_probes: int = MAX_SITE_PROBE_FRAMES,  # noqa: ANN001
                             _stats: dict[str, int] | None = None,
                             ) -> tuple[float, float] | None:
    """Best-effort observer ``(lat, lon)`` from a recent frame's FITS header.

    Reads headers only (fast, no pixel data), tries the cached copy before the
    original NAS path, and bails after ``max_probes`` reads. Any read error is
    swallowed — a missing site just means the caller must configure one. Takes an
    already-open ``Library`` so a caller that already holds one doesn't reopen it.

    This is **the** walk: :func:`probe_site_from_library` calls it rather than
    repeating it, so there is one place that decides where the telescope is and
    one seam for a caller (or a test) to stand in front of.

    ``_stats``, when given, is filled in with how much the walk touched
    (``probed`` paths, ``read_ok`` headers actually loaded) — the only thing
    :func:`_no_site_reason` needs to tell "you have no frames" from "your frames
    carry no site", without a second pass over the library.
    """
    from seestack.io.fits_loader import load_header
    from seestack.io.project import Project

    def _tick(key: str) -> None:
        if _stats is not None:
            _stats[key] = _stats.get(key, 0) + 1

    probed = 0
    for entry in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(entry))
            for frame in proj.iter_frames(accepted_only=True):
                if probed >= max_probes:
                    return None
                for path in (frame.cached_path, frame.source_path):
                    if not path:
                        continue
                    probed += 1
                    _tick("probed")
                    try:
                        info = load_header(path)
                    except Exception:  # noqa: BLE001 — unreadable frame, move on
                        continue
                    _tick("read_ok")
                    site = site_from_header(info.raw_header)
                    if site is not None:
                        return site
                    break  # one readable path per frame is enough
        except Exception:  # noqa: BLE001 — a broken project must not 500 the caller
            continue
        finally:
            if proj is not None:
                proj.close()
    return None


def probe_site_from_library(lib, *, max_probes: int = MAX_SITE_PROBE_FRAMES  # noqa: ANN001
                            ) -> SiteProbe:
    """:func:`detect_site_from_library` with the reason attached — one walk, not two.

    A caller that stands in for ``detect_site_from_library`` (a test, say) leaves
    ``_stats`` empty, and an empty walk reads as ``"no-frames"``: the reason then
    describes the stand-in rather than a library, which is the honest answer when
    nothing walked one.
    """
    stats: dict[str, int] = {}
    site = detect_site_from_library(lib, max_probes=max_probes, _stats=stats)
    if site is not None:
        return SiteProbe(site, "found")
    return SiteProbe(None, _no_site_reason(stats.get("probed", 0),
                                           stats.get("read_ok", 0)))


def _no_site_reason(probed: int, read_ok: int) -> str:
    """Classify an unsuccessful probe from what it managed to touch.

    Deliberately conservative about ``"unreadable"``: it is claimed only when
    *every* probed path failed to load, because a library where one frame is
    missing and the rest simply lack the header is a header problem, not a
    storage one.
    """
    if probed == 0:
        return "no-frames"
    if read_ok == 0:
        return "unreadable"
    return "no-site-header"


def resolve_site_lon(request: Any, lib: Any, configured_lon: float | None) -> float | None:
    """The observer's longitude (+E deg) to bucket **observing nights** with.

    An explicit Settings location wins; otherwise the longitude is sniffed from a
    frame's ``SITELONG`` header (the common Seestar case — a beginner rarely
    configures one) and cached on the app for
    :data:`SITE_LON_CACHE_TTL_S`, keyed on the target set so a scan invalidates
    it. ``None`` means "unknown", and callers then fall back to UTC noon-to-noon.

    Shared by **every surface that names a night** — the Dashboard's imaging
    calendar and the Target page's Nights card — so the two can never disagree
    about which night a given session belongs to. A broken library degrades to
    ``None`` (UTC) rather than failing the request.
    """
    if configured_lon is not None:
        return configured_lon
    site = detect_site_cached(request, lib)
    return site[1] if site is not None else None


def resolve_night_key(
    request: Any, lib: Any, configured_lon: float | None
) -> Callable[[str | None], str | None]:
    """The observing-night key every "which night was this?" surface buckets by:
    a capture stamp in, an ISO ``YYYY-MM-DD`` noon-to-noon local night out
    (``None`` when the stamp is missing or unparseable).

    Wraps :func:`resolve_site_lon` + ``night_date_of`` so the three surfaces that
    need it — the Target page's Nights card, the Dashboard's target-progress
    roll-up and the planner's already-targeted rows — cannot hand-mirror slightly
    different bucketing and quote different nights (or different "N more clear
    nights" ETAs) for the same target. The longitude is resolved once per call,
    off the same short app-level cache, so building the key is cheap enough to do
    per request.
    """
    from seestack.activity_calendar import night_date_of

    lon = resolve_site_lon(request, lib, configured_lon)

    def night_key(ts: str | None) -> str | None:
        if not ts:
            return None
        d = night_date_of(ts, lon)
        return d.isoformat() if d is not None else None

    return night_key


def probe_site_cached(request: Any, lib: Any) -> SiteProbe:
    """:func:`probe_site_from_library`, memoised on the app.

    The header probe walks real files, so it is far too expensive to redo on every
    request that wants to know where the telescope is. Cached for
    :data:`SITE_LON_CACHE_TTL_S`, keyed on the target set so a scan invalidates it.
    A ``None`` site means "no frame carries a site" — every caller must have a
    site-unknown behaviour, never a failure.

    A library that can't even be listed is reported as ``"unreadable"``: that is
    the one shape where neither "shoot more subs" nor "fill in Settings" is the
    honest next step.
    """
    try:
        targets = lib.list_targets()
    except Exception:  # noqa: BLE001 — a broken library just means "unknown site"
        return SiteProbe(None, "unreadable")
    tsig = tuple(sorted((t.safe_name, t.last_activity_utc or "") for t in targets))
    cache = getattr(request.app.state, "activity_lon_cache", None)
    now = time.monotonic()
    if (cache and cache["sig"] == tsig and (now - cache["at"]) < SITE_LON_CACHE_TTL_S
            and cache.get("reason")):
        return SiteProbe(cache.get("site"), cache["reason"])
    probe = probe_site_from_library(lib)
    # ``lon`` is kept beside ``site`` because it is what the night-bucketing
    # callers read; all three are written together so they cannot diverge.
    request.app.state.activity_lon_cache = {
        "sig": tsig, "at": now,
        "lon": probe.site[1] if probe.site is not None else None,
        "site": probe.site, "reason": probe.reason,
    }
    return probe


def detect_site_cached(request: Any, lib: Any) -> tuple[float, float] | None:
    """``(lat, lon)`` sniffed from the library's FITS headers, memoised on the app.

    The site alone — :func:`probe_site_cached` is the same answer with the reason
    attached, off the same cache entry.
    """
    return probe_site_cached(request, lib).site
