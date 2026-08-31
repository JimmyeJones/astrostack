"""Calibration masters: build, list and delete library-level dark/flat frames."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from webapp import calibration, deps, pipeline
from seestack.calibrate.masters import VALID_KINDS, VALID_METHODS

router = APIRouter(tags=["calibration"])


@router.get("/api/calibration/masters")
def list_masters(request: Request) -> list[dict[str, Any]]:
    settings = deps.get_settings(request)
    return calibration.list_masters(settings.resolved_library_root)


@router.post("/api/calibration/masters")
def build_master(body: dict[str, Any], request: Request) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)

    kind = str(body.get("kind", "")).lower()
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400,
                            detail=f"kind must be one of {VALID_KINDS}")
    method = str(body.get("method", "median")).lower()
    if method not in VALID_METHODS:
        raise HTTPException(status_code=400,
                            detail=f"method must be one of {VALID_METHODS}")
    source_dir = str(body.get("source_dir", "")).strip()
    if not source_dir:
        raise HTTPException(status_code=400, detail="source_dir is required")
    try:
        is_dir = Path(source_dir).is_dir()
    except (OSError, ValueError):
        # e.g. an embedded null byte raises ValueError on some platforms
        # rather than returning False — still a client-supplied bad path (400),
        # not a server fault (500).
        is_dir = False
    if not is_dir:
        raise HTTPException(status_code=400,
                            detail=f"source_dir is not a folder: {source_dir}")
    try:
        sigma = float(body.get("sigma", 3.0))
    except (TypeError, ValueError):
        sigma = 3.0

    job = pipeline.submit_build_master(
        settings, jm, kind=kind, source_dir=source_dir,
        name=str(body.get("name", "")).strip() or None,
        method=method, sigma=sigma,
    )
    return {"job_id": job.id}


def _median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


@router.get("/api/targets/{safe}/calibration-suggestions")
def calibration_suggestions(safe: str, request: Request) -> dict[str, Any]:
    """Recommend the dark/flat masters that best match this target's frames.

    Reads the median exposure/gain/sensor-temperature of the target's accepted
    frames and ranks the library's masters against them, so a beginner doesn't
    have to know which dark/flat goes with which lights. Purely advisory — the
    Stack form still lets the user pick anything (or nothing).

    ``params`` also carries the target's **modal raw frame dimensions**
    (``width_px``/``height_px``, ``None`` when the frames never recorded a size).
    A master built for a different camera or binning is not merely a poor match —
    ``CalibrationMasters.validate`` refuses it and the whole stack fails — so the
    form needs the subs' size to say so at pick time rather than letting the job
    die with a cryptic error. Additive keys; an older client just ignores them.

    ``tolerances`` carries the **engine's own** exposure/temperature mismatch
    thresholds. The Stack form warns about the same two mismatches at *pick* time
    that ``CalibrationMasters.calibration_warnings`` reports on the finished run,
    and until now each side chose its own threshold — so on a borderline pair the
    app could stay quiet before the night was spent and complain about it
    afterwards. Serving the numbers makes the engine the single source of truth;
    an older client that ignores the key just keeps its own built-in mirror.
    """
    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        frames = list(proj.iter_frames(accepted_only=True))
    finally:
        proj.close()
        lib.close()
    exposure_s = _median([f.exposure_s for f in frames if f.exposure_s])
    gain = _median([f.gain for f in frames if f.gain is not None])
    sensor_temp_c = _median([f.sensor_temp_c for f in frames if f.sensor_temp_c is not None])

    masters = calibration.list_masters(settings.resolved_library_root)
    rec = calibration.recommend_masters(
        masters, exposure_s=exposure_s, gain=gain, sensor_temp_c=sensor_temp_c)
    rec["params"]["width_px"] = calibration.modal_dim([f.width_px for f in frames])
    rec["params"]["height_px"] = calibration.modal_dim([f.height_px for f in frames])
    rec["n_frames"] = len(frames)
    # One source of truth for "is this master a poor match?" — see the docstring.
    # ``exposure_frac`` is measured against the *master's* exposure
    # (``|t_light / t_master − 1|``), exactly as ``calibration_warnings`` does.
    from seestack.calibrate.apply import EXPOSURE_MISMATCH_TOL, TEMP_MISMATCH_TOL_C

    rec["tolerances"] = {
        "exposure_frac": float(EXPOSURE_MISMATCH_TOL),
        "temp_c": float(TEMP_MISMATCH_TOL_C),
    }
    # …and what the *unattended* stack would have picked for these same subs.
    # ``recommend_masters`` above answers "the best master of each kind you own";
    # the walk-away chain answers the stricter "the best one we're confident
    # about", and the two can differ — a gain-mismatched-but-exposure-perfect
    # dark out-ranks a gain-matched dark that only needs bias-scaling, so the
    # form and the walk-away path could recommend different masters for one
    # target. Served as ids (what the form's pickers hold) from the same function
    # the unattended binding uses, so "Use recommended" lands where an unattended
    # stack would. Empty when nothing is confident — the form then keeps its
    # best-available recommendation and its existing cautions, which is right
    # when a human is watching.
    rec["confident"] = calibration.auto_bind_master_ids(
        settings.resolved_library_root, masters,
        exposure_s=exposure_s, gain=gain, sensor_temp_c=sensor_temp_c,
        width_px=rec["params"]["width_px"], height_px=rec["params"]["height_px"],
    )
    return rec


# The coverage roll-up opens every target's project SQLite and reads its accepted
# frames, so — unlike the registry-only master list — it is *not* free. Cache it on
# the app exactly like the Dashboard roll-ups do: the signature keys on each
# target's activity + accepted-frame count and on the master registry itself, so a
# fresh scan, a new master, or a deleted one invalidates it promptly; the TTL is
# the backstop for anything the signature misses.
_COVERAGE_CACHE_TTL_S = 60.0


@router.get("/api/calibration/coverage")
def calibration_coverage(request: Request) -> dict[str, Any]:
    """"Do my masters actually cover my targets?" — a read-only roll-up.

    For each master, how many of the library's targets the *unattended* binder
    would apply it to (and which it misses), plus the targets no master covers at
    all. It answers in one place a question the app currently makes a beginner
    answer target-by-target, on the Stack form or after an uncalibrated result.

    ``auto_apply`` reports whether ``auto_bind_calibration`` is actually on, so the
    page can promise "AstroStack will apply it for you" only when that's true. With
    it off (the default) a covered master is one the app *can* use — the user still
    picks it on the Stack form or saves it as the target's default — and the copy
    must say so rather than over-promising.

    Never raises on a bad target: a project that can't be opened is skipped, so
    one damaged target can't take the whole page down.
    """
    settings = deps.get_settings(request)
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
        masters = calibration.list_masters(settings.resolved_library_root)
        sig = (
            tuple(sorted((t.safe_name, t.last_activity_utc or "",
                          t.n_frames_accepted) for t in targets)),
            tuple(sorted((int(m.get("id", -1)), bool(m.get("exists", True)))
                         for m in masters)),
        )
        cache = getattr(request.app.state, "calibration_coverage_cache", None)
        now = time.monotonic()
        if cache and cache["sig"] == sig and (now - cache["at"]) < _COVERAGE_CACHE_TTL_S:
            data = cache["data"]
        else:
            rows = [_target_acquisition(lib, t) for t in targets]
            data = calibration.master_coverage(
                settings.resolved_library_root, masters,
                [r for r in rows if r is not None])
            request.app.state.calibration_coverage_cache = {
                "sig": sig, "at": now, "data": data}
        # Read live rather than cached: the setting can be flipped between polls
        # and it only changes the *wording*, never the (expensive) coverage maths.
        return {**data, "auto_apply": bool(settings.auto_bind_calibration)}
    finally:
        lib.close()


def _target_acquisition(lib: Any, entry: Any) -> dict[str, Any] | None:
    """One target's acquisition signature for :func:`calibration.master_coverage`,
    or ``None`` when its project can't be read (skip it rather than 500)."""
    try:
        proj = lib.open_target(entry.safe_name)
        try:
            frames = list(proj.iter_frames(accepted_only=True))
        finally:
            proj.close()
    except Exception:  # noqa: BLE001 — one unreadable target must not sink the page
        return None
    return {
        "name": entry.name, "safe_name": entry.safe_name,
        "exposure_s": _median([f.exposure_s for f in frames if f.exposure_s]),
        "gain": _median([f.gain for f in frames if f.gain is not None]),
        "sensor_temp_c": _median(
            [f.sensor_temp_c for f in frames if f.sensor_temp_c is not None]),
        "width_px": calibration.modal_dim([f.width_px for f in frames]),
        "height_px": calibration.modal_dim([f.height_px for f in frames]),
    }


@router.delete("/api/calibration/masters/{master_id}")
def delete_master(master_id: int, request: Request) -> dict[str, Any]:
    settings = deps.get_settings(request)
    if not calibration.delete_master(settings.resolved_library_root, master_id):
        raise HTTPException(status_code=404, detail="No such master")
    return {"deleted": master_id}
