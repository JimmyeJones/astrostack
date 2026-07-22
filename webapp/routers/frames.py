"""Per-target frame endpoints: list/sort, accept-reject, bulk, preview image."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from statistics import median
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from seestack.io.project import FrameRow
from seestack.render.thumbnail import THUMB_VERSION, generate_thumbnail, thumbs_dir
from seestack.solve.astap import (
    SOLVE_SETUP_ASTAP_MISSING,
    SOLVE_SETUP_NO_DATABASE,
    classify_solve_setup_error,
)
from webapp import deps
from webapp.rejection_summary import summarize_rejections
from webapp.schemas import (
    BulkFrameAction,
    FrameOut,
    FramePatch,
    GradeReasonOut,
    GradeRecommendationOut,
    GradeReportOut,
)

router = APIRouter(prefix="/api/targets/{safe}/frames", tags=["frames"])

_BAYER_PATTERNS = {"RGGB", "BGGR", "GRBG", "GBRG"}

# The app is built to survive a NAS mount going read-only or a locked
# ``project.sqlite`` (see ``system._folder_status`` and the connection-leak fixes
# throughout this file). When a frame write actually fails in that state, SQLite
# raises ``OperationalError`` ("attempt to write a readonly database" / "database
# is locked"), which otherwise surfaces as an opaque 500. Map it to a 503 with
# plain-language guidance so a beginner whose ZFS dataset unmounted mid-session
# is told *what* to do, not just "something broke".
STORAGE_READONLY_MSG = (
    "This target's storage is read-only or locked — check that the library "
    "folder / NAS mount is mounted and writable, then try again."
)

_SORTABLE = {
    "id", "timestamp_utc", "exposure_s", "fwhm_px", "star_count",
    "sky_adu_median", "eccentricity_median", "transparency_score",
}


# A frame counts as "trailed" when its median star eccentricity is *both* a
# strong within-target outlier (> median + 3·MAD) *and* above an absolute floor
# of noticeably elongated stars — so a target whose whole set is tight and round
# never has a frame flagged just for being marginally above the pack, and a
# genuinely bad-tracking night's worst subs surface. Mirrors the client-side
# badge count on the Target view; keep the two in sync.
_TRAILED_MAD_K = 3.0
_TRAILED_ECC_FLOOR = 0.6
_TRAILED_MIN_FRAMES = 5


def trailed_frame_ids(frames: list[FrameRow]) -> list[int]:
    """Ids of accepted frames whose eccentricity is a strong trailing outlier.

    ``frames`` is any iterable of frame rows; only those carrying a measured
    ``eccentricity_median`` inform the statistics and are eligible. Returns an
    empty list when too few frames carry the metric to judge robustly.
    """
    measured = [f for f in frames if f.eccentricity_median is not None]
    if len(measured) < _TRAILED_MIN_FRAMES:
        return []
    values = [f.eccentricity_median for f in measured]
    med = median(values)
    mad = median([abs(v - med) for v in values])
    threshold = max(med + _TRAILED_MAD_K * mad, _TRAILED_ECC_FLOOR)
    return [f.id for f in measured if f.eccentricity_median > threshold]


def _to_out(f: FrameRow) -> FrameOut:
    return FrameOut(
        id=f.id,
        name=Path(f.source_path).name,
        timestamp_utc=f.timestamp_utc,
        exposure_s=f.exposure_s,
        gain=f.gain,
        width_px=f.width_px,
        height_px=f.height_px,
        bayer_pattern=f.bayer_pattern,
        solved=f.wcs_json is not None,
        ra_center_deg=f.ra_center_deg,
        dec_center_deg=f.dec_center_deg,
        ra_hint_deg=f.ra_hint_deg,
        dec_hint_deg=f.dec_hint_deg,
        fwhm_px=f.fwhm_px,
        star_count=f.star_count,
        sky_adu_median=f.sky_adu_median,
        eccentricity_median=f.eccentricity_median,
        transparency_score=f.transparency_score,
        streak_detected=f.streak_detected,
        accept=f.accept,
        reject_reason=f.reject_reason,
        user_override=f.user_override,
    )


@router.get("", response_model=list[FrameOut])
def list_frames(
    safe: str,
    request: Request,
    accepted_only: bool = False,
    sort: str = "id",
    order: str = "asc",
    offset: int = 0,
    limit: int = 500,
) -> list[FrameOut]:
    if sort not in _SORTABLE:
        sort = "id"
    # Clamp the pagination window like every other int query param in the routers
    # (jobs `limit`, stats `recent_limit`, frame_preview `size`): a negative
    # `offset`/`limit` would trigger Python negative-index slicing and silently
    # return the wrong window (e.g. offset=-1 → the last frame only; limit=-1 →
    # every frame but the last) instead of the requested page.
    offset = max(0, offset)
    limit = max(0, limit)
    lib, proj = deps.open_target_project(request, safe)
    try:
        frames = list(proj.iter_frames(accepted_only=accepted_only))
    finally:
        proj.close()
        lib.close()

    # Keep unmeasured (None) frames *last* regardless of direction. The old
    # `(v is None, v)` + `reverse=` idiom is nulls-last only ascending: a
    # descending sort ("blurriest / worst first") inverted it and pinned a block
    # of unmeasured/unsolved subs to the top, hiding the actually-worst measured
    # frames a beginner asked to see. Sort the measured rows and append the
    # unmeasured ones (in their stable order) so both directions rank real
    # values first.
    reverse = order == "desc"
    measured = [f for f in frames if getattr(f, sort) is not None]
    unmeasured = [f for f in frames if getattr(f, sort) is None]
    measured.sort(key=lambda f: getattr(f, sort), reverse=reverse)
    frames = measured + unmeasured
    return [_to_out(f) for f in frames[offset : offset + limit]]


def _solve_setup_problem(counts: dict[str, int]) -> dict | None:
    """Classify the reject tally into a plate-solve *setup* problem, or ``None``.

    ASTAP or its star database being unavailable fails every frame identically,
    so the whole target piles up as ``solve_failed:…`` with no hint that the fix
    is a one-time setup step. Since v0.84.1 those failures are stored with a
    stable canonical reason (see :func:`classify_solve_setup_error`), so this
    server-side tally is reliable for the star-database case too — not just the
    deterministic "astap not found" message the frontend could already spot.
    ASTAP-missing wins over no-database (the solver never ran, so a database
    message can't also be present)."""
    astap = db = 0
    for reason, n in counts.items():
        if not reason.startswith("solve_failed:"):
            continue
        kind = classify_solve_setup_error(reason)
        if kind == SOLVE_SETUP_ASTAP_MISSING:
            astap += n
        elif kind == SOLVE_SETUP_NO_DATABASE:
            db += n
    if astap:
        return {"kind": "astap", "frames": astap}
    if db:
        return {"kind": "database", "frames": db}
    return None


@router.get("/reject-summary")
def reject_summary(safe: str, request: Request) -> dict:
    """Tally rejected frames by reason (``qc:fwhm``, ``bulk:streaked``,
    ``user``, …) so the Target view can explain *why* frames were dropped.
    Declared before ``/{frame_id}`` so the literal path isn't captured as an id."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        counts = proj.reject_reason_counts()
        n_accepted = proj.count(accepted_only=True)
        n_unsolved = proj.count_accepted_unsolved()
    finally:
        proj.close()
        lib.close()
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "solve_setup_problem": _solve_setup_problem(counts),
        # Plain-language grouped breakdown + reassuring verdict for the
        # "why were some frames left out?" beginner card. Additive: the raw
        # ``counts``/``total`` above stay for existing consumers.
        # ``n_unsolved`` folds accepted-but-not-plate-solved subs (silently
        # excluded from the stack) into the breakdown so a thin stack is
        # explained, not counted as "used".
        "summary": summarize_rejections(counts, n_accepted, n_unsolved),
    }


def _grade_report_out(report, changed_ids: list[int] | None = None) -> GradeReportOut:
    return GradeReportOut(
        sensitivity=report.sensitivity,
        n_accepted=report.n_accepted,
        n_considered=report.n_considered,
        recommendations=[
            GradeRecommendationOut(
                frame_id=rec.frame_id,
                name=rec.name,
                reasons=[
                    GradeReasonOut(metric=r.metric, label=r.label, value=r.value,
                                   typical=r.typical, z=r.z)
                    for r in rec.reasons
                ],
            )
            for rec in report.recommendations
        ],
        metrics_used=report.metrics_used,
        metrics_skipped=report.metrics_skipped,
        capped=report.capped,
        changed_ids=changed_ids,
    )


@router.get("/auto-grade", response_model=GradeReportOut)
def auto_grade_preview(
    safe: str,
    request: Request,
    sensitivity: Literal["conservative", "balanced", "aggressive"] | None = None,
) -> GradeReportOut:
    """Preview which accepted frames auto-grade would reject, and why.

    Pure read — nothing is changed. Defaults to the configured sensitivity.
    Declared before ``/{frame_id}`` so the literal path isn't captured as an id.
    """
    from seestack.qc.grading import grade_frames

    sens = sensitivity or deps.get_settings(request).auto_grade_sensitivity
    lib, proj = deps.open_target_project(request, safe)
    try:
        frames = list(proj.iter_frames(accepted_only=True))
    finally:
        proj.close()
        lib.close()
    return _grade_report_out(grade_frames(frames, sensitivity=sens))


@router.post("/auto-grade/apply", response_model=GradeReportOut)
def auto_grade_apply(
    safe: str,
    request: Request,
    sensitivity: Literal["conservative", "balanced", "aggressive"] | None = None,
) -> GradeReportOut:
    """Recompute the grading server-side and reject the recommended frames.

    Recomputing (rather than trusting ids from the client's preview) means the
    decision always reflects the frames' current state. Returns the applied
    report with ``changed_ids`` so the client can offer a one-click undo.
    """
    from seestack.qc.grading import apply_grade_report, grade_frames

    sens = sensitivity or deps.get_settings(request).auto_grade_sensitivity
    lib, proj = deps.open_target_project(request, safe)
    try:
        try:
            frames = list(proj.iter_frames(accepted_only=True))
            report = grade_frames(frames, sensitivity=sens)
            changed = apply_grade_report(proj, report)
        finally:
            proj.close()
        if changed:
            lib.refresh_target_stats(safe)  # accepted-count badge stays honest
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=503, detail=STORAGE_READONLY_MSG) from exc
    finally:
        lib.close()
    return _grade_report_out(report, changed_ids=changed)


@router.get("/{frame_id}", response_model=FrameOut)
def get_frame(safe: str, frame_id: int, request: Request) -> FrameOut:
    lib, proj = deps.open_target_project(request, safe)
    try:
        f = proj.get_frame(frame_id)
        if f is None:
            raise HTTPException(status_code=404, detail="No such frame")
        return _to_out(f)
    finally:
        proj.close()
        lib.close()


@router.patch("/{frame_id}", response_model=FrameOut)
def patch_frame(safe: str, frame_id: int, body: FramePatch, request: Request) -> FrameOut:
    lib, proj = deps.open_target_project(request, safe)
    # Nest proj-close inside lib-close (as apply_grade above does) so the library
    # handle is released on *every* exit — including the 404/no-such-frame and
    # 422/bad-bayer-pattern raises below. Splitting the two into sibling
    # try/finally blocks leaked the Library connection whenever the first block
    # raised, because the second (lib.close) block was then skipped.
    try:
        try:
            f = proj.get_frame(frame_id)
            if f is None:
                raise HTTPException(status_code=404, detail="No such frame")
            patch: dict = {}
            if body.accept is not None:
                patch["accept"] = body.accept
                patch["user_override"] = True
                patch["reject_reason"] = None if body.accept else (body.reject_reason or "user")
            if body.bayer_pattern is not None:
                # Validate before it lands in the DB — the stored pattern later gets
                # embedded in the preview cache filename (frame_preview), so junk
                # here would poison that path and break debayering.
                bp = body.bayer_pattern.upper()
                if bp not in _BAYER_PATTERNS:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Unknown bayer pattern: {body.bayer_pattern!r}",
                    )
                patch["bayer_pattern"] = bp
            if patch:
                proj.update_frame(frame_id, **patch)
            out = _to_out(proj.get_frame(frame_id))
        finally:
            proj.close()
        if body.accept is not None:
            # Keep the registry's accepted-count (Target badge, Library cards)
            # honest after a manual grade — it's only recomputed on refresh.
            lib.refresh_target_stats(safe)
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=503, detail=STORAGE_READONLY_MSG) from exc
    finally:
        lib.close()
    return out


@router.post("/bulk")
def bulk_frames(safe: str, body: BulkFrameAction, request: Request) -> dict:
    lib, proj = deps.open_target_project(request, safe)
    # Nest proj-close inside lib-close (as patch_frame / auto_grade_apply do) so the
    # library handle is released on *every* exit — including when a mid-loop
    # update_frame raises (a read-only/locked project DB, the NAS-went-read-only
    # state the app is built to survive). Splitting the two into sibling try/finally
    # blocks leaked the Library connection whenever the first block raised, because
    # the second (lib.close) block was then skipped.
    try:
        try:
            # Track exactly which frames this action touched so the client can offer
            # a one-click undo of an over-aggressive bulk reject.
            changed_ids: list[int] = []
            if body.action in ("accept", "reject") and body.ids:
                accept = body.action == "accept"
                for fid in body.ids:
                    proj.update_frame(
                        fid, accept=accept, user_override=True,
                        reject_reason=None if accept else "user",
                    )
                    changed_ids.append(fid)
            elif body.action == "reject_worst":
                frames = [f for f in proj.iter_frames(accepted_only=True)
                          if getattr(f, body.metric) is not None]
                # Higher FWHM/ecc/sky is worse; higher star_count / transparency is
                # better (so their "worst" are the *lowest* values).
                higher_is_better = {"star_count", "transparency_score"}
                reverse = body.metric not in higher_is_better
                frames.sort(key=lambda f: getattr(f, body.metric), reverse=reverse)
                n = int(len(frames) * max(0.0, min(1.0, body.fraction)))
                for f in frames[:n]:
                    proj.update_frame(
                        f.id, accept=False, user_override=True,
                        reject_reason=f"bulk:{body.metric}",
                    )
                    changed_ids.append(f.id)
            elif body.action == "reject_streaked":
                # Drop every accepted frame still flagged with a satellite/plane
                # trail. Pairs with the "N streaked" badge for users who'd rather
                # discard the streaked subs than rely on per-pixel rejection.
                for f in proj.iter_frames(accepted_only=True):
                    if f.streak_detected:
                        proj.update_frame(
                            f.id, accept=False, user_override=True,
                            reject_reason="bulk:streaked",
                        )
                        changed_ids.append(f.id)
            elif body.action == "reject_trailed":
                # Drop every accepted frame whose stars are a strong eccentricity
                # outlier for this target (a bad-tracking / wind / bumped-mount sub).
                # Pairs with the "N trailed" badge on the Target view.
                trailed = set(trailed_frame_ids(list(proj.iter_frames(accepted_only=True))))
                for fid in trailed:
                    proj.update_frame(
                        fid, accept=False, user_override=True,
                        reject_reason="bulk:trailed",
                    )
                    changed_ids.append(fid)
        finally:
            proj.close()
        if changed_ids:
            # Same registry refresh as the accept/reject PATCH — bulk actions
            # change the accepted count too.
            lib.refresh_target_stats(safe)
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=503, detail=STORAGE_READONLY_MSG) from exc
    finally:
        lib.close()
    return {"changed": len(changed_ids), "changed_ids": changed_ids}


@router.get("/{frame_id}/preview")
async def frame_preview(
    safe: str,
    frame_id: int,
    request: Request,
    size: int = 512,
    bayer: str | None = None,
) -> Response:
    size = max(64, min(2048, size))
    # bayer ends up embedded in the cache filename below — it must be one of
    # the four real patterns, both to fail cleanly and so it can never carry
    # a path separator into that filename (see write_stack_outputs' output_name
    # fix for the same class of bug).
    if bayer is not None and bayer.upper() not in _BAYER_PATTERNS:
        raise HTTPException(status_code=400, detail=f"Unknown bayer pattern: {bayer!r}")
    lib, proj = deps.open_target_project(request, safe)
    try:
        f = proj.get_frame(frame_id)
        if f is None:
            raise HTTPException(status_code=404, detail="No such frame")
        src = f.cached_path or f.source_path
        if not src or not Path(src).exists():
            raise HTTPException(status_code=404, detail="Frame file not found on disk")
        pattern = (bayer or f.bayer_pattern or "RGGB").upper()
        if pattern not in _BAYER_PATTERNS:
            # Defensive: a legacy/hand-edited DB row could hold a bad pattern.
            # Fall back to the OSC default rather than emitting it into the
            # cache filename or handing it to the debayer.
            pattern = "RGGB"
        cache_dir = thumbs_dir(proj.project_dir)
        out = cache_dir / f"web_{frame_id:06d}_{size}_{pattern}_v{THUMB_VERSION}.png"
        src_path = Path(src)
    finally:
        proj.close()
        lib.close()

    etag = f'"{frame_id}-{size}-{pattern}-{THUMB_VERSION}"'
    if request.headers.get("if-none-match") == etag and out.exists():
        return Response(status_code=304)

    if not out.exists():
        # Rendering is CPU-bound but fast; run it off the event loop and OFF the
        # single job worker so previews never queue behind a stack.
        await run_in_threadpool(
            generate_thumbnail, src_path, out, bayer_pattern=pattern, size=size
        )
    resp = FileResponse(out, media_type="image/png")
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp
