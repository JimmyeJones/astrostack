"""Normalize raw Seestar JSON-RPC replies into a flat telemetry dict.

Firmware revisions move and rename fields, so every lookup here tries a few
candidate paths and falls back to ``None`` rather than raising. The raw replies
are always passed through under ``raw`` so nothing is lost if a field we don't
yet parse turns out to matter.
"""

from __future__ import annotations

from typing import Any


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


def normalize(device_state: dict, view_state: dict, equ: dict) -> dict[str, Any]:
    pi = _dig(device_state, "pi_status") or {}
    device = _dig(device_state, "device") or {}

    # Storage: the first volume entry, where present.
    volumes = _dig(device_state, "storage", "storage_volume")
    vol0 = volumes[0] if isinstance(volumes, list) and volumes else {}
    free_mb = _first(vol0.get("freeMB"), vol0.get("free_mb"))
    total_mb = _first(vol0.get("totalMB"), vol0.get("total_mb"))

    # View / stacking progress lives under "View" (capitalised on most firmware).
    view = _first(_dig(view_state, "View"), view_state) or {}
    stack = _first(_dig(view, "Stack"), {}) or {}
    stacked = _first(stack.get("stacked_frame"), stack.get("stacked_count"))
    dropped = _first(stack.get("dropped_frame"), stack.get("dropped_count"))

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
        "mode": _first(view.get("mode"), _dig(view_state, "mode")),
        "state": _first(view.get("state"), _dig(view_state, "state")),
        "stage": view.get("stage"),
        "target_name": _first(view.get("target_name"), _dig(view_state, "target_name")),
        "stacked_frames": stacked,
        "dropped_frames": dropped,
        "ra_hours": _first(equ.get("ra"), _dig(equ, "ra")),
        "dec_deg": _first(equ.get("dec"), _dig(equ, "dec")),
        "raw": {"device_state": device_state, "view_state": view_state, "equ": equ},
    }
