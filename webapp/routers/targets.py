"""Targets (library view) endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from webapp import deps
from webapp.schemas import (
    BestFrameOut,
    CleanupSuggestionOut,
    DarkSpecOut,
    DifficultyHintOut,
    FocusTrendOut,
    FocusTrendPointOut,
    FramingHintOut,
    HealthNoteOut,
    IntegrationGoalOut,
    IntegrationGoalPatch,
    MergeRequest,
    MergeSuggestionOut,
    MergeSuggestionTarget,
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

router = APIRouter(prefix="/api/targets", tags=["targets"])

# Project-meta key holding the user's integration goal (total accepted exposure,
# seconds) for a target. Stored in the existing key/value ``project_meta`` table
# so it needs no schema migration — an old project simply has the key absent.
_GOAL_META_KEY = "integration_goal_s"

# Sanity bound so a fat-fingered value can't poison the readiness card: 1 minute
# to 1000 hours. A goal is a gentle suggestion, never a gate, so the bound only
# guards against nonsense, not against an ambitious deep-integration target.
_MIN_GOAL_S = 60.0
_MAX_GOAL_S = 1000.0 * 3600.0


def _read_goal_s(proj) -> float | None:  # noqa: ANN001
    """Parse the stored integration goal, tolerating a stale/garbage value
    (treated as unset) so a hand-edited project can never 500 the card."""
    raw = proj.get_meta(_GOAL_META_KEY)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not (val > 0) or val != val:  # non-positive or NaN → unset
        return None
    return val


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
            # subs — so nothing real is lost, and the message is truthful.
            if dup_sources and all(s in base_sources for s in dup_sources):
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
        blurb=info.blurb,
        difficulty=(DifficultyHintOut(level=info.difficulty.level,
                                      label=info.difficulty.label,
                                      text=info.difficulty.text)
                    if info.difficulty is not None else None),
    )


@router.get("/{safe}/session-recap", response_model=SessionRecapOut | None)
def target_session_recap(safe: str, request: Request) -> SessionRecapOut | None:
    """A friendly, plain-language recap of the target's most recent capture
    session — how many subs it added, how many were kept vs. set aside (and why,
    in plain buckets), and the target's total integration now. Returns ``null``
    when there's nothing datable to report (no frame carries a capture time).
    Read-only aggregation over the frames table; renders the "Last session" card.
    """
    from seestack.session_recap import session_recap

    lib, proj = deps.open_target_project(request, safe)
    try:
        recap = session_recap(proj)
    finally:
        proj.close()
        lib.close()
    if recap is None:
        return None
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


@router.get("/{safe}/nights", response_model=list[NightSummaryOut])
def target_nights(safe: str, request: Request) -> list[NightSummaryOut]:
    """Every capture night that went into this target, newest first — the
    "Nights" card. The §1 owner shoots one target across many nights (the Seestar
    writes a new folder per night), and today there's no per-target view of *all*
    the nights behind a picture. This lists each night's subs kept vs set aside,
    integration, median FWHM, and a one-word verdict (sharp / soft / hazy) from
    metrics already stored, so a clouded-out or soft night is easy to spot. Purely
    informational and read-only — it never rejects anything. ``[]`` when there's
    nothing datable (no frame carries a capture time)."""
    from seestack.session_recap import nights_breakdown

    lib, proj = deps.open_target_project(request, safe)
    try:
        nights = nights_breakdown(proj)
    finally:
        proj.close()
        lib.close()
    return [
        NightSummaryOut(
            start_utc=n.start_utc,
            end_utc=n.end_utc,
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
        return IntegrationGoalOut(goal_s=_read_goal_s(proj))
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
            proj.delete_meta(_GOAL_META_KEY)
            stored: float | None = None
        else:
            goal = float(body.goal_s)
            if not (goal == goal) or goal <= 0:  # NaN or non-positive
                raise HTTPException(status_code=422, detail="goal_s must be positive")
            goal = min(max(goal, _MIN_GOAL_S), _MAX_GOAL_S)
            proj.set_meta(_GOAL_META_KEY, repr(goal))
            stored = goal
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


@router.get("/{safe}/thumbnail")
def target_thumbnail(safe: str, request: Request) -> FileResponse:
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail="No preview")
        # A pinned cover wins; otherwise show the newest stack's preview.
        path = _cover_preview_path(lib, entry)
        if path is None:
            if not entry.last_stack_preview:
                raise HTTPException(status_code=404, detail="No preview")
            path = Path(entry.last_stack_preview)
        if not path.exists():
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
