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
* **Sanitise every name** — every path segment is sanitised, traversal (``..`` /
  NUL / a leftover separator) rejects the name outright, and every write is
  re-confirmed strictly under ``incoming/``. Only FITS suffixes are accepted.
  A folder drop can opt into keeping its **directories** (``preserve_folders``)
  so the scanner's Seestar folder convention sees ``M 31_sub/`` and makes the
  right target, instead of every object landing in one ``Unsorted`` pile.
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


def safe_relname(name: str) -> str | None:
    """Reduce a client-supplied (possibly folder-relative) name to a single safe
    filename that **preserves** its relative subpath by flattening the separators.

    A folder upload sends a relative path like ``night1/Light_001.fit``. Reducing
    it to the bare basename (:func:`safe_component`) is unsafe *for the destination
    name*: capture tools — Seestar included — restart frame numbering per session,
    so two genuinely different subs in different session subfolders often share a
    basename (``Light_0001.fit``). Collapsing them onto one destination silently
    drops all but the first (they'd land on the same path, and the second reads as
    "already present"). Flattening the *whole* relative path into the filename
    (``night1__Light_001.fit``) keeps distinct source files distinct while staying
    a single traversal-safe component (still landing flat in ``incoming/<target>/``,
    so the scanner's one-subfolder-per-target rule is unchanged). Every segment is
    sanitised and any ``..``/NUL rejects the whole name. Returns the safe flattened
    name, or ``None`` when unusable.
    """
    if not name or "\0" in name:
        return None
    segments: list[str] = []
    for seg in name.replace("\\", "/").split("/"):
        seg = seg.strip()
        if seg == "" or seg == ".":
            continue  # empty / current-dir segment — safely dropped
        if set(seg) <= {"."}:  # ``..`` (or any all-dots) — a traversal segment
            return None
        segments.append(seg)
    if not segments:
        return None
    flat = "__".join(segments)
    if "/" in flat or "\\" in flat or "\0" in flat:  # defence in depth
        return None
    return flat


# How many path components of a browser-supplied relative path are kept when
# folder structure is preserved. Real Seestar trees are 2–3 deep
# (``MyWorks/M 31_sub/Light_0001.fit``); anything deeper is a user who dragged in
# a whole archive, and an unbounded tree under ``incoming/`` is worth capping.
# The *last* components are the meaningful ones (the target folder sits right
# above the file), so a deeper path keeps its tail.
_MAX_REL_DEPTH = 6


def safe_relpath(name: str) -> str | None:
    """Reduce a client-supplied relative path to a safe **relative path**, keeping
    its directories.

    This is the folder-preserving counterpart to :func:`safe_relname`. A folder
    drop / ``webkitdirectory`` pick sends ``M 31_sub/Light_0001.fit``; flattening
    that to one filename lands every target's subs in a single ``incoming/`` pile,
    so the scanner's Seestar-aware folder convention (``<T>_sub`` → target
    ``<T>``, ``<T>_mosaic_sub`` → ``<T> (mosaic)``, ``*_video`` skipped, a
    whole-device container expanded) never fires and the user gets one giant
    ``Unsorted`` target instead of their real ones. Keeping the directories makes
    an upload land exactly like a NAS drop.

    Every segment is sanitised the same way :func:`safe_component` sanitises one:
    empty / ``.`` segments are dropped and any all-dots (``..``) segment or NUL
    rejects the whole path, so the result can never escape the destination. The
    path is capped at :data:`_MAX_REL_DEPTH` components (keeping the tail, which
    carries the target folder). Returns a ``/``-joined relative path, or ``None``
    when the name is unusable.
    """
    if not name or "\0" in name:
        return None
    segments: list[str] = []
    for seg in name.replace("\\", "/").split("/"):
        seg = seg.strip()
        if seg == "" or seg == ".":
            continue  # empty / current-dir segment — safely dropped
        if set(seg) <= {"."}:  # ``..`` (or any all-dots) — a traversal segment
            return None
        segments.append(seg)
    if not segments:
        return None
    if len(segments) > _MAX_REL_DEPTH:
        segments = segments[-_MAX_REL_DEPTH:]
    return "/".join(segments)


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


def confined_dest(dest_dir: Path, rel: str) -> Path | None:
    """Resolve ``dest_dir / rel``, confirming it stays strictly under ``dest_dir``.

    :func:`safe_relpath` already rejects traversal segments, so this is defence in
    depth — it also catches the case where an existing *symlink* inside
    ``incoming/`` would redirect a write outside the watched tree. Returns
    ``None`` when the resolved path escapes.
    """
    dest = (dest_dir / rel).resolve()
    root = dest_dir.resolve()
    if root not in dest.parents:
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
    # Top-level folders this upload wrote into under the destination,
    # when folder structure was preserved (empty on the flat path). Additive —
    # older frontends simply ignore it — and it lets the UI say *which* targets
    # the drop is about to become instead of a bare file count.
    folders: list[str] = []


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
        try:
            while True:
                chunk = await upload.read(_CHUNK)
                if not chunk:
                    break
                await run_in_threadpool(fh.write, chunk)
                written += len(chunk)
        finally:
            # Close (flushing buffered writes) exactly once, on every path. A
            # buffered-write ENOSPC can surface here at the *final flush*, not
            # only mid-write — so the close must sit inside the guard that
            # unlinks the temp, or that last-flush failure would orphan a .part.
            await run_in_threadpool(fh.close)
    except BaseException:
        await run_in_threadpool(tmp.unlink, True)  # missing_ok
        raise
    try:
        await run_in_threadpool(os.replace, tmp, dest)
    except BaseException:
        # The rename itself can fail (a cross-device dest, a permission or NAS
        # blip) *after* a complete temp is on disk. Clean up the fully-written
        # sidecar so a failed upload leaves no orphaned ``.part`` behind, rather
        # than only unlinking on a mid-write failure above.
        await run_in_threadpool(tmp.unlink, True)  # missing_ok
        raise
    return written


