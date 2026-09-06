"""Calibration masters: build, list and delete library-level dark/flat frames."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from webapp import calibration, deps, pipeline
from seestack.calibrate import discover
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
    # The subs' own colour-filter phase, so the form's "Use recommended" lands on
    # a flat the engine will actually accept (a flat one phase out divides red
    # photosites by a green correction — ``CalibrationMasters.validate`` refuses
    # it). Additive: an older client ignores the key.
    rec["params"]["bayer_pattern"] = calibration.modal_bayer(
        [f.bayer_pattern for f in frames])
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
        bayer_pattern=rec["params"]["bayer_pattern"],
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
        "bayer_pattern": calibration.modal_bayer(
            [f.bayer_pattern for f in frames]),
    }


@router.get("/api/calibration/incoming")
def calibration_incoming(request: Request) -> dict[str, Any]:
    """"You already have darks — shall I build the master?"

    Lists the folders under ``incoming/`` whose **frames' own ``IMAGETYP`` cards**
    say they are darks, flats or biases, so a beginner who has never heard of a
    master dark can build one in a click instead of learning what calibration is
    and finding the folder themselves.

    Nothing is inferred from a folder's *name*: a folder whose frames don't
    declare a kind is not offered at all (see
    :mod:`seestack.calibrate.discover`). ``incoming/`` is read-only here — a
    directory listing and a header read, nothing else — and this endpoint only
    ever *offers*; no master is built and none is applied until the owner asks.

    The folder walk (the expensive half — one header read per folder) is cached
    on the app and shared with the "why did this stack come out uncalibrated?"
    advice; "do I already have a master for this?" is registry arithmetic and is
    recomputed fresh on every request, so building a master updates the offer
    immediately without waiting for the TTL.
    """
    settings = deps.get_settings(request)
    root = str(settings.resolved_incoming_dir)
    folders = calibration.cached_incoming_folders(request.app.state, root)
    masters = calibration.list_masters(settings.resolved_library_root)
    out = []
    for f in folders:
        have = calibration.existing_master_like(
            masters, kind=f.kind, exposure_s=f.exposure_s, gain=f.gain,
            sensor_temp_c=f.sensor_temp_c,
            width_px=f.width_px, height_px=f.height_px,
        )
        out.append({
            "id": f.id,
            "name": f.folder_name,
            "rel_path": f.rel_path,
            "kind": f.kind,
            "declared": dict(f.declared),
            "n_frames": f.n_frames,
            "n_sampled": f.n_sampled,
            "exposure_s": f.exposure_s,
            "gain": f.gain,
            "sensor_temp_c": f.sensor_temp_c,
            "width_px": f.width_px,
            "height_px": f.height_px,
            "suggested_name": discover.suggested_master_name(f),
            # The master that already covers these frames, if any — so the offer
            # says "you already have this one" instead of inviting a duplicate.
            "have_master": (
                {"id": int(have["id"]), "name": str(have.get("name", ""))}
                if have else None
            ),
        })
    return {"incoming_dir": root, "folders": out}


@router.post("/api/calibration/incoming/{folder_id}/build")
def build_master_from_incoming(folder_id: str, request: Request) -> dict[str, str]:
    """Build a master from one discovered folder — the offer's one click.

    The folder is re-discovered **server-side** from its id, exactly as the video
    captures are: no filesystem path ever comes from the client, and a folder
    that has stopped looking like calibration frames since the page loaded is a
    404 rather than a build of whatever is there now.

    Discovery confirms the kind from only ``discover.SAMPLE_HEADERS`` sampled
    headers, so this path also asks the build to **drop a frame that declares a
    different slot** — a folder whose samples all read "dark" but which also holds
    lights would otherwise combine them, and a contaminated master dark corrupts
    every frame it is later applied to. A manual build the user aimed at a folder
    themselves is unchanged: it still takes what is in it.
    """
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    found = discover.find_calibration_folder(
        str(settings.resolved_incoming_dir), folder_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail="That folder is no longer there, or its frames no longer "
                   "say they are calibration frames.")
    job = pipeline.submit_build_master(
        settings, jm, kind=found.kind, source_dir=found.folder,
        name=discover.suggested_master_name(found), method="median",
        require_declared_kind=True,
    )
    # The offer's "you already have one" flag is registry arithmetic recomputed
    # per request, so it updates as soon as the build lands; the walk cache is
    # left alone (the folder itself hasn't changed).
    return {"job_id": job.id}


#: How many master censuses to keep. A master FITS never changes once written
#: (a rebuild takes a *new* id and filename), so the cache is keyed on the file's
#: own identity and needs no TTL — the cap exists only so a library that has been
#: rebuilt hundreds of times can't grow the map without bound.
_DEFECT_CACHE_MAX = 128


@router.get("/api/calibration/defects")
def calibration_defects(request: Request) -> dict[str, Any]:
    """"Does my camera have broken pixels, and can AstroStack fix them?"

    A read-only census of every *pedestal* master (dark, then bias — the two a
    defect map can be derived from): how many photosites it says are hot or
    stuck dark, and one plain-language line about it. The engine has been able
    to repair exactly those pixels since ``repair_sensor_defects`` shipped, but
    the setting lives in the Stack form's **advanced** group, so a beginner has
    no way to learn either that their sensor has broken pixels or that there is
    a one-switch fix. This is the surface that tells them, on the page where
    masters already live — not a new banner on the Stack form, which already
    carries enough calibration copy.

    Reading a master means loading its FITS and running the same per-phase local
    median the map is built from, so the answer is cached on the app keyed by
    each file's own identity (path + mtime + size). A master file is immutable
    once written, so a hit is always correct; a rebuilt master gets a new id and
    filename and so a new entry.

    Never raises on a bad master: one that can't be read is simply absent from
    the answer.
    """
    settings = deps.get_settings(request)
    root = settings.resolved_library_root
    cache = getattr(request.app.state, "calibration_defect_cache", None)
    if cache is None:
        cache = request.app.state.calibration_defect_cache = {}
    out: list[dict[str, Any]] = []
    for m in calibration.list_masters(root):
        if str(m.get("kind", "")).lower() not in calibration.DEFECT_CENSUS_KINDS:
            continue
        if not m.get("exists"):
            continue
        fp = calibration.calibration_dir(root) / str(m.get("filename", ""))
        try:
            st = fp.stat()
            key = (str(fp), st.st_mtime_ns, st.st_size)
        except OSError:
            continue
        if key in cache:
            census = cache[key]
        else:
            census = calibration.master_defect_census(fp)
            if len(cache) >= _DEFECT_CACHE_MAX:
                # Oldest-first: dicts preserve insertion order, and the oldest
                # entry is the master least likely to be on screen.
                cache.pop(next(iter(cache)))
            cache[key] = census
        if census is None:
            continue
        note = calibration.defect_note(census)
        out.append({"id": int(m.get("id", -1)), **census, "note": note})
    # The action beside the measurement: is there anything a repair could fix,
    # and is it already switched on? Read from the *global* stack defaults
    # because that is the one place both the Stack form's seed and the
    # unattended chain read — a per-run form tick reaches neither.
    enabled = _defect_repair_enabled(settings)
    offer = calibration.defect_repair_offer(
        out, enabled=enabled,
        # Only worth asking when the offer would say "every stack" — a target
        # walk on a 60 s poll has to earn itself, and with the switch off (or
        # nothing repairable) the answer changes no sentence.
        n_overridden=(_targets_overriding_defect_repair(request)
                      if enabled and _offer_wanted(out) else 0))
    return {"masters": out, "repair": offer}


def _offer_wanted(rows: list[dict[str, Any]]) -> bool:
    """Would :func:`~webapp.calibration.defect_repair_offer` render anything?

    Asked *before* building the offer so the target walk below is skipped on a
    library with nothing to repair. Deliberately the same predicate the offer
    itself applies, not a second one — it delegates rather than restating it.
    """
    return calibration.defect_repair_offer(rows, enabled=False) is not None


def _targets_overriding_defect_repair(request: Request) -> int:
    """How many targets' **saved** stack defaults pin the repair off.

    "Save as defaults" on the Stack form persists the whole form, so every target
    saved before ``repair_sensor_defects`` was switched on carries an explicit
    ``false`` — and a target's own saved blob wins over the global defaults in
    both readers. Without this count the on-state would claim "every stack" while
    those targets quietly opt out.

    One registry read plus one ``get_meta`` per target — cheap beside the master
    FITS this endpoint loads on a cache miss — and best-effort: a target whose
    project can't be opened (mid-delete, a locked DB) is skipped rather than
    500-ing the page.
    """
    from webapp.schemas import STACK_DEFAULTS_META_KEY
    from webapp.walkaway import parse_saved_stack_defaults

    key = calibration.DEFECT_REPAIR_OPTION
    n = 0
    lib = deps.open_library(request)
    try:
        for entry in lib.list_targets():
            try:
                proj = lib.open_target(entry.safe_name)
            except Exception:  # noqa: BLE001 — one bad target must not sink the page
                continue
            try:
                saved = parse_saved_stack_defaults(proj.get_meta(
                    STACK_DEFAULTS_META_KEY))
            except Exception:  # noqa: BLE001 — same
                saved = {}
            finally:
                proj.close()
            # Only a *pinned off* counts. A target that saved it on, or never
            # saved this key at all, follows the global switch.
            if key in saved and not saved[key]:
                n += 1
    finally:
        lib.close()
    return n


def _defect_repair_enabled(settings: Any) -> bool:
    """Is the sensor-defect repair on in the global stack defaults?

    Tolerant of a hand-edited or legacy ``config.json``: the store persists
    ``default_stack_options`` as an opaque dict, so a non-dict value (or a
    missing key, which is every install predating the option) reads as off
    rather than raising.
    """
    dso = getattr(settings, "default_stack_options", None)
    if not isinstance(dso, dict):
        return False
    return bool(dso.get(calibration.DEFECT_REPAIR_OPTION))


@router.post("/api/calibration/defects/repair")
def set_defect_repair(request: Request,
                      body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Turn the sensor-defect repair on (or off) for **future** stacks.

    The one-click behind :func:`~webapp.calibration.defect_repair_offer`. It
    writes ``repair_sensor_defects`` into the global ``default_stack_options``,
    which is what the Stack form seeds from *and* what the hands-off auto-stack
    chain merges — so the census line the owner is looking at becomes an action
    that also reaches the path with no form on it.

    Deliberately a *setting*, not a default: the shipped default stays off
    (AGENTS.md §9), nothing already on disk changes, and no finished picture is
    touched. It is exactly reversible — ``{"enabled": false}`` removes the key
    again, leaving the options blob as it was before the first click, so a user
    who turns it on and off is byte-for-byte back where they started.

    The read-modify-write happens here rather than in the browser so a click
    can't clobber a concurrent edit to another stack default.
    """
    enabled = True if body is None else bool(body.get("enabled", True))
    store = deps.get_settings_store(request)
    current = store.get().default_stack_options
    opts = dict(current) if isinstance(current, dict) else {}
    if enabled:
        opts[calibration.DEFECT_REPAIR_OPTION] = True
    else:
        # Remove rather than store ``False``: the option's own default is off,
        # so an absent key and a stored ``False`` mean the same thing to every
        # reader, and dropping it leaves no residue from a click the user undid.
        opts.pop(calibration.DEFECT_REPAIR_OPTION, None)
    store.update({"default_stack_options": opts})
    return {"enabled": enabled}


@router.delete("/api/calibration/masters/{master_id}")
def delete_master(master_id: int, request: Request) -> dict[str, Any]:
    settings = deps.get_settings(request)
    if not calibration.delete_master(settings.resolved_library_root, master_id):
        raise HTTPException(status_code=404, detail="No such master")
    return {"deleted": master_id}
