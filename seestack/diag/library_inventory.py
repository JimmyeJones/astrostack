"""What is in the owner's library — the shape every 1.0 decision is sized against.

Roadmap 1.0, test R1. Reads the library record only; no FITS file is opened.
Per target: catalogue name, whether it is a mosaic, sub counts, integration,
nights, mosaic panels, the share of subs that plate-solved, median star size
and sky level, why subs were set aside (reason category only), and the newest
stack's canvas and options. Library-wide: totals, and the spread of exposure,
gain, sensor temperature and frame size.

**Privacy.** Catalogue target names and numbers. A reject reason is reduced to
its category (the text before the first ``:``, at most 40 characters) and
dropped if it still looks like a path; no file path, header value, date finer
than a night or site coordinate is reported.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from typing import Any

from seestack.diag import Diagnostic, DiagnosticStopped

_COLUMNS = ("accept", "reject_reason", "timestamp_utc", "exposure_s", "gain",
            "sensor_temp_c", "width_px", "height_px", "fwhm_px", "sky_adu_median",
            "mosaic_panel_id", "pixscale_arcsec")

#: Stack options worth seeing in the report (all plain values).
_OPTION_KEYS = ("drizzle", "drizzle_scale", "auto_drizzle", "background_flatten",
                "background_mode", "background_box_size", "sigma_clip", "sigma_kappa",
                "min_max_reject", "auto_reject", "quality_weighted", "photometric_normalize",
                "final_gradient_removal", "final_gradient_mode", "subpixel_refine",
                "color_calibration", "color_calibration_mode", "suppress_hot_pixels",
                "repair_sensor_defects", "panel_gain_match", "dark_master_id", "flat_master_id")


def _reason_category(reason: str | None) -> str | None:
    if not reason:
        return None
    cat = reason.split(":", 1)[0].strip()[:40]
    if not cat or "/" in cat or "\\" in cat:
        return "other"
    return cat


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _bucket(value: float | None, step: float) -> str | None:
    if value is None:
        return None
    return f"{round(value / step) * step:g}"


def _latest_run(proj) -> dict[str, Any] | None:  # noqa: ANN001
    runs = list(proj.iter_stack_runs())
    if not runs:
        return None
    r = runs[0]
    try:
        opts = json.loads(r.options_json or "{}")
    except ValueError:
        opts = {}
    return {
        "n_runs": len(runs),
        "n_frames_used": r.n_frames_used,
        "canvas_w": r.canvas_w, "canvas_h": r.canvas_h,
        "is_mosaic": bool(r.is_mosaic),
        "coverage_max": r.coverage_max,
        "noise_sigma": r.noise_sigma,
        "engine_version": r.engine_version,
        "options": {k: opts[k] for k in _OPTION_KEYS if k in opts
                    and isinstance(opts[k], (bool, int, float, str, type(None)))},
    }


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    entries = library.list_targets()
    targets: list[dict[str, Any]] = []
    exposures: Counter[str] = Counter()
    gains: Counter[str] = Counter()
    temps: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    reasons_all: Counter[str] = Counter()
    all_nights: set[str] = set()
    tot = {"subs": 0, "accepted": 0, "solved": 0, "hours": 0.0}
    for i, e in enumerate(entries):
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        if progress is not None:
            progress("reading the library record", i, len(entries))
        try:
            proj = library.open_target(e.safe_name)
        except Exception:  # noqa: BLE001 — a broken target is reported, not fatal
            targets.append({"name": e.name, "error": "could not open"})
            continue
        try:
            n = acc = solved = 0
            exp_s = 0.0
            nights: set[str] = set()
            panels: set[int] = set()
            fwhms: list[float] = []
            skies: list[float] = []
            reasons: Counter[str] = Counter()
            for (accept, reason, ts, exp, gain, temp, w, h, fwhm, sky, panel,
                 pix) in proj.iter_frame_columns(*_COLUMNS):
                n += 1
                if pix:
                    solved += 1
                if ts:
                    nights.add(ts[:10])
                if panel is not None:
                    panels.add(int(panel))
                if w and h:
                    sizes[f"{int(w)}x{int(h)}"] += 1
                exposures[_bucket(exp, 1) or "unknown"] += 1
                gains[_bucket(gain, 10) or "unknown"] += 1
                temps[_bucket(temp, 5) or "unknown"] += 1
                if accept:
                    acc += 1
                    if exp and exp > 0:
                        exp_s += float(exp)
                    if fwhm:
                        fwhms.append(float(fwhm))
                    if sky:
                        skies.append(float(sky))
                else:
                    cat = _reason_category(reason) or "no reason recorded"
                    reasons[cat] += 1
            reasons_all.update(reasons)
            all_nights |= nights
            tot["subs"] += n
            tot["accepted"] += acc
            tot["solved"] += solved
            tot["hours"] += exp_s / 3600.0
            targets.append({
                "name": e.name,
                "mosaic_folder": bool(getattr(e, "folder_name", None)
                                      and "mosaic" in str(e.folder_name).lower()),
                "subs": n, "accepted": acc,
                "solved_share": round(solved / n, 3) if n else None,
                "hours": round(exp_s / 3600.0, 2),
                "nights": len(nights),
                "mosaic_panels": len(panels),
                "median_fwhm_halfres_px": _median(fwhms),
                "median_sky_adu": _median(skies),
                "set_aside": dict(reasons.most_common(6)),
                "latest_stack": _latest_run(proj),
            })
        finally:
            proj.close()
    targets.sort(key=lambda t: -(t.get("subs") or 0))
    return {
        "totals": {"targets": len(entries), "subs": tot["subs"],
                   "accepted": tot["accepted"],
                   "solved_share": round(tot["solved"] / tot["subs"], 3) if tot["subs"] else None,
                   "hours": round(tot["hours"], 1), "nights": len(all_nights),
                   "targets_with_a_stack": sum(1 for t in targets if t.get("latest_stack"))},
        "exposure_s": dict(exposures.most_common(8)),
        "gain": dict(gains.most_common(8)),
        "sensor_temp_c": dict(sorted(temps.items())),
        "frame_size": dict(sizes.most_common(5)),
        "set_aside_reasons": dict(reasons_all.most_common(12)),
        "targets": targets,
    }


DIAGNOSTIC = Diagnostic(
    name="library_inventory",
    version=1,
    question=("What is in the library: targets, subs, mosaics, nights, solve rates, why "
              "subs were set aside, and how each target was last stacked? (1.0 roadmap R1)"),
    run=run,
    on_demand=True,
    ready=lambda library: bool(library.list_targets()),
)
