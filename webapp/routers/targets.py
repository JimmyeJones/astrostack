"""Targets (library view) endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from webapp import deps
from webapp.schemas import MergeRequest, TargetCreate, TargetOut

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
        added = lib.merge_targets(body.into, body.sources)
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


@router.delete("/{safe}")
def delete_target(safe: str, request: Request, remove_files: bool = False) -> dict:
    lib = deps.open_library(request)
    try:
        lib.delete_target(safe, remove_files=remove_files)
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
