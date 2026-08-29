"""Targets (library view) endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from webapp import deps
from webapp.goals import GOAL_META_KEY, MAX_GOAL_S, MIN_GOAL_S, read_goal_s
from webapp.registry_cache import invalidate_registry_cache
from webapp.schemas import (
    AngularSizeOut,
    AutoStackHoldOut,
    BackgroundModeHintOut,
    BestFrameOut,
    CleanestShotOut,
    CleanupSuggestionOut,
    DarkSpecOut,
    DifficultyHintOut,
    FocusTrendOut,
    FocusTrendPointOut,
    FramingHintOut,
    GrainierNewestOut,
    HealthNoteOut,
    IntegrationGoalOut,
    IntegrationGoalPatch,
    LightTravelOut,
    LiveConditionsOut,
    LiveSessionOut,
    MergeRequest,
    MergeSuggestionOut,
    MergeSuggestionTarget,
    MosaicPlanOut,
    NightSummaryOut,
    ObjectInfoOut,
    SessionQualityDriftOut,
    SessionRecapOut,
    SetCoverRequest,
    StackHealthOut,
    TargetCreate,
    TargetOut,
    TargetPatch,
    TransparencyTrendOut,
    TransparencyTrendPointOut,
)
from webapp.site_location import detect_site_cached, resolve_site_lon

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/targets", tags=["targets"])

# The user's per-target integration goal — its meta key, its sanity bounds and
# the tolerant parse — lives in ``webapp.goals``: one definition shared by this
# router, the Dashboard roll-up and the Tonight planner, so no two screens can
# disagree about the same target's goal.


def _to_out(entry) -> TargetOut:  # noqa: ANN001
    return TargetOut(
        safe_name=entry.safe_name,
        name=entry.name,
        ra_deg=entry.ra_deg,
        dec_deg=entry.dec_deg,
        n_frames=entry.n_frames,
        n_frames_accepted=entry.n_frames_accepted,
        total_exposure_s=entry.total_exposure_s,
        last_activity_utc=entry.last_activity_utc,
        has_preview=bool(entry.last_stack_preview and Path(entry.last_stack_preview).exists()),
        notes=entry.notes,
        tags=list(entry.tags),
        cover_stack_run_id=entry.cover_stack_run_id,
    )


@router.get("", response_model=list[TargetOut])
def list_targets(request: Request) -> list[TargetOut]:
    lib = deps.open_library(request)
    try:
        return [_to_out(t) for t in lib.list_targets()]
    finally:
        lib.close()


@router.post("", response_model=TargetOut, status_code=201)
def create_target(body: TargetCreate, request: Request) -> TargetOut:
    lib = deps.open_library(request)
    try:
        try:
            entry, proj = lib.create_target(body.name)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        proj.close()
        return _to_out(entry)
    finally:
        lib.close()


@router.post("/merge")
def merge_targets(body: MergeRequest, request: Request) -> dict:
    lib = deps.open_library(request)
    try:
        try:
            added = lib.merge_targets(body.into, body.sources)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"into": body.into, "frames_added": added}
    finally:
        lib.close()


@router.get("/merge-suggestions", response_model=list[MergeSuggestionOut])
def merge_suggestions(request: Request) -> list[MergeSuggestionOut]:
    """Detect targets that look like the *same sky object* split across separate
    folders/nights (the Seestar writes a new folder per night), so the Library can
    offer a one-click "combine into one deep stack" nudge. Read-only: it only
    reads each target's plate-solved centre + integration figures and clusters by
    sky position; it never merges anything (the user confirms via ``POST
    /merge``). Returns ``[]`` when nothing clusters."""
    from seestack.io.library import find_same_object_target_groups
    from seestack.objectinfo import identify_object

    lib = deps.open_library(request)
    try:
        groups = find_same_object_target_groups(lib.list_targets())
    finally:
        lib.close()

    out: list[MergeSuggestionOut] = []
    for g in groups:
        # Name the cluster from its deepest member (offline catalog), best-effort —
        # a null name just drops the "(M 31)" clause in the nudge, never errors.
        info = identify_object(g.members[0].name, g.center_ra_deg, g.center_dec_deg)
        object_name = (info.name or info.id) if info else None
        out.append(MergeSuggestionOut(
            object_name=object_name,
            center_ra_deg=g.center_ra_deg,
            center_dec_deg=g.center_dec_deg,
            max_sep_arcmin=g.max_sep_deg * 60.0,
            targets=[
                MergeSuggestionTarget(
                    safe=m.safe_name,
                    name=m.name,
                    n_frames_accepted=m.n_frames_accepted,
                    total_exposure_s=m.total_exposure_s,
                )
                for m in g.members
            ],
        ))
    return out


# A real light-frame stack has many subs; only a 1-frame on-device output (or a
# ``_video`` target, handled by name regardless of count) is a cleanup candidate.
# Skipping the big ones by frame count avoids opening their projects and scanning
# thousands of source paths on every poll.
_MAX_CLEANUP_FRAMES = 2


@router.get("/cleanup-suggestions", response_model=list[CleanupSuggestionOut])
def cleanup_suggestions(request: Request) -> list[CleanupSuggestionOut]:
    """Detect leftover targets a pre-v0.184.9 scan built before the scanner learned
    the Seestar folder convention, so the Library can offer a one-click "remove
    these" cleanup. Two kinds: (1) *junk* targets built from the Seestar's own
    output / ``_video`` folders (not raw subs, cannot be stacked); (2)
    ``<T>_sub``-named *duplicates* holding the same raw subs the base target ``<T>``
    now owns (clutter + double compute, not corrupt data). Read-only: it never
    deletes anything (the user confirms via ``DELETE /api/targets/{safe}``), and
    never touches the real ``_sub`` data or the base target. Returns ``[]`` when
    the library is clean."""
    from seestack.io.library import make_safe_name
    from seestack.io.scanner import (
        classify_seestar_junk_target,
        duplicate_sub_target_base_name,
    )

    lib = deps.open_library(request)
    out: list[CleanupSuggestionOut] = []
    try:
        targets = lib.list_targets()
        by_safe = {t.safe_name: t for t in targets}
        for entry in targets:
            # --- (0) legacy whole-device / mixed-folder container drop ---------
            # Flagged at scan time (a registry column) when a container-expansion
            # re-scan found the pre-existing giant target an old scan built from
            # the same container. It's a *large* target (all several objects'
            # subs), so the cheap frame-count-gated detectors below never open it —
            # the flag lets us surface it here without re-reading source paths.
            if entry.legacy_mixed_drop:
                out.append(CleanupSuggestionOut(
                    safe=entry.safe_name,
                    name=entry.name,
                    n_frames=entry.n_frames,
                    reason="legacy_mixed_drop",
                    detail=(
                        "A leftover from an older scan that lumped a whole Seestar "
                        "card or share into one target — it mixes several different "
                        "objects' subs (plus the Seestar's own finished images and "
                        "videos), so stacking it just makes a mess. The app has "
                        "since re-sorted those frames into their own proper targets, "
                        "so this jumbled one is now a stale duplicate. Removing it "
                        "leaves your raw sub folders on disk untouched."
                    ),
                ))
                continue
            # --- (1) output/video junk (cheap: only small targets opened) -----
            is_video_name = entry.name.strip().lower().endswith("_video")
            if is_video_name or entry.n_frames <= _MAX_CLEANUP_FRAMES:
                source_paths: list[str] = []
                if not is_video_name:
                    proj = lib.open_target(entry.safe_name)
                    try:
                        source_paths = [f.source_path for f in proj.iter_frames()]
                    finally:
                        proj.close()
                verdict = classify_seestar_junk_target(
                    entry.name, source_paths, entry.n_frames)
                if verdict is not None:
                    out.append(CleanupSuggestionOut(
                        safe=entry.safe_name,
                        name=entry.name,
                        n_frames=entry.n_frames,
                        reason=verdict.reason,
                        detail=verdict.detail,
                    ))
                    continue  # a junk target is never also a duplicate

            # --- (2) <T>_sub duplicate of a base target that now owns the subs -
            # Cheap name-shape prefilter: only ``_sub``-named targets (rare) reach
            # the project-opening confirmation below.
            low = entry.name.strip().lower()
            if not low.endswith("_sub") or low.endswith("_mosaic_sub"):
                continue
            proj = lib.open_target(entry.safe_name)
            try:
                dup_sources = [f.source_path for f in proj.iter_frames()]
                # A genuine leftover duplicate holds nothing but re-registered raw
                # subs. If this target *also* carries the user's own data — a
                # stack-run history — then it is not disposable: the frontend's
                # one-click cleanup deletes the registry target (keeping the files
                # on disk), which would silently drop that history from the UI.
                # Never offer such a target for removal (the base owns the subs,
                # but the runs live only here). See the notes check below for the
                # matching free-text-notes guard.
                dup_has_runs = next(proj.iter_stack_runs(), None) is not None
            finally:
                proj.close()
            base_name = duplicate_sub_target_base_name(entry.name, dup_sources)
            if base_name is None:
                continue
            base = by_safe.get(make_safe_name(base_name))
            if base is None or base.safe_name == entry.safe_name:
                continue
            base_proj = lib.open_target(base.safe_name)
            try:
                base_sources = {f.source_path for f in base_proj.iter_frames()}
            finally:
                base_proj.close()
            # Offer removal only when the base already owns *every* one of these
            # subs — so nothing real is lost, and the message is truthful — and
            # only when this duplicate carries no user-owned data of its own
            # (stack-run history or free-text notes), which a one-click removal
            # would drop from the UI even though the files stay on disk.
            dup_has_notes = bool((entry.notes or "").strip())
            if (
                dup_sources
                and all(s in base_sources for s in dup_sources)
                and not dup_has_runs
                and not dup_has_notes
            ):
                out.append(CleanupSuggestionOut(
                    safe=entry.safe_name,
                    name=entry.name,
                    n_frames=entry.n_frames,
                    reason="duplicate_sub",
                    detail=(
                        "A leftover from an older scan — these are the same raw "
                        f"subs, now already in your “{base.name}” target. Removing "
                        "this duplicate tidies your library and saves re-stacking "
                        "the same frames twice; your files on disk are untouched."
                    ),
                ))
    finally:
        lib.close()
    return out


@router.get("/{safe}", response_model=TargetOut)
def get_target(safe: str, request: Request) -> TargetOut:
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        return _to_out(entry)
    finally:
        lib.close()


@router.get("/{safe}/identify", response_model=ObjectInfoOut | None)
def identify_target(safe: str, request: Request) -> ObjectInfoOut | None:
    """Match this target against the bundled deep-sky catalog (offline) and
    return friendly context — common name, type, constellation, catalog id — or
    ``null`` when nothing matches confidently. Read-only; renders the
    "What am I looking at?" card. Matches by the target's name first, then by its
    plate-solved centre if one is known."""
    from seestack.objectinfo import identify_object

    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        info = identify_object(entry.name, entry.ra_deg, entry.dec_deg)
    finally:
        lib.close()
    if info is None:
        return None
    return ObjectInfoOut(
        id=info.id, name=info.name, type=info.type,
        constellation=info.constellation, constellation_abbr=info.constellation_abbr,
        ra_deg=info.ra_deg, dec_deg=info.dec_deg, matched_by=info.matched_by,
        size_arcmin=info.size_arcmin,
        framing=(FramingHintOut(level=info.framing.level, text=info.framing.text)
                 if info.framing is not None else None),
        mosaic=(MosaicPlanOut(cols=info.mosaic.cols, rows=info.mosaic.rows,
                              panels=info.mosaic.panels, text=info.mosaic.text)
                if info.mosaic is not None else None),
        blurb=info.blurb,
        difficulty=(DifficultyHintOut(level=info.difficulty.level,
                                      label=info.difficulty.label,
                                      text=info.difficulty.text)
                    if info.difficulty is not None else None),
        background_mode_hint=(
            BackgroundModeHintOut(mode=info.background_mode_hint.mode,
                                  text=info.background_mode_hint.text)
            if info.background_mode_hint is not None else None),
        light_travel=(LightTravelOut(distance_ly=info.light_travel.distance_ly,
                                     years=info.light_travel.years,
                                     text=info.light_travel.text)
                      if info.light_travel is not None else None),
        angular_size=(AngularSizeOut(size_arcmin=info.angular_size.size_arcmin,
                                     moons=info.angular_size.moons,
                                     text=info.angular_size.text)
                      if info.angular_size is not None else None),
    )


@router.get("/{safe}/autostack-hold", response_model=AutoStackHoldOut | None)
def target_autostack_hold(safe: str, request: Request) -> AutoStackHoldOut | None:
    """Whether the most recent hands-off scan held *this* target's stack back
    because some of its subs had no file on disk, or ``null``.

    The hold is already recorded per-target in the scan job's summary
    (``auto_stack_held_unreadable``) and explained on the Jobs page; this is the
    same fact at the surface a beginner actually looks at when their picture
    stops updating. Deliberately reads **only the newest finished scan**: a hold
    the next scan resolved is history, not news, so the note self-clears with no
    state of its own to go stale. Read-only — it re-reads a job record and never
    touches the frames or their files.
    """
    lib = deps.open_library(request)
    try:
        if lib.find_target(safe) is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
    finally:
        lib.close()
    jm = deps.get_job_manager(request)
    for job in jm.list(limit=200):  # newest first
        if job.kind != "pipeline" or job.state != "done":
            continue
        held = (job.result or {}).get("auto_stack_held_unreadable")
        if not isinstance(held, list):
            return None  # the newest scan reported no hold — nothing to say
        for entry in held:
            if isinstance(entry, dict) and entry.get("target") == safe:
                return AutoStackHoldOut(
                    offered=int(entry.get("offered") or 0),
                    readable=int(entry.get("readable") or 0),
                    unreadable=int(entry.get("unreadable") or 0),
                    reason=(entry.get("reason") if isinstance(
                        entry.get("reason"), str) else None),
                    when_utc=job.finished_utc,
                )
        return None
    return None


@router.get("/{safe}/cleanest-shot", response_model=CleanestShotOut | None)
def target_cleanest_shot(safe: str, request: Request) -> CleanestShotOut | None:
    """Offer to promote the newest stack to cover when it's materially cleaner
    than the pinned one, or ``null`` when there's nothing to say.

    A pinned cover stays pinned forever — right, because the choice is the
    user's — but a beginner who keeps adding subs gets steadily cleaner stacks
    while every showcase surface (Library tile, "My best pictures", the montage
    wall) keeps showing the older picture. This is that gap, stated once, with
    the same one-tap ``set-cover`` the History page already offers. It never
    swaps the cover by itself.

    Compares like with like: only *genuine* stack runs (editor-export / combine
    runs are skipped — their σ isn't measured on the same kind of image), and
    only when both runs carry a usable noise σ. Read-only.
    """
    from seestack.covernudge import cleanest_shot
    from webapp.pipeline import _stack_options_from_run_json

    lib, proj = deps.open_target_project(request, safe)
    try:
        entry = lib.find_target(safe)
        cover_id = entry.cover_stack_run_id if entry is not None else None
        runs = [r for r in proj.iter_stack_runs()  # newest first
                if _stack_options_from_run_json(r.options_json) is not None]
    finally:
        proj.close()
        lib.close()
    shot = cleanest_shot(runs, cover_id)
    if shot is None:
        return None
    # Never offer a cover whose picture is gone: pinning it would leave every
    # showcase surface falling back to the newest stack anyway (see
    # ``_cover_preview_path``), which makes the nudge look broken.
    candidate = next((r for r in runs if r.id == shot.run_id), None)
    if candidate is None or not candidate.preview_path:
        return None
    if not Path(candidate.preview_path).exists():
        return None
    return CleanestShotOut(
        run_id=shot.run_id,
        cover_run_id=shot.cover_run_id,
        noise_sigma=shot.noise_sigma,
        cover_noise_sigma=shot.cover_noise_sigma,
        percent_cleaner=shot.percent_cleaner,
        n_frames_used=shot.n_frames_used,
        cover_n_frames_used=shot.cover_n_frames_used,
        timestamp_utc=shot.timestamp_utc,
    )


@router.get("/{safe}/grainier-newest", response_model=GrainierNewestOut | None)
def target_grainier_newest(safe: str, request: Request) -> GrainierNewestOut | None:
    """Offer to pin an earlier, cleaner stack when the newest one came out
    materially grainier — or ``null`` when there's nothing to say.

    The mirror of ``cleanest-shot``, for the state a beginner is actually in.
    With nothing pinned the cover simply *follows* the newest stack, so a restack
    through haze (or one that set a lot of subs aside) silently replaces a better
    picture on the Library tile, "My best pictures" and the montage wall. This is
    that silent regression, said once, with the same one-tap ``set-cover``. It
    never pins anything by itself, and it can never speak at the same time as
    ``cleanest-shot``: that one needs a pin, this one needs none.

    Compares like with like — only *genuine* stack runs — and only offers a run
    whose picture is actually on disk. Read-only.
    """
    from seestack.covernudge import grainier_newest
    from webapp.pipeline import _stack_options_from_run_json

    lib, proj = deps.open_target_project(request, safe)
    try:
        entry = lib.find_target(safe)
        cover_id = entry.cover_stack_run_id if entry is not None else None
        all_runs = list(proj.iter_stack_runs())  # newest first
    finally:
        proj.close()
        lib.close()
    runs = [r for r in all_runs
            if _stack_options_from_run_json(r.options_json) is not None]
    nudge = grainier_newest(runs, cover_id)
    if nudge is None:
        return None
    # Only speak when the grainy newest stack is genuinely the picture on show.
    # Unpinned, every showcase surface takes the newest run *with a preview* out
    # of *all* runs, which can be an editor export rather than the newest genuine
    # stack — and telling the owner their picture got grainier while a different
    # image is on screen would just be wrong. Ask the same helper the wall does,
    # so the two can't drift apart.
    from webapp.routers.gallery import _representative_run

    shown, _pinned = _representative_run(all_runs, cover_id)
    if shown is None or shown.id != nudge.newest_run_id:
        return None
    # Never offer a cover whose picture is gone: pinning it would fall straight
    # back to the newest stack anyway, which makes the nudge look broken.
    better = next((r for r in runs if r.id == nudge.run_id), None)
    if better is None or not better.preview_path:
        return None
    if not Path(better.preview_path).exists():
        return None
    return GrainierNewestOut(
        run_id=nudge.run_id,
        newest_run_id=nudge.newest_run_id,
        noise_sigma=nudge.noise_sigma,
        newest_noise_sigma=nudge.newest_noise_sigma,
        percent_grainier=nudge.percent_grainier,
        n_frames_used=nudge.n_frames_used,
        newest_n_frames_used=nudge.newest_n_frames_used,
        timestamp_utc=nudge.timestamp_utc,
    )


def _recap_observer(request: Request, lib, settings):  # noqa: ANN001, ANN202
    """Where the telescope is, for the retrospective Moon note — or ``None``.

    Same precedence every planning surface uses (``plan.py``'s
    ``_resolve_observer``): an explicit Settings location wins, else the site
    sniffed from a solved frame's header, which is the common Seestar case
    because a beginner rarely configures one. ``None`` when neither is known, and
    the note simply doesn't appear — an unknown site must never cost the card.
    """
    from seestack.nightplan import Observer

    if settings.site_lat is not None and settings.site_lon is not None:
        return Observer(lat_deg=float(settings.site_lat),
                        lon_deg=float(settings.site_lon),
                        elevation_m=float(settings.site_elevation_m or 0.0))
    site = detect_site_cached(request, lib)
    if site is None:
        return None
    return Observer(lat_deg=site[0], lon_deg=site[1],
                    elevation_m=float(settings.site_elevation_m or 0.0))


def _session_moon_note(observer, target_pos, start_utc: str | None,  # noqa: ANN001
                       end_utc: str | None) -> str | None:
    """"Was the Moon washing this out?" for one finished session, or ``None``.

    Quiet by design — it returns a sentence only when the Moon was bright, up and
    close while this target was being shot, which is the one case where a
    beginner's disappointing picture has a sky-side explanation they can act on
    ("shoot it again on a dark-Moon night"). Everything else — a good or merely
    passable night, no site, no solved position, an undatable session, or an
    ephemeris that won't compute — reads as "nothing worth saying", so the card
    stays clean.
    """
    ra, dec = target_pos
    if observer is None or ra is None or dec is None or not start_utc:
        return None
    from seestack.nightplan import session_moon

    try:
        start = datetime.fromisoformat(start_utc)
        end = datetime.fromisoformat(end_utc) if end_utc else start
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return session_moon(observer, float(ra), float(dec), start, end).text
    except Exception:  # noqa: BLE001 — an ephemeris hiccup must not cost the card
        log.debug("session Moon note unavailable", exc_info=True)
        return None


@router.get("/{safe}/session-recap", response_model=SessionRecapOut | None)
def target_session_recap(safe: str, request: Request) -> SessionRecapOut | None:
    """A friendly, plain-language recap of the target's most recent capture
    session — how many subs it added, how many were kept vs. set aside (and why,
    in plain buckets), and the target's total integration now. Returns ``null``
    when there's nothing datable to report (no frame carries a capture time).
    Read-only aggregation over the frames table; renders the "Last session" card.

    The recap also carries the **observing-night** date its session belongs to
    (same noon-to-noon local bucketing as the Nights card and the Dashboard's
    imaging calendar), so a beginner reading "27 subs kept" can tell whether that
    was last night or three weeks ago — and so the two cards can never name the
    same session's night differently.

    ...and, when a bright Moon was genuinely up and close to this target while it
    was being shot, one plain-language ``moon_note`` saying so. The planner warns
    about the Moon *before* a night; nothing said it afterwards, so a beginner who
    shot a faint nebula under a full Moon saw a flat picture and blamed their gear
    or their editing. Silent on every other night (see :func:`_session_moon_note`).
    """
    from seestack.activity_calendar import night_date_of
    from seestack.session_recap import session_recap

    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        recap = session_recap(proj)
        lon = resolve_site_lon(request, lib, settings.site_lon)
        entry = lib.find_target(safe)
        observer = _recap_observer(request, lib, settings)
        target_pos = (entry.ra_deg, entry.dec_deg) if entry is not None else (None, None)
    finally:
        proj.close()
        lib.close()
    if recap is None:
        return None
    night = night_date_of(recap.start_utc, lon) if recap.start_utc else None
    moon_note = _session_moon_note(observer, target_pos, recap.start_utc, recap.end_utc)
    drift = recap.quality_drift
    return SessionRecapOut(
        n_frames=recap.n_frames,
        n_kept=recap.n_kept,
        n_set_aside=recap.n_set_aside,
        session_exposure_s=recap.session_exposure_s,
        kept_exposure_s=recap.kept_exposure_s,
        total_kept_exposure_s=recap.total_kept_exposure_s,
        start_utc=recap.start_utc,
        end_utc=recap.end_utc,
        night_date=night.isoformat() if night is not None else None,
        moon_note=moon_note,
        reject_buckets=recap.reject_buckets,
        quality_drift=(
            SessionQualityDriftOut(
                kind=drift.kind,
                latest_fwhm_px=drift.latest_fwhm_px,
                baseline_fwhm_px=drift.baseline_fwhm_px,
                n_latest=drift.n_latest,
                n_baseline=drift.n_baseline,
            )
            if drift is not None
            else None
        ),
    )


@router.get("/{safe}/live-session", response_model=LiveSessionOut | None)
def target_live_session(safe: str, request: Request) -> LiveSessionOut | None:
    """**"Tonight, live"** — how the session happening *right now* is going.

    The forward-looking planner says what is up; the session recap says what last
    night gave you. Neither answers the two questions a beginner standing outside
    in the cold actually has — *"is this actually working?"* and *"have I got
    enough to go inside?"* — and the app knows both, live: the watcher QCs each
    sub within a minute or two of it landing, so it holds every sub's accept
    verdict and star size while the night is still running.

    Returns the trailing capture session with an ``active`` flag (the newest sub
    is recent enough for the night to still be in progress), the counts and
    integration so far, a rolling read of how the last ~20 subs have gone, and the
    target's goal when one is set. ``null`` when the target has no datable frames
    at all, so the page shows its empty state rather than an invented night.

    Read-only aggregation over the ``frames`` table — safe to call while a scan,
    an ingest or a stack is running, which is exactly when it will be called.
    """
    from seestack.livesession import live_session

    lib, proj = deps.open_target_project(request, safe)
    try:
        live = live_session(proj)
        goal_s = read_goal_s(proj)
    finally:
        proj.close()
        lib.close()
    if live is None:
        return None
    c = live.conditions
    return LiveSessionOut(
        active=live.active,
        n_frames=live.n_frames,
        n_kept=live.n_kept,
        n_set_aside=live.n_set_aside,
        kept_exposure_s=live.kept_exposure_s,
        session_exposure_s=live.session_exposure_s,
        total_kept_exposure_s=live.total_kept_exposure_s,
        start_utc=live.start_utc,
        latest_utc=live.latest_utc,
        minutes_since_latest=live.minutes_since_latest,
        conditions=LiveConditionsOut(
            verdict=c.verdict,
            n_recent=c.n_recent,
            n_recent_kept=c.n_recent_kept,
            median_fwhm_px=c.median_fwhm_px,
            recent_buckets=c.recent_buckets,
        ),
        reject_buckets=live.reject_buckets,
        newest_kept_frame_id=live.newest_kept_frame_id,
        goal_exposure_s=goal_s,
    )


@router.get("/{safe}/nights", response_model=list[NightSummaryOut])
def target_nights(safe: str, request: Request) -> list[NightSummaryOut]:
    """Every capture night that went into this target, newest first — the
    "Nights" card. The §1 owner shoots one target across many nights (the Seestar
    writes a new folder per night), and today there's no per-target view of *all*
    the nights behind a picture. This lists each night's subs kept vs set aside,
    integration, median FWHM, and a one-word verdict (sharp / soft / hazy) from
    metrics already stored, so a clouded-out or soft night is easy to spot. Purely
    informational and read-only — it never rejects anything. ``[]`` when there's
    nothing datable (no frame carries a capture time).

    Each night also carries the **observing-night date** it belongs to, bucketed
    noon-to-noon in the observer's local time exactly as the Dashboard's imaging
    calendar does. Labelling from the raw UTC start instead named the *following*
    day for any observer west of UTC — a 21:00 local start in the Americas is
    already tomorrow in UTC — so the two cards disagreed about which night a
    session was."""
    from seestack.activity_calendar import night_date_of
    from seestack.session_recap import nights_breakdown

    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        nights = nights_breakdown(proj)
        lon = resolve_site_lon(request, lib, settings.site_lon)
    finally:
        proj.close()
        lib.close()

    def _night_date(ts: str | None) -> str | None:
        if not ts:
            return None
        d = night_date_of(ts, lon)
        return d.isoformat() if d is not None else None

    return [
        NightSummaryOut(
            start_utc=n.start_utc,
            end_utc=n.end_utc,
            night_date=_night_date(n.start_utc),
            n_frames=n.n_frames,
            n_kept=n.n_kept,
            n_set_aside=n.n_set_aside,
            exposure_s=n.exposure_s,
            kept_exposure_s=n.kept_exposure_s,
            median_fwhm_px=n.median_fwhm_px,
            verdict=n.verdict,
            is_best=n.is_best,
            reject_buckets=n.reject_buckets,
        )
        for n in nights
    ]


@router.get("/{safe}/focus-trend", response_model=FocusTrendOut | None)
def target_focus_trend(safe: str, request: Request) -> FocusTrendOut | None:
    """Star-sharpness (FWHM) through the target's most recent capture night — the
    "Focus & sharpness" card. The Seestar shoots unattended for hours, and a
    beginner has no easy way to see whether their stars stayed sharp all night or
    drifted soft partway through (dew on the lens, temperature/focus drift). This
    returns each accepted, measured sub's FWHM over capture time plus a plain
    verdict (steady / softened / improved), all from data already stored. Purely
    informational and read-only — it never rejects anything. ``null`` when the
    latest session has too few measured subs to trend (the card self-hides)."""
    from seestack.session_recap import focus_trend

    lib, proj = deps.open_target_project(request, safe)
    try:
        trend = focus_trend(proj)
    finally:
        proj.close()
        lib.close()
    if trend is None:
        return None
    return FocusTrendOut(
        verdict=trend.verdict,
        points=[
            FocusTrendPointOut(t_utc=p.t_utc, fwhm_px=p.fwhm_px) for p in trend.points
        ],
        n_points=trend.n_points,
        median_fwhm_px=trend.median_fwhm_px,
        early_fwhm_px=trend.early_fwhm_px,
        late_fwhm_px=trend.late_fwhm_px,
        start_utc=trend.start_utc,
        end_utc=trend.end_utc,
        soft_after_utc=trend.soft_after_utc,
    )


@router.get("/{safe}/transparency-trend", response_model=TransparencyTrendOut | None)
def target_transparency_trend(safe: str, request: Request) -> TransparencyTrendOut | None:
    """Sky clarity (transparency) through the target's most recent capture night —
    the "Clouds & haze" card. Clouds and haze are the single most common reason a
    beginner's stack comes out thin, and the app never *explains* when the sky went
    bad. This returns each accepted, measured sub's transparency over capture time
    plus a plain verdict (clear / degraded / cleared), all from data already stored,
    and reassures the beginner that any hazy subs were already auto-down-weighted.
    Purely informational and read-only — it never rejects anything. ``null`` when
    the latest session has too few measured subs to trend (the card self-hides)."""
    from seestack.session_recap import transparency_trend

    lib, proj = deps.open_target_project(request, safe)
    try:
        trend = transparency_trend(proj)
    finally:
        proj.close()
        lib.close()
    if trend is None:
        return None
    return TransparencyTrendOut(
        verdict=trend.verdict,
        points=[
            TransparencyTrendPointOut(t_utc=p.t_utc, transparency=p.transparency)
            for p in trend.points
        ],
        n_points=trend.n_points,
        median_transparency=trend.median_transparency,
        early_transparency=trend.early_transparency,
        late_transparency=trend.late_transparency,
        start_utc=trend.start_utc,
        end_utc=trend.end_utc,
        degraded_after_utc=trend.degraded_after_utc,
    )


@router.get("/{safe}/stack-health", response_model=StackHealthOut | None)
def target_stack_health(
    safe: str, request: Request, run_id: int | None = None
) -> StackHealthOut | None:
    """Plain-language "How's my stack?" check on a stack: what's strong and the
    single highest-value next step, from cues we already compute (the run's
    stamped fields + the frames' QC metrics). With no ``run_id`` it grades the
    target's newest genuine stack (the Target-page card); with ``run_id`` it
    grades that specific run (the History card for a run you're viewing). Returns
    ``null`` when there's no matching genuine stack. Read-only; never a gate.
    """
    from webapp.pipeline import _newest_genuine_stack_run, _stack_options_from_run_json
    from seestack.stackhealth import recommended_dark_spec, stack_health

    lib, proj = deps.open_target_project(request, safe)
    try:
        if run_id is None:
            run = _newest_genuine_stack_run(proj)
        else:
            # Grade the specific run — but only if it's a genuine stack (skip
            # editor-export/combine runs, whose stamped fields don't describe a
            # stack), matching the newest-genuine path's contract.
            run = next(
                (r for r in proj.iter_stack_runs()
                 if r.id == run_id
                 and _stack_options_from_run_json(r.options_json) is not None),
                None,
            )
        if run is None:
            return None
        frames = list(proj.iter_frames())
        notes = stack_health(run, frames)
        spec = recommended_dark_spec(frames)
    finally:
        proj.close()
        lib.close()
    return StackHealthOut(
        run_id=run.id,
        notes=[HealthNoteOut(kind=n.kind, severity=n.severity,
                             message=n.message, action=n.action)
               for n in notes],
        dark_spec=DarkSpecOut(exposure_s=spec.exposure_s, gain=spec.gain),
    )


@router.get("/{safe}/best-frame", response_model=BestFrameOut)
def target_best_frame(safe: str, request: Request) -> BestFrameOut:
    """The target's sharpest accepted sub, for the pre-stack "First look" card.

    A beginner drops a night's subs and then waits — often minutes — for the
    stack before seeing *anything*. The moment QC finishes we can already surface
    the single best sub (sharpest, then most stars) so they get instant "yes, it
    worked" reassurance and can catch a bad-framing/focus night before waiting on
    a stack. Read-only; reuses the existing QC metrics and per-frame preview
    endpoint. ``frame_id`` is ``null`` when nothing is QC'd yet."""
    from seestack.qc.grading import best_frame

    lib, proj = deps.open_target_project(request, safe)
    try:
        frames = list(proj.iter_frames(accepted_only=True))
    finally:
        proj.close()
        lib.close()
    best = best_frame(frames)
    if best is None:
        return BestFrameOut(n_accepted=len(frames))
    return BestFrameOut(
        frame_id=best.id,
        captured_utc=best.timestamp_utc,
        fwhm_px=best.fwhm_px,
        star_count=best.star_count,
        n_accepted=len(frames),
    )


@router.get("/{safe}/integration-goal", response_model=IntegrationGoalOut)
def get_integration_goal(safe: str, request: Request) -> IntegrationGoalOut:
    """The user's integration goal for this target (total accepted exposure in
    seconds), or ``null`` when none is set — the readiness card then uses its
    sane per-object-type default. Read-only; a plain project-meta lookup."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        return IntegrationGoalOut(goal_s=read_goal_s(proj))
    finally:
        proj.close()
        lib.close()


@router.put("/{safe}/integration-goal", response_model=IntegrationGoalOut)
def set_integration_goal(
    safe: str, body: IntegrationGoalPatch, request: Request
) -> IntegrationGoalOut:
    """Set (``goal_s`` > 0) or clear (``goal_s`` null) this target's integration
    goal. Opt-in and reversible: clearing reverts the readiness card to its
    per-object-type default. Stored in the existing ``project_meta`` kv table,
    so it's an additive, upgrade-safe change (no schema migration)."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        if body.goal_s is None:
            proj.delete_meta(GOAL_META_KEY)
            stored: float | None = None
        else:
            goal = float(body.goal_s)
            if not (goal == goal) or goal <= 0:  # NaN or non-positive
                raise HTTPException(status_code=422, detail="goal_s must be positive")
            goal = min(max(goal, MIN_GOAL_S), MAX_GOAL_S)
            proj.set_meta(GOAL_META_KEY, repr(goal))
            stored = goal
        # The Dashboard roll-up and the Tonight planner both fold this goal into
        # a cached per-target answer, and a goal write leaves the registry
        # signature untouched — so drop those caches here rather than making the
        # user wait out a TTL to see the goal they just set.
        invalidate_registry_cache(request.app)
        return IntegrationGoalOut(goal_s=stored)
    finally:
        proj.close()
        lib.close()


@router.patch("/{safe}", response_model=TargetOut)
def patch_target(safe: str, body: TargetPatch, request: Request) -> TargetOut:
    """Edit user-owned target metadata: free-text notes and tags."""
    lib = deps.open_library(request)
    try:
        entry = lib.update_target(safe, notes=body.notes, tags=body.tags)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        return _to_out(entry)
    finally:
        lib.close()


@router.delete("/{safe}")
def delete_target(safe: str, request: Request, remove_files: bool = False) -> dict:
    lib = deps.open_library(request)
    try:
        found = lib.delete_target(safe, remove_files=remove_files)
        if not found:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        return {"deleted": safe, "files_removed": remove_files}
    finally:
        lib.close()


def _cover_preview_path(lib, entry) -> Path | None:  # noqa: ANN001
    """The pinned cover run's preview path, or ``None`` to fall back to newest.

    Resolves the target's ``cover_stack_run_id`` through its own project so the
    path always tracks the run (e.g. after a re-stack archives it — the run's
    ``preview_path`` is repointed). Returns ``None`` when nothing is pinned, the
    pinned run was pruned, or its preview file is gone, so the caller degrades
    gracefully to the newest stack rather than serving a broken image."""
    if entry is None or entry.cover_stack_run_id is None:
        return None
    try:
        proj = lib.open_target(entry.safe_name)
    except Exception:  # noqa: BLE001 — a missing/broken project just falls back
        return None
    try:
        run = next((r for r in proj.iter_stack_runs()
                    if r.id == entry.cover_stack_run_id), None)
    finally:
        proj.close()
    if run is None or not run.preview_path:
        return None
    path = Path(run.preview_path)
    return path if path.exists() else None


def _readable_file(raw: str | Path | None) -> Path | None:
    """``raw`` as a path that is really there, or ``None``.

    An unreachable mount raises rather than answering, and "I can't tell" has to
    read as "not this one" here — every caller is choosing between candidates.
    """
    if not raw:
        return None
    path = Path(raw)
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def current_picture_path(lib, entry) -> Path | None:  # noqa: ANN001
    """The one picture that **is** this target's, right now — or ``None``.

    Three steps, in the order the app has always meant them: the run the user
    pinned as the cover, then the library's stamped newest-stack preview, then —
    only when that file is gone — the newest run that still has a preview on
    disk.

    That third step is the one that used to be missing from everything except
    ``/api/gallery/best``. The stamped path can outlive its file (deleting a
    target's newest run removes its preview and leaves the stamp behind), and a
    caller that stopped at step two then dropped the target entirely while
    ``best`` quietly stepped back to the previous run and still showed it — so
    the same library read as N pictures on one screen and N−1 on another, with
    nothing to explain the difference.

    Costs one project open per target that needs step three, i.e. essentially
    never on a healthy library — which is what makes it affordable on the
    deliberate one-tap downloads that use it. It is deliberately *not* wired into
    the per-render list endpoints for that reason (see ``TargetOut.has_preview``):
    there, a library where many stamps went stale would pay N opens per page.
    """
    if entry is None:
        return None
    cover = _cover_preview_path(lib, entry)
    if cover is not None:
        return cover
    stamped = _readable_file(getattr(entry, "last_stack_preview", None))
    if stamped is not None:
        return stamped
    try:
        proj = lib.open_target(entry.safe_name)
    except Exception:  # noqa: BLE001 — a missing/broken project is just no picture
        return None
    try:
        for run in proj.iter_stack_runs():  # newest first
            found = _readable_file(getattr(run, "preview_path", None))
            if found is not None:
                return found
    except Exception:  # noqa: BLE001 — an unreadable run list must not 500 a wall
        return None
    finally:
        proj.close()
    return None


@router.get("/{safe}/thumbnail")
def target_thumbnail(safe: str, request: Request) -> FileResponse:
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail="No preview")
        # A pinned cover wins; otherwise the newest stack's preview, and if that
        # file has gone, the newest run that still has one — so deleting a
        # target's newest run leaves a slightly older thumbnail rather than a
        # broken image.
        path = current_picture_path(lib, entry)
        if path is None:
            raise HTTPException(status_code=404, detail="No preview")
        return FileResponse(path, media_type="image/png")
    finally:
        lib.close()


@router.put("/{safe}/cover", response_model=TargetOut)
def set_target_cover(safe: str, body: SetCoverRequest, request: Request) -> TargetOut:
    """Pin a stack run as the target's showcase "cover" (``run_id``), or clear
    it (``run_id`` null → show the newest stack, the default). Validates the run
    exists in this target's project so a bad id can't be pinned."""
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        if body.run_id is not None:
            proj = lib.open_target(entry.safe_name)
            try:
                exists = any(r.id == body.run_id for r in proj.iter_stack_runs())
            finally:
                proj.close()
            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"No stack run {body.run_id} for target '{safe}'",
                )
        updated = lib.set_target_cover(safe, body.run_id)
        if updated is None:  # pragma: no cover — found above, re-checked defensively
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        return _to_out(updated)
    finally:
        lib.close()
