"""Targets (library view) endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from webapp import deps
from webapp.schemas import (
    HealthNoteOut,
    IntegrationGoalOut,
    IntegrationGoalPatch,
    MergeRequest,
    ObjectInfoOut,
    SessionQualityDriftOut,
    SessionRecapOut,
    StackHealthOut,
    TargetCreate,
    TargetOut,
    TargetPatch,
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
    from seestack.stackhealth import stack_health

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
        notes = stack_health(run, proj.iter_frames())
    finally:
        proj.close()
        lib.close()
    return StackHealthOut(
        run_id=run.id,
        notes=[HealthNoteOut(kind=n.kind, severity=n.severity,
                             message=n.message, action=n.action)
               for n in notes],
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


@router.get("/{safe}/thumbnail")
def target_thumbnail(safe: str, request: Request) -> FileResponse:
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None or not entry.last_stack_preview:
            raise HTTPException(status_code=404, detail="No preview")
        path = Path(entry.last_stack_preview)
        if not path.exists():
            raise HTTPException(status_code=404, detail="No preview")
        return FileResponse(path, media_type="image/png")
    finally:
        lib.close()
