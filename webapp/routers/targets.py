"""Targets (library view) endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from webapp import deps
from webapp.schemas import (
    MergeRequest,
    ObjectInfoOut,
    SessionQualityDriftOut,
    SessionRecapOut,
    TargetCreate,
    TargetOut,
    TargetPatch,
)

router = APIRouter(prefix="/api/targets", tags=["targets"])


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