@router.post("/api/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    target: Annotated[str, Form()] = "",
    preserve_folders: Annotated[bool, Form()] = False,
) -> UploadResponse:
    """Accept FITS uploads, land them in ``incoming/<target>/``, kick a scan.

    Non-FITS / unsafe-named files are rejected with a plain-language reason
    (the rest still upload); a file already present is skipped (the scan's own
    content dedup would drop it anyway). A scan is enqueued only when at least
    one new file was saved, so the existing ingest → QC → solve pipeline runs
    exactly as it does for a NAS drop.

    ``preserve_folders`` (opt-in, default off so an older frontend and every
    existing caller behave exactly as before) keeps the browser-relative
    **directories** of a folder drop / ``webkitdirectory`` pick instead of
    flattening them into one filename. That is what makes a dragged Seestar
    folder land like a NAS drop: the scanner's folder convention then sees
    ``M 31_sub/`` and creates the target *M 31* — rather than tipping every
    object's subs into one ``Unsorted`` pile. Paths are sanitised per segment and
    every write is re-confirmed under the destination (:func:`safe_relpath`,
    :func:`confined_dest`).
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
    # Resolve once: ``safe_target_dir`` returns ``incoming`` verbatim for the
    # blank-target case, so comparing a *resolved* destination against it would
    # otherwise mis-read every flat write as a subfolder on an install whose
    # incoming path is relative or crosses a symlink.
    dest_root = dest_dir.resolve()

    saved: list[UploadedFile] = []
    skipped: list[UploadedFile] = []
    rejected: list[RejectedFile] = []
    bytes_written = 0
    folders: list[str] = []

    for upload in files:
        # Close each upload's spooled temp on *every* path — reject, skip,
        # disk-space, or success — not only the streamed one, so a large
        # multi-file POST doesn't hold spooled parts open until GC. (Starlette
        # closes form uploads only on a parse error, not on success.)
        try:
            # Preserve the browser-relative subpath: as real directories when the
            # caller asked for it (so the scanner's Seestar folder convention
            # fires), otherwise flattened into one filename so two different subs
            # sharing a basename across session subfolders don't collide onto one
            # destination and silently drop one (Seestar restarts per-session
            # frame numbering). Either way the result is traversal-safe.
            base = (safe_relpath(upload.filename or "") if preserve_folders
                    else safe_relname(upload.filename or ""))
            if base is None:
                rejected.append(RejectedFile(name=upload.filename or "(unnamed)",
                                             reason="unsafe file name"))
                continue
            if not is_fits_name(base):
                rejected.append(RejectedFile(
                    name=base,
                    reason="not a FITS file (accepts .fit, .fits, .fts)"))
                continue

            dest = confined_dest(dest_root, base)
            if dest is None:
                rejected.append(RejectedFile(name=base, reason="unsafe file name"))
                continue
            if dest.parent != dest_root:
                # A preserved subfolder — create it (once per new folder) so the
                # stream below has somewhere to land, and remember its top level
                # for the response's plain-language "which targets is this?" line.
                try:
                    await run_in_threadpool(
                        dest.parent.mkdir, parents=True, exist_ok=True)
                except OSError as e:
                    rejected.append(RejectedFile(
                        name=base, reason=f"could not be saved ({e})"))
                    continue
                top = base.split("/", 1)[0]
                if top not in folders:
                    folders.append(top)
            if dest.exists():
                skipped.append(UploadedFile(name=base, bytes=dest.stat().st_size))
                continue

            # Disk-space guard: refuse a write that would drop free space below
            # the reserve, rather than silently filling the NAS. size is
            # best-effort (Starlette populates it for the spooled upload); when
            # unknown we let the write proceed and rely on the ENOSPC handling
            # below.
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

            saved.append(UploadedFile(name=base, bytes=n))
            bytes_written += n
        finally:
            await upload.close()

    job_id: str | None = None
    if saved:
        jm = deps.get_job_manager(request)
        job = pipeline.submit_pipeline(settings, jm)
        job_id = job.id

    return UploadResponse(
        target=dest_dir.name if dest_dir != incoming else "",
        saved=saved, skipped=skipped, rejected=rejected,
        bytes_written=bytes_written, job_id=job_id,
        folders=folders,
    )
