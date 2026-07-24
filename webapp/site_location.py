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

from typing import Any

# Cap how many frames we probe for a site location so a big library with no
# SITELAT header anywhere can't turn one request into thousands of header reads.
MAX_SITE_PROBE_FRAMES = 24


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


def detect_site_from_library(lib, *, max_probes: int = MAX_SITE_PROBE_FRAMES  # noqa: ANN001
                             ) -> tuple[float, float] | None:
    """Best-effort observer ``(lat, lon)`` from a recent frame's FITS header.

    Reads headers only (fast, no pixel data), tries the cached copy before the
    original NAS path, and bails after ``max_probes`` reads. Any read error is
    swallowed — a missing site just means the caller must configure one. Takes an
    already-open ``Library`` so a caller that already holds one doesn't reopen it.
    """
    from seestack.io.fits_loader import load_header
    from seestack.io.project import Project

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
                    try:
                        info = load_header(path)
                    except Exception:  # noqa: BLE001 — unreadable frame, move on
                        continue
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
