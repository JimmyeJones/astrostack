"""Normalize raw Seestar JSON-RPC replies into a flat telemetry dict.

Firmware revisions move and rename fields, so every lookup here tries a few
candidate paths and falls back to ``None`` rather than raising. The raw replies
are passed through under ``raw`` so nothing is lost if a field we don't yet
parse turns out to matter — minus anything private (:func:`scrub`).
"""

from __future__ import annotations

import re
from typing import Any

#: Sub-states and keys that must never reach the browser: on real firmware the
#: ``setting`` block carries the scope's hotspot password, ``station`` the home
#: Wi-Fi's name and address, ``location_lon_lat`` the owner's site. AstroStack
#: no longer asks for any of them; this is the belt to that braces, applied to
#: everything passed through under ``raw``.
_PRIVATE_KEYS = frozenset({"setting", "station", "location_lon_lat", "sn", "sn_str"})
_PRIVATE_PATTERN = re.compile(r"pass|pwd|ssid|secret|token", re.IGNORECASE)
#: ``YYYYMMDD-HHMMSS`` in an album file name — how Seestar Studio picks the
#: newest picture (verified on the owner's S30).
_TS_RE = re.compile(r"(\d{8})-(\d{6})")
#: A view in one of these states is not running (an idle scope answers
#: ``get_view_state`` with ``{}``; a stopped view lingers as ``cancel``).
_IDLE_STATES = ("cancel", "idle")


def _dig(obj: Any, *path: str) -> Any:
    """Walk nested dict keys, returning None if any hop is missing."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _first(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def scrub(obj: Any) -> Any:
    """A copy of ``obj`` without any key in :data:`_PRIVATE_KEYS` or matching
    :data:`_PRIVATE_PATTERN`, at any depth."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()
                if not (isinstance(k, str)
                        and (k in _PRIVATE_KEYS or _PRIVATE_PATTERN.search(k)))}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def latest_image(albums: dict) -> dict[str, Any] | None:
    """The newest picture in a ``get_albums`` reply, preferring a stacked one
    at the same timestamp — Seestar Studio's rule. ``thumb`` and ``full`` are
    paths on the scope's HTTP server; the full picture is the thumbnail's path
    without ``_thn``. None when the scope holds no picture."""
    if not isinstance(albums, dict):
        return None
    parent = albums.get("path") if isinstance(albums.get("path"), str) else "MyWorks"
    groups = albums.get("list")
    best: tuple[str, dict[str, Any]] | None = None
    for grp in groups if isinstance(groups, list) else []:
        files = grp.get("files") if isinstance(grp, dict) else None
        for f in files if isinstance(files, list) else []:
            thn = f.get("thn") if isinstance(f, dict) else None
            if not isinstance(thn, str) or not thn.endswith("_thn.jpg") or ".." in thn:
                continue
            m = _TS_RE.search(thn)
            score = ((m.group(1) + m.group(2)) if m else "0") + ("1" if "Stacked" in thn else "0")
            if best is None or score > best[0]:
                count = f.get("count")
                best = (score, {
                    "name": f.get("name") if isinstance(f.get("name"), str) else None,
                    "count": count if isinstance(count, int) else None,
                    "stacked": "Stacked" in thn,
                    "thumb": f"{parent}/{thn}",
                    "full": f"{parent}/{thn[: -len('_thn.jpg')]}.jpg",
                })
    return best[1] if best is not None else None


def normalize(device_state: dict, view_state: dict, equ: dict,
              disk: dict | None = None, albums: dict | None = None) -> dict[str, Any]:
    pi = _dig(device_state, "pi_status") or {}
    device = _dig(device_state, "device") or {}
    disk = disk if isinstance(disk, dict) else {}

    # Storage: the first volume entry, where present; else ``get_disk_volume``,
    # which is where the owner's S30 (firmware 9.75) reports it.
    volumes = _dig(device_state, "storage", "storage_volume")
    vol0 = volumes[0] if isinstance(volumes, list) and volumes else {}
    free_mb = _first(vol0.get("freeMB"), vol0.get("free_mb"), disk.get("freeMB"))
    total_mb = _first(vol0.get("totalMB"), vol0.get("total_mb"), disk.get("totalMB"))

    # View / stacking progress lives under "View" (capitalised on most firmware).
    view = _first(_dig(view_state, "View"), view_state) or {}
    stack = _first(_dig(view, "Stack"), {}) or {}
    stacked = _first(stack.get("stacked_frame"), stack.get("stacked_count"))
    dropped = _first(stack.get("dropped_frame"), stack.get("dropped_count"))
    exposure = stack.get("Exposure") if isinstance(stack.get("Exposure"), dict) else {}
    exp_ms = exposure.get("exp_ms")
    exp_ms = exp_ms if isinstance(exp_ms, (int, float)) and exp_ms > 0 else None
    integration_s = (int(stacked * exp_ms / 1000)
                     if exp_ms is not None and isinstance(stacked, int) else None)
    # Nothing running: ``{}`` after boot, or a stopped view lingering as
    # ``cancel`` with its old mode and stage. Say "idle" rather than "star".
    state = _first(view.get("state"), _dig(view_state, "state"))
    idle = not view or state in _IDLE_STATES

    charger = _first(pi.get("charger_status"), pi.get("charge_status"))
    charging = None
    if isinstance(charger, str):
        charging = charger.lower() in ("charging", "full")
    charging = _first(charging, pi.get("charge_online"))

    return {
        "device_name": _first(device.get("name"), device.get("device_name")),
        "model": _first(device.get("product_model"), device.get("name")),
        "firmware": _first(device.get("firmware_ver_string"), device.get("firmware_ver")),
        "temp_c": _first(pi.get("temp"), pi.get("temperature")),
        "battery_pct": _first(pi.get("battery_capacity"), pi.get("battery")),
        "charging": charging,
        "charger_status": charger if isinstance(charger, str) else None,
        "free_storage_mb": free_mb,
        "total_storage_mb": total_mb,
        "mode": None if idle else _first(view.get("mode"), _dig(view_state, "mode")),
        "state": "idle" if idle else state,
        "stage": None if idle else view.get("stage"),
        "target_name": _first(view.get("target_name"), _dig(view_state, "target_name")),
        "stacked_frames": stacked,
        "dropped_frames": dropped,
        "exposure_s": exp_ms / 1000 if exp_ms is not None else None,
        "integration_s": integration_s,
        "latest_image": latest_image(albums or {}),
        "ra_hours": _first(equ.get("ra"), _dig(equ, "ra")),
        "dec_deg": _first(equ.get("dec"), _dig(equ, "dec")),
        "raw": scrub({"device_state": device_state, "view_state": view_state, "equ": equ,
                      "disk": disk}),
    }
