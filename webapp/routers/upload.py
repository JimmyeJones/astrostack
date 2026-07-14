"""Bulk FITS upload through the web interface (no NAS share required).

The only way to get subs in used to be dropping Seestar target folders into
``incoming/`` over an SMB/NFS share — which assumes the user can mount the NAS.
This router lets a beginner drag-and-drop (or multi-select) FITS files straight
in the browser; the files stream to ``incoming/<target>/`` and the existing
watcher/pipeline then ingests → QC → solves them exactly as if they'd been
dropped there.

Guardrails (this is a file-writing endpoint on a live NAS):

* **Stream to disk, never buffer whole files in RAM** — a bulk upload can be
  thousands of subs / many GB. Files are read in chunks and written from a
  threadpool so the event loop / single job worker aren't blocked.
* **Sanitise every name** — only the basename is used, traversal (``..`` / path
  separators / a browser-supplied relative path) is stripped, and every write is
  confined strictly under ``incoming/``. Only FITS suffixes are accepted.
* **Disk-space aware** — the free space is checked before each write and a clear
  "not enough room" reason is returned instead of silently filling the NAS.
* **Resilient** — each file streams to a ``.part`` sidecar and is atomically
  renamed into place only once fully written, so a dropped connection can never
  leave a half-written FITS for the watcher to ingest.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from seestack.io.ingest import FITS_SUFFIXES
from webapp import deps, pipeline

router = APIRouter(tags=["upload"])

# Read/write in 1 MiB chunks so a multi-GB upload never lands in RAM whole.
_CHUNK = 1024 * 1024
# Keep this much disk free as a safety margin so an upload never fills the NAS
# to 0 bytes (which would break the running app's own writes).
_DISK_RESERVE_BYTES = 256 * 1024 * 1024


def safe_component(name: str) -> str | None:
    """Reduce a client-supplied name to a single safe path component.

    Browsers send just a filename for a multi-select, but a *folder* upload
    (``webkitdirectory``) sends a relative path like ``M31/Light_001.fit`` and a
    Windows client may use backslashes — so we normalise both, take only the
    final component, and reject anything that could escape the target dir
    (``..``, an empty/dot name, a leftover separator or NUL). Returns the safe
    basename, or ``None`` when the name is unusable.
    """
    if not name:
        return None
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not base or base in (".", "..") or set(base) <= {"."}:
        return None
    if "/" in base or "\0" in base:
        return None
    return base


def is_fits_name(base: str) -> bool:
    """True when ``base`` is a FITS file the scanner would actually ingest."""
    return Path(base).suffix.lower() in FITS_SUFFIXES


def safe_target_dir(incoming: Path, target: str) -> Path | None:
    """Resolve the destination dir for an optional user-supplied target name.

    An empty/blank target puts files loose in ``incoming/`` (the scanner's
    ``Unsorted`` catch-all). A named target becomes ``incoming/<name>/`` — the
    name is sanitised to a single component and the result is confirmed to stay
    strictly under ``incoming`` (defence in depth against traversal). Returns
    ``None`` when the name is unsafe.
    """
    target = (target or "").strip()
    if not target:
        return incoming
    comp = safe_component(target)
    if comp is None:
        return None
    dest = (incoming / comp).resolve()
    root = incoming.resolve()
    if dest != root and root not in dest.parents:
        return None
    return dest


class UploadedFile(BaseModel):
    name: str
    bytes: int


class RejectedFile(BaseModel):
    name: str
    reason: str


class UploadResponse(BaseModel):
    target: str            # the folder the files landed in ("" = Unsorted)
    saved: list[UploadedFile]
    skipped: list[UploadedFile]     # already present — deduped, not re-written
    rejected: list[RejectedFile]    # not a FITS, unsafe name, or no disk room
    bytes_written: int
    job_id: str | None     # the scan enqueued to ingest the upload, if any


async def _stream_to_disk(upload: UploadFile, dest: Path) -> int:
    """Stream an upload to ``dest`` via a ``.part`` sidecar, atomically renamed.

    Blocking file I/O runs in a threadpool so the event loop stays responsive.
    On any failure the partial ``.part`` is removed so a dropped connection never
    leaves a truncated FITS in ``incoming/`` for the watcher to ingest.

    The sidecar gets a **unique** name (``tempfile.mkstemp``) rather than a fixed
    ``<name>.part``: two concurrent POSTs of the *same* filename (a double-submit,
    a retried request) would otherwise stream into one shared ``.part`` at once —
    interleaving their bytes into a corrupt file that both then rename into place.
    A per-request temp file makes each write independent; the final ``os.replace``
    is atomic, so the loser is simply overwritten by a *complete* file (and the
    duplicate is dropped by the pipeline's content dedup) — never a scrambled sub.
    The ``.part`` suffix keeps the sidecar out of the scanner's FITS glob, so even
    an orphan from a hard crash is never ingested.
    """
    fd, tmp_name = await run_in_threadpool(
        tempfile.mkstemp, suffix=".part", prefix=dest.name + ".",
        dir=str(dest.parent))
    tmp = Path(tmp_name)
    written = 0
    fh = os.fdopen(fd, "wb")
    try:
        while True:
            chunk = await upload.read(_CHUNK)
            if not chunk:
                break
            await run_in_threadpool(fh.write, chunk)
            written += len(chunk)
    except BaseException:
        await run_in_threadpool(fh.close)
        await run_in_threadpool(tmp.unlink, True)  # missing_ok
        raise
    await run_in_threadpool(fh.close)
    await run_in_threadpool(os.replace, tmp, dest)
    return written


@router.post("/api/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    target: Annotated[str, Form()] = "",
) -> UploadResponse:
    """Accept FITS uploads, land them in ``incoming/<target>/``, kick a scan.

    Non-FITS / unsafe-named files are rejected with a plain-language reason
    (the rest still upload); a file already present is skipped (the scan's own
    content dedup would drop it anyway). A scan is enqueued only when at least
    one new file was saved, so the existing ingest → QC → solve pipeline runs
    exactly as it does for a NAS drop.
    """
    settings = deps.get_settings(request)
    incoming = settings.resolved_incoming_dir

    dest_dir = safe_target_dir(incoming, target)
    if dest_dir is None:
        raise HTTPException(status_code=400, detail="Invalid target folder name")

    try:
        await run_in_threadpool(dest_dir.mkdir, parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"Could not create upload folder: {e}") from e

    saved: list[UploadedFile] = []
    skipped: list[UploadedFile] = []
    rejected: list[RejectedFile] = []
    bytes_written = 0

    for upload in files:
        base = safe_component(upload.filename or "")
        if base is None:
            rejected.append(RejectedFile(name=upload.filename or "(unnamed)",
                                         reason="unsafe file name"))
            continue
        if not is_fits_name(base):
            rejected.append(RejectedFile(
                name=base,
                reason="not a FITS file (accepts .fit, .fits, .fts)"))
            continue

        dest = dest_dir / base
        if dest.exists():
            skipped.append(UploadedFile(name=base, bytes=dest.stat().st_size))
            continue

        # Disk-space guard: refuse a write that would drop free space below the
        # reserve, rather than silently filling the NAS. size is best-effort
        # (Starlette populates it for the spooled upload); when unknown we let
        # the write proceed and rely on the ENOSPC handling below.
        size = getattr(upload, "size", None)
        try:
            free = shutil.disk_usage(dest_dir).free
        except OSError:
            free = None
        if size is not None and free is not None and free - size < _DISK_RESERVE_BYTES:
            rejected.append(RejectedFile(name=base, reason="not enough disk space"))
            continue

        try:
            n = await _stream_to_disk(upload, dest)
        except OSError as e:
            reason = ("not enough disk space" if getattr(e, "errno", None) == 28
                      else f"could not be saved ({e})")
            rejected.append(RejectedFile(name=base, reason=reason))
            continue
        finally:
            await upload.close()

        saved.append(UploadedFile(name=base, bytes=n))
        bytes_written += n

    job_id: str | None = None
    if saved:
        jm = deps.get_job_manager(request)
        job = pipeline.submit_pipeline(settings, jm)
        job_id = job.id

    return UploadResponse(
        target=dest_dir.name if dest_dir != incoming else "",
        saved=saved, skipped=skipped, rejected=rejected,
        bytes_written=bytes_written, job_id=job_id,
    )
