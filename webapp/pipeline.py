"""Job bodies: thin adapters that drive the seestack engine and report progress
into a :class:`~webapp.jobs.Job`.

These run on the single job-worker thread. Each opens the Library / Project,
calls the existing engine functions (``scan_and_organize``,
``run_qc_and_solve``, ``run_stack``), and maps their progress callbacks onto the
job record so the SSE stream and the jobs DB stay current.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from seestack.io.library import Library
from seestack.io.project import count_unreadable_frames
from seestack.io.scanner import run_qc_and_solve, scan_and_organize
from seestack.render.thumbnail import invalidate_frame_thumbs
from seestack.stack.pointings import MixedPointings, detect_mixed_pointings
from webapp import __version__ as APP_VERSION
from webapp.config import Settings
from webapp.jobs import Job, JobManager
from webapp.preview_orient import baked_north_up_deg
from webapp.schemas import (
    STACK_DEFAULTS_META_KEY,
    coerce_stack_options,
    strip_non_form_keys,
)
from webapp.walkaway import apply_unattended_rejection, parse_saved_stack_defaults

if TYPE_CHECKING:
    from seestack.io.project import StackRunRow

log = logging.getLogger(__name__)

# Per-target meta marker recording the solved+accepted frame count of the last
# *auto*-stack attempt. Used to break a crash loop: if a stack repeatedly kills
# the process (e.g. OOM), the container restarts, the watcher re-scans, and
# without this we'd auto-stack the same data forever. We attempt a given frame
# count once; the user can still trigger a manual stack to retry.
AUTO_STACK_ATTEMPT_META_KEY = "web_auto_stack_attempt"

# Per-target meta marker recording the confident-master fingerprint of the last
# calibration-availability *re-stack*. The frame-count auto-stack trigger only
# fires when new subs solve, so a beginner who follows the app's own "add darks"
# advice and drops in a master *without* capturing new subs would otherwise never
# get their noisy uncalibrated result re-stacked with the darks. The
# calibration recheck (:func:`_auto_stack_calibration_recheck`) closes that loop —
# and this marker holds it to *once per newly-available master set*, mirroring the
# crash-loop discipline of ``AUTO_STACK_ATTEMPT_META_KEY`` so a restack that (for
# any reason) stays uncalibrated can't re-trigger on every subsequent scan.
AUTO_STACK_CALIB_META_KEY = "web_auto_stack_calib_retrigger"

# Per-target meta marker recording how many of the last stack attempt's
# solved+accepted subs had **no readable file on disk at the time**. The
# attempt marker above is a pure DB-level count, so it cannot tell "I already
# covered these 800 subs" from "I attempted 800 subs but could only read 280 of
# them" — and without that distinction a stack crippled by a transient storage
# problem (an unmounted drive, a NAS share that flapped, a folder moved
# mid-session) marks the data covered and is never retried, leaving the thin,
# noisy result standing as the target's newest picture indefinitely. Pairing the
# attempt count with the unreadable count lets the trigger re-fire *once* the
# files come back, while still refusing to loop while they are still missing.
# Absent (older installs, and every healthy target) reads as 0, which is exactly
# today's behaviour — see :func:`_auto_stack_frame_count`.
AUTO_STACK_UNREADABLE_META_KEY = "web_auto_stack_unreadable"

# Per-target meta marker recording the ``best:solved`` fingerprint of the last
# *degraded-picture heal* re-stack. The readability preflight above stops a new
# walk-away stack from publishing a picture made thin by missing files, but it
# cannot undo one that was already published (the owner's live install sat on a
# 271-frame result where the same target had previously made 787), because the
# frame-count trigger correctly refuses to re-stack data it has already covered.
# :func:`_auto_stack_degraded_recheck` closes that loop once the data is all
# readable again, and this marker holds it to **once per situation** — mirroring
# the calibration recheck's discipline — so a heal that (for any reason) still
# comes out thin can never re-trigger on every subsequent scan.
AUTO_STACK_DEGRADED_META_KEY = "web_auto_stack_degraded_retrigger"

# How much thinner than the target's best a newest picture must be before a heal
# is worth the compute. A stack that drops a few subs at alignment is normal and
# run-to-run consistent; losing a fifth of the night is not. Both rails must be
# cleared, so a tiny target can't be re-stacked over a one-frame wobble.
AUTO_STACK_DEGRADED_MAX_RATIO = 0.8
AUTO_STACK_DEGRADED_MIN_LOSS = 2


def _progress(jm: JobManager, job: Job):
    """Engine ``(phase, done, total)`` callback bound to a job."""
    def cb(phase: str, done: int, total: int) -> None:
        job.set_progress(phase, done, total)
        jm.maybe_flush(job)
    return cb


def _unstacked_video_captures(
    settings: Settings, scan_root: Path,
) -> list[dict[str, Any]]:
    """The ``*_video/`` folders under ``scan_root`` the user hasn't dealt with yet.

    The scanner skips these deliberately (they hold no deep-sky subs) and says
    nothing, so a beginner's lunar clip can sit in ``incoming/`` unmentioned
    forever while every scan reports only the subs it added. This is the pointer
    to the page that *can* stack them.

    **Gated on "not already dealt with"**, or it would nag on every scan for the
    rest of the install's life: a capture that already has a stacked still, or a
    quicklook from the "Check this capture first" pass, is one the user has
    plainly found — it drops out of the report and stays out. Both checks are a
    single ``stat`` of a file the video store already writes, so this costs one
    cheap directory walk plus two stats per capture and never opens a video.

    Best-effort throughout: a discovery that raises (an unreadable drop, a
    vanished mount) returns nothing rather than failing a scan that has already
    ingested the user's frames.

    ``label`` is the plain-language subject for the sentence ("Moon", "Sun") and
    is **null unless the folder's own prefix says which**, because ``label``
    falls back to the folder's base name for an unrecognised capture — and
    "that's a stuff video" is worse copy than "that's a video capture". Deciding
    that here rather than on the client keeps the "am I confident?" test in one
    place instead of a magic-string check in TypeScript.
    """
    from seestack.video.discover import find_video_captures
    from webapp.video import has_quicklook, has_result

    out: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for cap in find_video_captures(scan_root):
            if has_result(settings, cap.id) or has_quicklook(settings, cap.id):
                continue
            out.append({
                "name": cap.folder_name,
                "label": cap.label if cap.kind in ("lunar", "solar") else None,
            })
    return out


def submit_pipeline(settings: Settings, jm: JobManager, *, root: str | None = None) -> Job:
    def body(job: Job) -> dict[str, Any]:
        return _pipeline_body(settings, jm, job, root=root)
    return jm.submit("pipeline", body)


def _pipeline_body(
    settings: Settings, jm: JobManager, job: Job, *, root: str | None
) -> dict[str, Any]:
    lib = Library.open_or_create(settings.resolved_library_root)
    scan_root = Path(root) if root else settings.resolved_incoming_dir
    summary: dict[str, Any] = {"root": str(scan_root), "targets": []}
    try:
        if settings.auto_ingest:
            job.set_progress("scan", 0, 0, f"Scanning {scan_root}")
            scan = scan_and_organize(
                lib, scan_root,
                copy_to_cache=settings.copy_to_cache,
                progress=_progress(jm, job),
            )
            # Re-QC a target when it gained new frames OR when a dedup-skipped
            # frame's cache was refreshed (a mid-copy sub whose source completed):
            # its stale QC was reset, so re-grade it here rather than waiting for
            # brand-new frames to touch the target.
            touched_names = [
                t.safe_name for t in scan.targets
                if t.n_frames_added > 0 or t.n_frames_refreshed > 0
            ]
            # A refreshed frame's content changed under a reused id, but its cached
            # preview PNGs key on id alone and only regenerate when missing — so
            # drop them here or the Frames table keeps showing the old capture.
            for t in scan.targets:
                for fid in t.refreshed_frame_ids:
                    with contextlib.suppress(OSError):
                        invalidate_frame_thumbs(lib.targets_dir / t.safe_name, fid)
            summary["scanned"] = scan.total_added
            # Folders the Seestar convention passed over as "the device's own
            # finished picture" that hold files its naming can't vouch for — i.e.
            # possibly a user's own raw subs sitting in a plainly-named folder
            # beside a "<T>_sub/". Empty on a healthy Seestar library (there the
            # skipped folders are pure "Stacked*.fit"), so this only ever appears
            # when a scan really has passed over frames unexplained. Reported,
            # never acted on: the skip's behaviour is unchanged.
            unvouched = [
                {"name": s.name, "n_files": s.n_files,
                 "n_unrecognised": s.n_unvouched}
                for s in scan.unvouched_skips
            ]
            if unvouched:
                summary["skipped_folders"] = unvouched
            # The *other* silent skip, and the one that has somewhere to go.
            # ``_apply_seestar_convention`` walks past "<T>_video/" folders with
            # the same wordless ``continue``, and that skip is right — they hold
            # no stackable deep-sky subs. But a beginner who copies their whole
            # Seestar share in and reads "40 subs added" has no way to know their
            # Lunar_video was passed over, and unlike the bare-folder case the
            # app *can* do something with it: the Moon & Sun page stacks exactly
            # these clips. Reported, never acted on.
            summary_videos = _unstacked_video_captures(settings, scan_root)
            if summary_videos:
                summary["video_folders"] = summary_videos
        else:
            touched_names = [t.safe_name for t in lib.list_targets()]
        summary["targets"] = touched_names

        if settings.auto_qc or settings.auto_solve:
            graded: dict[str, int] = {}
            # Subs auto-grade *put back* this pass (it reconsiders its own earlier
            # rejects against the now-larger population). Counted per target like
            # ``graded`` so the walk-away scan can say it out loud instead of the
            # frame silently reappearing.
            regraded_back: dict[str, int] = {}
            qc_errors: dict[str, str] = {}
            # Subs the stack-then-solve bootstrap rescued per target (it can only
            # engage when most subs failed to plate-solve). The single-target
            # jobs already return run_qc_and_solve's summary verbatim, but the
            # scan loop discarded it — so the walk-away path, which is exactly
            # where the rescue happens unattended, had no way to say so.
            rescued: dict[str, int] = {}
            # Subs put back because their file reappeared, after the owner had
            # set them aside as missing (see ``Project.restore_missing_frames``).
            # Reported so a scan that quietly un-does a manual decision says so.
            missing_restored: dict[str, int] = {}
            for safe in touched_names:
                if job.cancel_requested():
                    # Surface the cancel at the top level so JobManager._run's
                    # ``engine_cancelled`` check marks the job 'cancelled' rather
                    # than 'done' — a bare truthy summary would otherwise read as a
                    # fully-successful scan on the Jobs/History page.
                    summary["cancelled"] = True
                    break
                try:
                    proj = lib.open_target(safe)
                    try:
                        qc_summary = run_qc_and_solve(
                            proj,
                            astap_path=settings.astap_path,
                            astap_fov_deg=settings.astap_fov_deg,
                            astap_timeout_s=settings.astap_timeout_s,
                            max_workers=settings.cpu_workers,
                            run_qc=settings.auto_qc,
                            run_solve=settings.auto_solve,
                            only_new_qc=True,  # don't re-QC frames already done on re-scans
                            use_solve_hints=settings.astap_use_solve_hints,
                            auto_reject_streaks=not settings.keep_streaked_frames,
                            bootstrap_solve=settings.astap_bootstrap_solve,
                            progress=_progress(jm, job),
                            should_stop=job.cancel_requested,
                        )
                        n_rescued = int((qc_summary or {}).get("bootstrap_propagated") or 0)
                        if n_rescued > 0:
                            rescued[safe] = n_rescued
                        if settings.auto_grade_frames and settings.auto_qc:
                            counts = _auto_grade_target(proj, settings)
                            if counts.rejected:
                                graded[safe] = counts.rejected
                            if counts.restored:
                                regraded_back[safe] = counts.restored
                        # Subs the owner set aside as "gone" whose files are back.
                        # Free here (the project is already open) and one indexed
                        # predicate on a target that never used the button, i.e.
                        # every healthy install. See ``restore_missing_frames``.
                        n_back = len(proj.restore_missing_frames())
                        if n_back:
                            missing_restored[safe] = n_back
                    finally:
                        proj.close()
                    lib.refresh_target_stats(safe)
                except Exception as exc:  # noqa: BLE001 — one target shouldn't sink the batch
                    # A target-level failure in QC/solve (a process-pool spin-up
                    # error, a build_*_arglist raise, a DB hiccup) must isolate like
                    # every sibling per-target loop (auto-stack, reprocess-all,
                    # editor-batch) — otherwise one bad target aborts the whole
                    # unattended pipeline, marks the job 'error', and skips the
                    # auto-stack pass for *all* targets (the frames were already
                    # scanned/persisted, so this is purely lost automation + a
                    # misleading red job). A cancel surfaces as a graceful early
                    # return from run_qc_and_solve, not a raise, but re-check it here
                    # so a cancel-driven error is still classified as a cancel.
                    if job.cancel_requested():
                        summary["cancelled"] = True
                        break
                    log.warning("auto QC/solve failed for %s: %s", safe, exc)
                    qc_errors[safe] = str(exc)
            if graded:
                summary["auto_graded"] = graded
            if regraded_back:
                summary["auto_regraded_back"] = regraded_back
            if rescued:
                summary["bootstrap_rescued"] = rescued
            if missing_restored:
                summary["missing_files_restored"] = missing_restored
            if qc_errors:
                summary["qc_errors"] = qc_errors

        # Auto-stack runs as its own pass (not gated on QC/solve being on) and is
        # non-fatal per target. It considers *all* targets — not just the ones
        # touched by this batch — so enabling auto-stack and running a scan picks
        # up existing data too. A target is (re)stacked only when it has new
        # plate-solved accepted frames since its last stack, so repeated scans
        # don't redundantly re-stack unchanged targets.
        if settings.auto_stack:
            stacked: list[str] = []
            skipped: list[str] = []
            held_thin: list[dict[str, Any]] = []
            held_unreadable: list[dict[str, Any]] = []
            healed: list[dict[str, Any]] = []
            mixed_skipped: list[str] = []
            legacy_skipped: list[str] = []
            stack_errors: dict[str, str] = {}
            auto_edited = 0
            for entry in lib.list_targets():
                if job.cancel_requested():
                    summary["cancelled"] = True
                    break
                safe = entry.safe_name
                if entry.legacy_mixed_drop:
                    # A legacy whole-device / mixed-folder drop the container-
                    # expansion re-scan superseded: it holds several objects' subs
                    # (plus on-device outputs/videos) jumbled into one target, so
                    # auto-stacking it just makes mixed-pointing gibberish and burns
                    # compute — and the correct per-target versions already exist.
                    # Skip it (it's surfaced for one-click cleanup) without marking
                    # an attempt, so removing it is the only state change. A user can
                    # still stack it by hand if they really want to.
                    legacy_skipped.append(safe)
                    continue
                # The whole per-target body — pre-checks included — is wrapped so
                # one target can't sink the batch. The pre-check helpers each
                # open_target(safe), which raises FileNotFoundError if the target
                # was deleted mid-scan (live DELETE /api/targets/{safe}) or a
                # sqlite "database is locked" if a request thread holds the write
                # lock past the busy_timeout; without this guard such a raise
                # escapes _pipeline_body, marks the whole (already-successful)
                # scan job 'error', and skips auto-stack for every remaining
                # target — the exact non-fatality the QC/solve loop above honours.
                try:
                    calib_fp: str | None = None
                    degraded_fp: str | None = None
                    # Put back any sub the owner set aside as "gone" whose file
                    # has since reappeared, *before* deciding whether to stack —
                    # otherwise the target would stack the thin set once more
                    # before healing on the following scan. Covers targets the
                    # QC pass above didn't touch (no new subs), which is exactly
                    # the state a target sits in while its files are away.
                    _restore_missing_frames(lib, safe)
                    attempt_n = _auto_stack_frame_count(lib, safe)
                    if attempt_n is None:
                        # No *new* frames to stack — but if the target's stack is
                        # still uncalibrated and a confident master has newly
                        # become available (the beginner added darks after their
                        # first stack), re-stack it once to actually apply them.
                        recheck = _auto_stack_calibration_recheck(settings, lib, safe)
                        if recheck is None:
                            # …and if the target's newest picture came out
                            # materially thinner than one it already made, and
                            # every sub is readable again, heal it once rather
                            # than leave the worse picture standing (the state a
                            # storage hiccup left behind before the readability
                            # preflight existed).
                            heal = _auto_stack_degraded_recheck(lib, safe)
                            if heal is None:
                                skipped.append(safe)
                                continue
                            attempt_n, degraded_fp, heal_detail = heal
                        else:
                            attempt_n, calib_fp = recheck
                    if attempt_n < settings.auto_stack_min_frames:
                        # Too few located subs to make anything but single-frame
                        # colour speckle (the owner-reported gibberish). Hold the
                        # target back — *without* marking the attempt, so the next
                        # scan re-checks and stacks it the moment enough subs solve
                        # — rather than auto-publishing (and auto-editing) noise.
                        # The already-shipped thin-stack warning covers the
                        # notification; this is the "don't silently publish it" half.
                        held_thin.append(
                            {"target": safe, "frames": attempt_n,
                             "min": settings.auto_stack_min_frames})
                        continue
                    unread_hold = _auto_stack_readability_hold(
                        lib, safe, attempt_n, settings.auto_stack_min_frames)
                    if unread_hold is not None:
                        # Some of this target's subs have no file on disk right
                        # now, and stacking without them would publish a worse
                        # picture than the one that already stands. Hold back
                        # *without* marking the attempt — same discipline as
                        # held_thin — so the next scan stacks it the moment the
                        # files come back, instead of stamping the data
                        # "covered" and stranding the degraded result.
                        held_unreadable.append(unread_hold)
                        continue
                    if settings.mixed_pointing_guard and _mixed_pointing_check(
                            lib, safe) is not None:
                        # Looks like two+ targets in one folder — don't burn a
                        # walk-away stack on one pointing. Skip without marking the
                        # attempt, so the next scan re-checks (and stacks once the
                        # user rejects the odd-target frames), rather than stranding
                        # it.
                        mixed_skipped.append(safe)
                        continue
                    # Record the attempt *before* stacking so that if this stack
                    # crashes the whole process, the watcher won't re-trigger the
                    # identical stack on restart (crash-loop guard). A
                    # calibration-availability re-stack (no new frames) also stamps
                    # its master-set fingerprint first, so a restack that stays
                    # uncalibrated can't loop the recheck on every scan.
                    if calib_fp is not None:
                        _mark_auto_stack_calib_retrigger(lib, safe, calib_fp)
                    if degraded_fp is not None:
                        _mark_auto_stack_degraded_heal(lib, safe, degraded_fp)
                    _mark_auto_stack_attempt(lib, safe, attempt_n)
                    res = _stack_target(
                        settings, jm, job, lib, safe,
                        auto_bind_calibration=settings.auto_bind_calibration,
                        auto=True)
                    if res.get("cancelled"):
                        # A user cancel mid-stack is a survivable, non-crash outcome
                        # that recorded no run and raised no exception, so it never
                        # reaches the except handler below. Clear the crash-loop
                        # marker written at line ~123 (exactly as that handler does
                        # for a survivable error) — otherwise the target is stranded
                        # and never auto-stacked again until brand-new frames arrive
                        # — and don't report a cancelled target as stacked. The loop
                        # breaks on the next iteration's cancel check anyway.
                        with contextlib.suppress(Exception):
                            _clear_auto_stack_attempt(lib, safe)
                        if calib_fp is not None:
                            with contextlib.suppress(Exception):
                                _clear_auto_stack_calib_retrigger(lib, safe)
                        if degraded_fp is not None:
                            with contextlib.suppress(Exception):
                                _clear_auto_stack_degraded_heal(lib, safe)
                        summary["cancelled"] = True
                        break
                    stacked.append(safe)
                    if degraded_fp is not None:
                        # Report the heal only once it actually happened — the
                        # checks between the recheck and here (thin floor, mixed
                        # pointings) can still hold the target back.
                        healed.append(heal_detail)
                    # Optionally finish the fresh master into a picture (the same
                    # Auto-recipe chain the one-click Process/Reprocess use), so
                    # the fully-unattended path returns a finished image, not a
                    # flat linear master. Best-effort: never sinks the batch.
                    run_id = res.get("run_id")
                    if (settings.auto_edit_on_autostack and run_id is not None
                            and not job.cancel_requested()):
                        if _auto_edit_process_run(
                                lib, safe, run_id,
                                auto_crop=settings.auto_crop_border) is not None:
                            auto_edited += 1
                except Exception as exc:  # noqa: BLE001 — one target shouldn't sink the batch
                    # The process survived this failure, so the crash-loop marker
                    # written at line 123 must be cleared — otherwise a *transient*
                    # error (flapping mount, momentary lock) would strand the
                    # target's auto-stack permanently. A true process-killing crash
                    # never reaches here, so this doesn't weaken the crash-loop guard.
                    with contextlib.suppress(Exception):
                        _clear_auto_stack_attempt(lib, safe)
                    if calib_fp is not None:
                        with contextlib.suppress(Exception):
                            _clear_auto_stack_calib_retrigger(lib, safe)
                    if degraded_fp is not None:
                        with contextlib.suppress(Exception):
                            _clear_auto_stack_degraded_heal(lib, safe)
                    # A cancel that surfaced as a raise (rather than a graceful
                    # cancelled result) is a cancel, not a target error — classify
                    # it as one and stop, mirroring the QC/solve loop above.
                    if job.cancel_requested():
                        summary["cancelled"] = True
                        break
                    log.warning("auto-stack failed for %s: %s", safe, exc)
                    stack_errors[safe] = str(exc)
            summary["auto_stacked"] = stacked
            summary["auto_stack_skipped"] = skipped
            if held_thin:
                summary["auto_stack_held_thin"] = held_thin
            if held_unreadable:
                summary["auto_stack_held_unreadable"] = held_unreadable
            if healed:
                summary["auto_stack_healed"] = healed
            if mixed_skipped:
                summary["auto_stack_mixed_skipped"] = mixed_skipped
            if legacy_skipped:
                summary["auto_stack_legacy_skipped"] = legacy_skipped
            if auto_edited:
                summary["auto_edited"] = auto_edited
            if stack_errors:
                summary["stack_errors"] = stack_errors
        return summary
    finally:
        lib.close()


def submit_build_master(
    settings: Settings, jm: JobManager, *,
    kind: str, source_dir: str, name: str | None = None,
    method: str = "median", sigma: float = 3.0,
) -> Job:
    """Build a master dark/flat/bias from a folder of raw FITS frames and
    register it in the library-level calibration store."""
    def body(job: Job) -> dict[str, Any]:
        from webapp import calibration
        from seestack.calibrate.masters import build_master

        paths = calibration.find_fits_in_dir(source_dir)
        if not paths:
            raise FileNotFoundError(f"No FITS files found in {source_dir}")
        job.set_progress("loading", 0, len(paths), f"{len(paths)} frames")
        skipped: list[tuple[str, str]] = []
        built = build_master(
            paths, kind=kind, method=method, sigma=sigma,
            progress=_progress(jm, job),
            should_stop=job.cancel_requested,
            skipped=skipped,
        )
        if built is None:
            # Cancelled mid-build (no master was written). Surface a cancellation
            # sentinel so the worker classifies the job 'cancelled', not 'done'.
            return {"cancelled": True}
        array, meta = built
        entry = calibration.register_master(
            settings.resolved_library_root, name=name or "", array=array, meta=meta,
        )
        # Bucket the dropped frames so the Jobs page can tell the user how many of
        # their frames were actually used vs. set aside (and why) — not just a bare
        # "done" with a silently smaller master.
        skipped_buckets: dict[str, int] = {}
        for _fname, reason in skipped:
            skipped_buckets[reason] = skipped_buckets.get(reason, 0) + 1
        return {
            "id": entry["id"], "name": entry["name"], "kind": entry["kind"],
            "n_frames": entry["n_frames"], "width_px": entry["width_px"],
            "height_px": entry["height_px"],
            "n_skipped": len(skipped), "skipped_buckets": skipped_buckets,
            # How many frames the user actually pointed at, so a build that was
            # sampled down to the memory bound can say so. A beginner who drops
            # 200 darks and reads "built from 64 frames" has no way to tell
            # whether 136 failed or the app is broken; it did neither.
            "n_supplied": meta.n_supplied,
            # What the frames' own IMAGETYP cards said, and the plain-language
            # verdict on whether they agree with the kind that was asked for —
            # so "you just built a master dark out of your subs" is said at the
            # moment it happens, not only next time the Calibration page loads.
            # Both are None/absent when no frame carried a card we recognise.
            "header_kinds": dict(meta.header_kinds or {}),
            "header_note": calibration.header_kind_note(
                entry["kind"], meta.header_kinds, entry["n_frames"]),
        }

    return jm.submit("build_master", body)


class AutoGradeCounts(NamedTuple):
    """How many frames one auto-grade pass moved, in each direction.

    ``rejected`` is what the pass took away; ``restored`` is what it *gave back*
    (frames it had rejected against a smaller, noisier population that the
    now-larger night no longer flags). Both are worth saying out loud — the app
    narrates what automation did everywhere else, and a sub silently reappearing
    is as confusing as one silently vanishing.
    """

    rejected: int
    restored: int


def _auto_grade_target(proj: Any, settings: Settings) -> AutoGradeCounts:
    """Run auto-grade over a target's accepted frames and apply the rejections
    (the opt-in ``auto_grade_frames`` pipeline hook). Returns how many frames the
    pass rejected and how many it put back.
    Best-effort: grading must never sink a QC/ingest pass.

    ``grade_frames`` caps a *single* pass at ``MAX_REJECT_FRACTION`` of the
    considered set, but this hook re-grades a target on **every** scan and a
    Seestar drips subs continuously, so an actively-imaged target is re-graded
    many times. Two problems came out of that, and one grading pass over one
    stable population fixes both: we hand ``grade_frames`` the target's own
    ``auto:grade`` rejects as its ``reconsider`` list, so the set it decides over
    is "everything auto-grade has ever considered" — the accepted non-override
    frames **plus** the ones it already dropped.

    1. *The cap was per-pass.* Each pass used to re-centre on the **shrinking**
       survivor set (removing the low tail raises the median and tightens the
       MAD), so borderline frames that cleared the practical-significance floor
       last pass crossed it this pass and the cumulative auto-rejected fraction
       crept past the documented 25% rail (measured to converge at ~29% on a
       bimodal session). Grading over the combined set measures ``grade_frames``'
       own cap against that original population directly, so the rail is
       cumulative with no external budget arithmetic.
    2. *Machine decisions were permanent.* A frame rejected **early** — graded
       against a tiny, noisy population — stayed rejected forever even once
       hundreds of good subs made it plainly typical, silently losing the user a
       good sub. The same pass now names those frames in ``report.re_accept`` and
       we put them back.

    The combined set is invariant under auto-grade's own moves (a frame only ever
    swaps halves), so the pass is deterministic across scans and can't oscillate.
    A user decision is never touched: ``user_override`` frames are excluded from
    ``reconsider``, and the re-accept step only clears an ``auto:grade`` reason.
    """
    from seestack.qc.grading import apply_grade_reaccepts, apply_grade_report, grade_frames

    try:
        all_frames = list(proj.iter_frames())
        accepted = [f for f in all_frames if f.accept]
        # Frames auto-grade itself already rejected (machine decision, not a user
        # override) still belong to its population. Streak/QC/manual rejects are a
        # different decision and stay out of it entirely — neither counted nor
        # reconsidered.
        reconsider = [
            f for f in all_frames
            if not f.accept and not f.user_override
            and (f.reject_reason or "").startswith("auto:grade")
        ]
        if not accepted and not reconsider:
            return AutoGradeCounts(0, 0)
        report = grade_frames(
            accepted,
            sensitivity=settings.auto_grade_sensitivity,
            reconsider=reconsider,
        )
        changed = apply_grade_report(proj, report)
        restored = apply_grade_reaccepts(proj, report)
        if changed:
            log.info("Auto-grade rejected %d frame(s): %s", len(changed),
                     ", ".join(f"{r.name} ({r.primary_metric})"
                               for r in report.recommendations if r.frame_id in set(changed)))
        if restored:
            log.info(
                "Auto-grade re-accepted %d frame(s) the larger population no "
                "longer flags: %s", len(restored),
                ", ".join(str(fid) for fid in restored),
            )
        return AutoGradeCounts(len(changed), len(restored))
    except Exception as exc:  # noqa: BLE001 — advisory automation, never fatal
        log.warning("Auto-grade failed: %s", exc)
        return AutoGradeCounts(0, 0)


def submit_qc_solve(settings: Settings, jm: JobManager, safe: str) -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            proj = lib.open_target(safe)
            try:
                summary = run_qc_and_solve(
                    proj,
                    astap_path=settings.astap_path,
                    astap_fov_deg=settings.astap_fov_deg,
                    astap_timeout_s=settings.astap_timeout_s,
                    max_workers=settings.cpu_workers,
                    run_qc=settings.auto_qc or True,
                    run_solve=settings.auto_solve or True,
                    use_solve_hints=settings.astap_use_solve_hints,
                    auto_reject_streaks=not settings.keep_streaked_frames,
                    bootstrap_solve=settings.astap_bootstrap_solve,
                    progress=_progress(jm, job),
                    should_stop=job.cancel_requested,
                )
                summary = dict(summary)
                if settings.auto_grade_frames:
                    counts = _auto_grade_target(proj, settings)
                    if counts.rejected:
                        summary["auto_graded"] = counts.rejected
                    if counts.restored:
                        summary["auto_regraded_back"] = counts.restored
            finally:
                proj.close()
            lib.refresh_target_stats(safe)
            if job.cancel_requested():
                # QC/solve honours the cancel between frame completions and
                # returns its (truthy) partial summary with no cancelled marker;
                # surface it at the top level so the job is classified 'cancelled'
                # rather than a misleading 'done'. Partial QC results are already
                # persisted, so nothing is lost either way.
                summary["cancelled"] = True
            return summary
        finally:
            lib.close()

    return jm.submit("qc_solve", body, target=safe)


def submit_process_target(settings: Settings, jm: JobManager, safe: str) -> Job:
    """One-click "process this target": QC + plate-solve every frame, auto-grade
    (when enabled), then stack — the whole ``drop files → good image`` middle in
    one job, so the user reaches a finished stack without configuring the global
    auto toggles or hand-filling the Stack form.

    Reuses the same primitives as the auto pipeline (``run_qc_and_solve`` →
    ``_auto_grade_target`` → ``_stack_target``) but scoped to one target and run
    on demand regardless of the ``auto_*`` settings. The stack uses the target's
    saved defaults (falling back to the global defaults), exactly like auto-stack,
    and is **non-destructive** — a new ``stack_runs`` row alongside any existing
    output. The stack step is skipped (with a reason) when nothing is
    plate-solved yet or the job was cancelled during QC/solve.
    """
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            proj = lib.open_target(safe)
            try:
                summary = dict(run_qc_and_solve(
                    proj,
                    astap_path=settings.astap_path,
                    astap_fov_deg=settings.astap_fov_deg,
                    astap_timeout_s=settings.astap_timeout_s,
                    max_workers=settings.cpu_workers,
                    run_qc=True,
                    run_solve=True,
                    use_solve_hints=settings.astap_use_solve_hints,
                    auto_reject_streaks=not settings.keep_streaked_frames,
                    bootstrap_solve=settings.astap_bootstrap_solve,
                    progress=_progress(jm, job),
                    should_stop=job.cancel_requested,
                ))
                if settings.auto_grade_frames:
                    counts = _auto_grade_target(proj, settings)
                    if counts.rejected:
                        summary["auto_graded"] = counts.rejected
                    if counts.restored:
                        summary["auto_regraded_back"] = counts.restored
                solved_accepted = _solved_accepted_count(proj)
                # Pre-flight mixed-pointing check while the project is still open
                # (below reflects the post-grade accept state the stack will use).
                mixed = (_detect_mixed_pointings(proj)
                         if settings.mixed_pointing_guard else None)
            finally:
                proj.close()
            lib.refresh_target_stats(safe)

            summary["solved_accepted"] = solved_accepted
            if job.cancel_requested():
                # Cancelled *during* QC/solve, before the stack. Surface the
                # cancel at the top level (mirroring the stack-phase cancel below)
                # so the job is classified 'cancelled', not a misleading 'done'.
                summary["cancelled"] = True
                summary["stacked"] = False
                summary["stack_skipped_reason"] = "cancelled"
                return summary
            if solved_accepted == 0:
                # Nothing to combine yet (e.g. ASTAP not set up, so no frame has a
                # WCS). Leave a clear reason instead of failing the whole job.
                summary["stacked"] = False
                summary["stack_skipped_reason"] = "no_solved_frames"
                return summary
            if mixed is not None:
                # The batch looks like two+ targets in one folder — stacking would
                # burn the run on one pointing and silently drop the rest. Skip
                # with guidance instead (guard is opt-in; off by default).
                summary["stacked"] = False
                summary["stack_skipped_reason"] = "mixed_pointings"
                summary["mixed_pointings"] = _mixed_pointing_summary(mixed)
                summary["mixed_pointings_message"] = _mixed_pointing_message(mixed)
                return summary
            summary["stack"] = _stack_target(
                settings, jm, job, lib, safe,
                auto_bind_calibration=settings.auto_bind_calibration,
                auto=True)
            if summary["stack"].get("cancelled"):
                # Cancelled *during* the stack: no run was written. Surface the
                # cancellation at the top level (mirroring submit_stack /
                # reprocess_all) so JobMan._run's ``engine_cancelled`` check
                # classifies the job 'cancelled' rather than 'done' — otherwise a
                # user who cancels mid-stack sees a misleading "done" with
                # ``stacked:True``/``run_id:None`` on the Jobs page.
                summary["cancelled"] = True
                summary["stacked"] = False
                return summary
            summary["stacked"] = True
            run_id = summary["stack"].get("run_id")
            if run_id is not None and not job.cancel_requested():
                # Chain a one-click auto-edit onto the fresh master so the result
                # is a finished *picture*, not a flat linear stack: save the Auto
                # recipe as the run's editor recipe (so it opens edited) and
                # re-render its History/Target thumbnail through that recipe.
                # Best-effort — a failure here never fails the whole Process job;
                # the linear master is already recorded.
                n_ops = _auto_edit_process_run(
                    lib, safe, run_id, auto_crop=settings.auto_crop_border)
                if n_ops is not None:
                    summary["auto_edited"] = n_ops
            return summary
        finally:
            lib.close()

    return jm.submit("process_target", body, target=safe)


def submit_stack(
    settings: Settings, jm: JobManager, safe: str, options: dict[str, Any]
) -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            return _stack_target(settings, jm, job, lib, safe, options=options)
        finally:
            lib.close()

    return jm.submit("stack", body, target=safe)


def _stack_options_from_run_json(options_json: str | None) -> dict[str, Any] | None:
    """Parse a stack run's ``options_json`` back into a plain ``StackOptions``
    dict, or ``None`` when the run isn't a genuine stack.

    Editor-export and channel-combine runs are also recorded in ``stack_runs``
    but store a different shape (``{"editor_recipe": …}`` / ``{"channel_combine":
    …}``), so they're rejected — we only want to reuse the settings that produced
    an actual integration. Empty/garbage/unknown-only JSON also yields ``None``
    so the caller falls back to the target's saved defaults.
    """
    if not options_json:
        return None
    try:
        data = json.loads(options_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or "editor_recipe" in data or "channel_combine" in data:
        return None
    import dataclasses

    from seestack.stack.stacker import StackOptions

    valid = {f.name for f in dataclasses.fields(StackOptions)}
    clean = {k: v for k, v in data.items() if k in valid}
    return clean or None


def _last_stack_options_for_target(lib: Library, safe: str) -> dict[str, Any] | None:
    """The most recent *genuine* stack run's options for a target, or ``None``.

    Walks the target's runs newest-first and returns the first that parses as a
    real ``StackOptions`` dict (skipping editor/combine runs), so a reprocess
    reuses exactly the settings that made the target's current image.
    """
    proj = lib.open_target(safe)
    try:
        for run in proj.iter_stack_runs():  # newest first
            opts = _stack_options_from_run_json(run.options_json)
            if opts is not None:
                return opts
    finally:
        proj.close()
    return None


def _newest_genuine_stack_run(proj) -> StackRunRow | None:
    """The target's most recent *genuine* stack run (the first, newest-first, whose
    options parse as a real ``StackOptions`` — skipping editor-export/combine runs),
    or ``None`` when it has none. Shared by the reprocess reuse/stale logic and the
    stale-target count so they agree on what "the current image's stack" is.
    """
    for run in proj.iter_stack_runs():  # newest first
        if _stack_options_from_run_json(run.options_json) is not None:
            return run
    return None


def _last_stack_version_for_target(lib: Library, safe: str) -> str | None:
    """The ``engine_version`` of the target's most recent *genuine* stack run
    (skipping editor/combine runs), or ``None`` when it has no genuine stack or
    that run predates version tracking. Used by the "reprocess only stale targets"
    filter to skip targets already stacked on the current build.
    """
    proj = lib.open_target(safe)
    try:
        run = _newest_genuine_stack_run(proj)
        return run.engine_version if run is not None else None
    finally:
        proj.close()


def reprocess_status(lib: Library) -> dict[str, Any]:
    """Count targets whose current image is stale relative to the running build.

    A target is **outdated** when its most recent *genuine* stack was produced by
    a different app version than the one now running (including a run that predates
    version tracking, ``engine_version`` ``None`` — it was made by some older
    build). A target with no genuine stack yet is neither outdated nor up to date:
    there's no existing image to refresh, so it's excluded from both counts (it
    isn't "stale", it just hasn't been stacked). This drives the proactive
    "N targets were made with an older version — reprocess" nudge, so it counts
    only images a reprocess would actually change.

    Returns ``{current_version, outdated, up_to_date, total_targets}``.
    """
    outdated = 0
    up_to_date = 0
    total = 0
    for entry in lib.list_targets():
        total += 1
        proj = lib.open_target(entry.safe_name)
        try:
            run = _newest_genuine_stack_run(proj)
        finally:
            proj.close()
        if run is None:
            continue  # never stacked — not an out-of-date existing image
        if run.engine_version == APP_VERSION:
            up_to_date += 1
        else:
            outdated += 1
    return {
        "current_version": APP_VERSION,
        "outdated": outdated,
        "up_to_date": up_to_date,
        "total_targets": total,
    }


def auto_cast_summary(lib: Library) -> dict[str, Any]:
    """Aggregate every auto-edited run's finished sky-background cast into one
    library-wide "does Auto land neutral?" read-out.

    Each unattended auto-edit (Process-target / reprocess-everything / watcher
    auto-stack) stamps the finished picture's residual sky-background cast into
    that run's provenance (``editor_auto_skycast:{run_id}`` project meta — r/g/b
    sky medians + a neutral/colour verdict, see ``measure_sky_cast``). Read on
    their own those are one dimmed History line each; aggregated they answer the
    exact question the deferred "vet on REAL data: does Auto's colour path leave a
    background cast?" items need — *on how many of the owner's real auto-edited
    runs did the ``color_calibrate → SCNR`` path actually land the background
    neutral, and when it didn't, which way did it skew?*

    Pure read-only aggregation over data already on disk: iterates every target's
    stack runs, reads the stamped cast metas, and tallies the neutral/cast split,
    the counts by dominant tint, and the median per-channel deviation. Runs whose
    measurement couldn't be taken (``cast == "unknown"`` — a failed/empty stack)
    are ignored so they neither inflate nor skew the split. Empty (all zeros) until
    auto-edited runs accrue.

    Returns ``{measured, neutral, cast, by_cast, median_deviation}`` where
    ``measured`` is the number of auto-edited runs with a usable cast reading,
    ``neutral``/``cast`` split it, ``by_cast`` counts the dominant tints among the
    cast runs, and ``median_deviation`` is the median largest per-channel departure
    from grey across the measured runs (``None`` when nothing is measured).
    """
    import numpy as np

    from webapp.routers.editor import AUTO_EDIT_SKYCAST_PREFIX

    neutral = 0
    cast = 0
    by_cast: dict[str, int] = {}
    deviations: list[float] = []
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            for run in proj.iter_stack_runs():
                raw = proj.get_meta(f"{AUTO_EDIT_SKYCAST_PREFIX}{run.id}")
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(parsed, dict):
                    continue
                verdict = parsed.get("cast")
                if not isinstance(verdict, str) or verdict == "unknown":
                    continue  # not measurable — don't count it either way
                dev = parsed.get("deviation")
                if isinstance(dev, (int, float)):
                    deviations.append(float(dev))
                if verdict == "neutral" or parsed.get("neutral") is True:
                    neutral += 1
                else:
                    cast += 1
                    by_cast[verdict] = by_cast.get(verdict, 0) + 1
        finally:
            proj.close()
    measured = neutral + cast
    median_dev = float(np.median(deviations)) if deviations else None
    return {
        "measured": measured,
        "neutral": neutral,
        "cast": cast,
        "by_cast": by_cast,
        "median_deviation": (round(median_dev, 5)
                             if median_dev is not None else None),
    }


def _refresh_target(settings: Settings, jm: JobManager, job: Job,
                    lib: Library, safe: str) -> None:
    """Deep-rescan one target before it's restacked: re-run QC + plate-solve over
    *all* its existing library frames (not just new ones) and re-apply auto-grade,
    so a "reprocess everything" after an in-place upgrade also picks up QC / solve /
    grading improvements — not only the stacker's.

    ``run_qc_and_solve`` is called with ``only_new_qc=False`` so the metrics are
    re-derived for every frame with the current engine; ``apply_qc_result_to_db``
    still honours a user's manual accept/reject (``user_override``), so re-QC never
    clobbers a hand-made decision. Solving is best-effort — with no ASTAP available
    it simply solves nothing. Auto-grade is applied only when the user has grading
    enabled (``auto_grade_frames``), matching the ordinary ingest pipeline.

    Best-effort and self-contained: a refresh failure is logged and swallowed so it
    can never sink the target's restack (the whole point of reprocess is the new
    stack; a flaky re-QC must not cost the user that)."""
    try:
        proj = lib.open_target(safe)
        try:
            run_qc_and_solve(
                proj,
                astap_path=settings.astap_path,
                astap_fov_deg=settings.astap_fov_deg,
                astap_timeout_s=settings.astap_timeout_s,
                max_workers=settings.cpu_workers,
                run_qc=True,
                run_solve=True,
                only_new_qc=False,  # re-derive QC for *every* frame with the new engine
                use_solve_hints=settings.astap_use_solve_hints,
                auto_reject_streaks=not settings.keep_streaked_frames,
                bootstrap_solve=settings.astap_bootstrap_solve,
                progress=_progress(jm, job),
                should_stop=job.cancel_requested,
            )
            if settings.auto_grade_frames:
                _auto_grade_target(proj, settings)
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    except Exception as exc:  # noqa: BLE001 — refresh is advisory, never fatal
        log.warning("reprocess-all deep-rescan failed for %s: %s", safe, exc)


def submit_reprocess_all(settings: Settings, jm: JobManager, *,
                         stale_only: bool = False,
                         deep_rescan: bool = False,
                         auto_edit: bool = False) -> Job:
    """Restack *every* target with the current engine — the owner's one-click
    "reprocess everything after an upgrade" maintenance action.

    Each target is restacked reusing the settings that produced its current image
    (its last genuine stack run's ``options_json``; falling back to its saved
    stack defaults / global auto-defaults when it has none). The per-target stacks
    run **serially** inside this single job — the stack hot path is memory-bounded
    on purpose (OOM history), so exactly one runs at a time — and each is recorded
    as a *new* ``stack_runs`` row **alongside** the existing output: nothing is
    ever deleted or overwritten, so a worse restack can't lose a good result.

    Cancellable between targets (and within each target's stack). A target that
    fails to stack is isolated: its error is recorded and the batch carries on.

    ``stale_only`` skips targets whose most recent *genuine* stack was already
    produced by the current app version — so after an upgrade the user reprocesses
    only the images that would actually change, not the whole library. A target
    with no genuine stack (or one that predates version tracking) is treated as
    stale and reprocessed.

    ``deep_rescan`` additionally re-runs QC / plate-solve / auto-grade over each
    target's existing frames *before* its restack (see :func:`_refresh_target`), so
    the reprocess also benefits from QC/solve/grading improvements, not just the
    stacker. Off by default (the plain restack is the common case and a full rescan
    is much slower); the refresh is best-effort per target and honours manual frame
    decisions. It runs only for targets that are going to be restacked, so a
    ``stale_only`` skip skips the rescan too.

    Each reprocessed run is written to a **fresh, version-tagged basename** (see
    :func:`_reprocess_output_basename`) rather than the target's existing
    ``master`` — otherwise the reused ``options_json`` (which carries the old run's
    ``output_name="master"``) would make the stacker *archive* the current
    ``master.fits`` to an orphaned timestamped file and write the new pixels in its
    place, so the old run's DB row would silently start serving the *new* image.
    A distinct basename keeps the old output on disk and reachable, making the
    "nothing is deleted or overwritten — compare them in History" promise true.

    ``auto_edit`` chains the one-click Auto recipe onto every restacked run (see
    :func:`_auto_edit_process_run`), so a reprocess after an upgrade yields finished
    *pictures* across the whole library — not flat linear masters the user must
    hand-edit one by one. Off by default: it seeds an editor recipe on many runs at
    once, so it's an explicit opt-in. It only touches each *new* run's own recipe and
    preview thumbnail (never an existing run's saved edit), is best-effort per run (a
    failure never fails the batch), and is fully reversible in the editor (Reset/undo).
    """
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            targets = list(lib.list_targets())
            total = len(targets)
            job.set_progress("reprocess", 0, total, f"0/{total} targets")
            jm.maybe_flush(job)
            stacked = 0
            skipped = 0
            rescanned = 0
            auto_edited = 0
            failed: list[dict[str, str]] = []
            cancelled = False
            for i, entry in enumerate(targets):
                if job.cancel_requested():
                    cancelled = True
                    break
                safe = entry.safe_name
                name = entry.name or safe
                if stale_only and _last_stack_version_for_target(lib, safe) == APP_VERSION:
                    # Up to date on the current build — nothing would change, skip it.
                    skipped += 1
                    job.set_progress("reprocess", i + 1, total, f"{i + 1}/{total} targets")
                    jm.maybe_flush(job)
                    continue
                # Persistent label; the inner run_stack progress updates
                # phase/done/total per frame but leaves detail untouched.
                job.detail = f"Target {i + 1}/{total}: {name}"
                jm.maybe_flush(job)
                if deep_rescan and not job.cancel_requested():
                    # Re-derive QC/solve/grade with the current engine first, so the
                    # restack below stacks the freshly-graded frame set.
                    _refresh_target(settings, jm, job, lib, safe)
                    rescanned += 1
                    if job.cancel_requested():
                        cancelled = True
                        break
                reuse = _last_stack_options_for_target(lib, safe)
                # Write to a fresh, version-tagged basename so the reprocessed run
                # lands *alongside* the target's existing output instead of
                # archiving/orphaning its ``master`` (the reused options carry the
                # old run's output_name). This is what makes the batch genuinely
                # non-destructive.
                proj = lib.open_target(safe)
                try:
                    existing = {r.output_basename for r in proj.iter_stack_runs()
                                if r.output_basename}
                finally:
                    proj.close()
                fresh_name = _reprocess_output_basename(existing, APP_VERSION)
                try:
                    res = _stack_target(
                        settings, jm, job, lib, safe,
                        options=reuse, output_name=fresh_name,
                        auto_bind_calibration=settings.auto_bind_calibration)
                except Exception as exc:  # noqa: BLE001 — isolate one bad target
                    log.exception("reprocess-all: target %s failed", safe)
                    failed.append({"target": safe, "error": f"{type(exc).__name__}: {exc}"})
                else:
                    if res.get("cancelled"):
                        cancelled = True
                        break
                    stacked += 1
                    run_id = res.get("run_id")
                    if auto_edit and run_id is not None and not job.cancel_requested():
                        # Chain the one-click Auto recipe onto the fresh master so the
                        # reprocess yields a finished *picture*, not a flat linear
                        # stack — same helper the single-target Process action uses.
                        # Best-effort: a failure here never fails the batch.
                        if _auto_edit_process_run(
                                lib, safe, run_id,
                                auto_crop=settings.auto_crop_border) is not None:
                            auto_edited += 1
                job.set_progress("reprocess", i + 1, total, f"{i + 1}/{total} targets")
                jm.maybe_flush(job)
            return {
                "total": total,
                "stacked": stacked,
                "skipped": skipped,
                "rescanned": rescanned,
                "auto_edited": auto_edited,
                "failed": failed,
                "cancelled": cancelled,
            }
        finally:
            lib.close()

    return jm.submit("reprocess_all", body)


def _load_full_rgb_wcs(fits_path: str) -> tuple[Any, Any]:
    """Read a stack FITS to float32 (H,W,3) + an optional celestial WCS."""
    import numpy as np
    from astropy.io import fits as _fits

    with _fits.open(fits_path) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float32)
        header = hdul[0].header
    if data.ndim == 3:
        rgb = np.transpose(data, (1, 2, 0))
        if rgb.shape[2] == 1:
            rgb = np.repeat(rgb, 3, axis=2)
        elif rgb.shape[2] > 3:
            rgb = rgb[..., :3]
    else:
        rgb = np.stack([data, data, data], axis=-1)
    wcs = None
    try:
        from astropy.wcs import WCS
        w = WCS(header).celestial
        if w.has_celestial:
            wcs = w
    except Exception:  # noqa: BLE001
        wcs = None
    return rgb, wcs


def _deconv_psf_meta(recipe) -> dict[str, Any]:  # noqa: ANN001
    """If an editor recipe includes enabled ``detail.deconvolve`` op(s), return a
    ``DECONPSF`` provenance card recording the Gaussian PSF σ (px) actually used,
    so a sharpened export self-documents whether and how hard it was deconvolved.

    Records a single float when one deconvolution ran, or a comma-joined string
    when several ran (in application order). Empty dict when none did.
    """
    sigmas = [round(float(op.params.get("psf_sigma", 1.5)), 3)
              for op in recipe.ops
              if op.enabled and op.id == "detail.deconvolve"]
    if not sigmas:
        return {}
    value: Any = sigmas[0] if len(sigmas) == 1 else ", ".join(str(s) for s in sigmas)
    return {"DECONPSF": (value, "Richardson-Lucy PSF sigma (px)")}


def _recipe_history(recipe) -> list[str]:  # noqa: ANN001
    """Human-readable FITS HISTORY lines, one per enabled editor op (in order),
    e.g. ``AstroStack: detail.denoise(method=wavelet, strength=0.5)``. This is the
    canonical FITS provenance mechanism, so an edited export self-documents its
    full processing chain in Siril/PixInsight/APP — not just the op count."""
    lines: list[str] = []
    for op in recipe.ops:
        if not op.enabled:
            continue
        parts = []
        for k, v in op.params.items():
            if isinstance(v, float):
                v = round(v, 4)
            # skip long/structured params (e.g. curve control points) — keep the
            # line human-readable and within the 72-char FITS card limit.
            text = f"{k}={v}"
            if len(text) <= 24:
                parts.append(text)
        args = ", ".join(parts)
        lines.append(f"AstroStack: {op.id}({args})"[:72])
    return lines


def _carry_provenance(fits_path: str) -> dict[str, Any]:
    """Read provenance cards from a source stack FITS so a derived export can
    keep describing the underlying integration (target, frame count, exposure).

    Best-effort: any header that can't be read simply yields no carry-over cards.
    Only the integration-describing keys are carried; ``STACKER``/``STACKMTD`` are
    intentionally left for the caller to overwrite with the derivation method.
    """
    from astropy.io import fits as _fits

    carry: dict[str, Any] = {}
    try:
        with _fits.open(fits_path) as hdul:
            header = hdul[0].header
            for key in ("OBJECT", "NFRAMES", "EXPOSURE", "EXPTOTAL",
                        "COLORTYP", "DATE-OBS", "DATE-END",
                        # The camera the subs were taken with, and the optics it
                        # can be derived from — so a baked caption names the
                        # owner's actual gear instead of asserting a model.
                        "INSTRUME", "FOCALLEN"):
                if key in header:
                    carry[key] = (header[key], header.comments[key])
    except Exception:  # noqa: BLE001 — provenance is non-critical
        pass
    return carry


def _nameplate_camera(prov: dict) -> str | None:
    """The camera to print on a baked caption, from the stack's own header.

    This used to be the constant ``"ZWO Seestar S50"``, applied unconditionally to
    the nameplate, the keepsake and every print — a **wrong fact printed onto every
    shared picture** of an owner who has an S30, justified by a comment citing an
    `AGENTS.md` §1 that had never named a model. It now reads what the stack says
    (``INSTRUME``, stamped from the subs' own headers since v0.326.5, else the
    optics), and returns ``None`` when it says nothing — a caption with no camera
    is honest; a caption naming the wrong one is not.

    A master stacked before v0.326.5 carries neither card, so its captions simply
    drop the camera until the target is next stacked. That is the intended
    behaviour, not a gap to paper over with a default.
    """
    from seestack.io.fits_loader import camera_name_from_header

    return camera_name_from_header({k: v[0] for k, v in prov.items()})


def _nameplate_fields(fits_path: str, entry: Any, run: Any,
                      lon_deg: float | None = None) -> Any:
    """Build a :class:`NameplateFields` for a run's share export, preferring the
    stamped FITS provenance and falling back to the library/run record. Every
    field is best-effort — a missing/unparseable one is simply left ``None`` and
    the nameplate omits that part (never a blank line).

    The **date** is the exception that reads the run record *first*: it is the
    app's own answer to "when was this shot" (``capture_start_utc`` /
    ``capture_end_utc``), named as the observing night through the same helper
    every other night surface uses, so a baked caption and the Nights card cannot
    date one session differently. The header card is the fallback — it is what a
    FITS from elsewhere, or one written before the stacker stamped a capture
    time, has to offer.

    ``lon_deg`` is the observer's longitude for that bucketing; every caller
    passes ``Settings.site_lon`` so all three nameplate surfaces agree. Unset
    (the common case — a beginner rarely fills a location in) falls back to UTC
    noon-to-noon, exactly as the rest of the app does.
    """
    from seestack.nameplate import NameplateFields
    from webapp.capture_nights import capture_night_count, capture_night_range

    prov = _carry_provenance(fits_path)  # key -> (value, comment)

    def _num(key: str, default: Any = None) -> Any:
        card = prov.get(key)
        try:
            return float(card[0]) if card is not None else default
        except (TypeError, ValueError):
            return default

    target = None
    obj = prov.get("OBJECT")
    if obj is not None and str(obj[0]).strip():
        target = str(obj[0]).strip()
    else:
        target = getattr(entry, "name", None)
    # A beginner who drops loose FITS in gets a target called "Unsorted" or
    # "MyWorks_2026-08-14", and that is what the caption prints under the picture
    # they were about to post. When the plate solve lands squarely on a catalog
    # object *and* the stored name identifies nothing, the catalog's own name is
    # the honest, useful title. `confident_object_title` keeps the user's words
    # whenever they mean something, so this can only ever replace a name that
    # said nothing. Display-time only — nothing is written back to the target,
    # the library or the FITS.
    from seestack.objectinfo import confident_object_title
    try:
        better = confident_object_title(
            target, getattr(entry, "ra_deg", None), getattr(entry, "dec_deg", None))
    except Exception:  # a catalog read is best-effort, like every other field here
        better = None
    if better:
        target = better

    n_card = prov.get("NFRAMES")
    try:
        n_frames = int(n_card[0]) if n_card is not None else getattr(run, "n_frames_used", None)
    except (TypeError, ValueError):
        n_frames = getattr(run, "n_frames_used", None)

    date_iso, date_end_iso = capture_night_range(
        getattr(run, "capture_start_utc", None),
        getattr(run, "capture_end_utc", None),
        lon_deg,
    )
    # How many nights the span covers, bucketed for the same longitude, so the
    # baked caption and the app's own night surfaces cannot disagree. Absent for
    # every run predating schema 19, which simply captions the span alone.
    nights = capture_night_count(getattr(run, "capture_hours_json", None), lon_deg)
    if date_iso is None:
        for key in ("DATE-OBS", "DATE-END"):
            card = prov.get(key)
            value = str(card[0]).strip() if card is not None else ""
            if value:
                if date_iso is None:
                    date_iso = value
                else:
                    date_end_iso = value

    return NameplateFields(
        target=target,
        integration_s=_num("EXPTOTAL", getattr(run, "total_exposure_s", None)),
        n_frames=n_frames,
        sub_exposure_s=_num("EXPOSURE"),
        date_iso=date_iso,
        date_end_iso=date_end_iso,
        nights=nights,
        camera=_nameplate_camera(prov),
    )


def _render_recipe_fullres(fits_path: str, recipe_dict: dict, progress,
                           errors: list[str] | None = None) -> tuple[Any, Any]:
    """Apply an editor recipe to a full-res FITS. Returns ``(out_rgb, recipe)``
    where ``out_rgb`` is the display-stretched 0..1 result. A default STF
    autostretch is applied if the recipe has no stretch op (so the result is never
    raw-linear/black), matching the live preview's fallback.

    An op that raises on the full-res data is dropped (best-effort, like the live
    preview) but its failure message is appended to ``errors`` (when provided) —
    same format as ``apply_recipe`` — so the caller can surface it instead of the
    export silently changing the look with no notice to the user.

    When ``fits_path`` is itself a tone-mapped display-space export (re-editing an
    edited run), the default fallback stretch is suppressed so an empty/no-stretch
    recipe doesn't double-stretch the already-stretched image — matching the live
    preview's ``ctx.already_display`` behaviour."""
    import numpy as np

    from seestack.edit.recipe import recipe_from_dict
    from seestack.edit.registry import EditContext, as_rgb, get_op

    from seestack.edit.proxy import load_coverage, load_frame_coverage
    from seestack.stack.output import fits_is_display_space

    display_space = fits_is_display_space(fits_path)
    rgb, wcs = _load_full_rgb_wcs(fits_path)
    recipe = recipe_from_dict(recipe_dict)
    n = max(len([o for o in recipe.ops if o.enabled]), 1)
    # Load the run's per-pixel coverage map (if any) so the "Coverage leveling" op
    # can equalise the sky across mosaic panels; None for a single-field image.
    coverage = load_coverage(fits_path)
    # …and the honest per-pixel frame count beside it, so the leveling op bins
    # this mosaic's panels by subs rather than by a sum of weights. None on a run
    # recorded before that sibling existed — same behaviour as before.
    ctx = EditContext(wcs=wcs, is_proxy=False, proxy_scale=1.0, coverage=coverage,
                      frame_coverage=load_frame_coverage(fits_path))
    ctx.stage = "linear"
    out = as_rgb(np.asarray(rgb, dtype=np.float32))
    stretched = False
    done = 0
    for op in [o for o in recipe.ops if o.enabled]:
        spec = get_op(op.id)
        if spec is None:
            continue
        try:
            out = as_rgb(spec.apply(out, op.params, ctx))
            if spec.is_stretch:
                stretched = True
                ctx.stage = "nonlinear"
        except Exception as exc:  # noqa: BLE001
            msg = f"{spec.label}: {type(exc).__name__}: {exc}"
            log.warning("editor op %s failed on export: %s", op.id, msg)
            if errors is not None:
                errors.append(msg)
        done += 1
        progress("render", done, n)
    if not stretched and not display_space:
        # Mirror the live preview's fallback (seestack/edit/pipeline.py): the STF
        # autostretch renders uncovered (NaN) pixels as black 0, so restore NaN
        # afterwards. Without this the export bakes mosaic-gap / reproject-border
        # "no coverage" to real black in the float32 FITS — diverging from the
        # preview and making a re-edit treat the gap as covered black. Using the
        # same autostretch as the preview keeps a no-stretch export byte-parallel
        # with what the editor showed.
        from seestack.edit.registry import finite_mask
        from seestack.render.thumbnail import autostretch
        uncovered = ~finite_mask(out)
        out = as_rgb(autostretch(out)).copy()
        out[uncovered] = np.nan
    return out, recipe


def _edit_export_wcs_text(fits_path: str, recipe) -> str | None:  # noqa: ANN001
    """The celestial WCS to write onto an editor export of ``fits_path``.

    An editor export used to be written with ``wcs_text=None`` unconditionally, so
    **every** edited picture lost its sky solution — and with it North-up, the
    scale bar, the compass and object labels, all of which read the run's own FITS
    (:func:`seestack.io.wcs_io.celestial_wcs_from_fits`). Tone edits don't move a
    single pixel, so there was nothing to lose in the first place; crop and resize
    move pixels in a way the solution can follow exactly.

    Returns ``None`` — no WCS, rather than a wrong one — when the source has no
    solution, or when the recipe rotates (see
    :func:`~seestack.edit.ops.geometry.geometry_pixel_steps`). Best-effort: any
    failure here yields ``None`` and the export is written exactly as it was
    before, so this can never cost a user their edit.
    """
    from seestack.edit.ops.geometry import geometry_pixel_steps
    from seestack.io.wcs_io import celestial_wcs_from_fits, wcs_text_after_pixel_steps, wcs_to_text

    try:
        wcs, width, height = celestial_wcs_from_fits(fits_path)
        if wcs is None or width <= 0 or height <= 0:
            return None
        steps = geometry_pixel_steps(recipe, (height, width))
        if steps is None:
            return None
        return wcs_text_after_pixel_steps(wcs_to_text(wcs), steps)
    except Exception:  # noqa: BLE001 — provenance, never worth failing an export over
        log.warning("editor export WCS carry-over failed", exc_info=True)
        return None


def render_run_recipe_fullres_png(
    fits_path: str, recipe_dict: dict, *,
    max_long_edge: int = 8000, north_up: bool = False,
) -> bytes:
    """PNG bytes of a run's full-res FITS rendered through a *saved editor recipe* —
    the finished, edited picture at native resolution, matching the preview the user
    clicked.

    A "Process target" auto-edit leaves the run's FITS **linear** and stores the
    tone-mapped look as the run's editor recipe, so the plain STF render
    (:func:`~seestack.render.thumbnail.render_preview_png_full_res`) serves the
    *un-edited* master — the wrong picture — for such a run. This renders the recipe
    instead and encodes it exactly like ``render_preview_png_full_res`` (same
    ``north_up`` rotation + ``max_long_edge`` decimation), so the full-res download
    is the picture on screen, just bigger.
    """
    import io

    import numpy as np
    from PIL import Image

    from seestack.render.thumbnail import _apply_north_up
    from seestack.stack.output import pack_unit

    def _noop_progress(*_a: Any, **_k: Any) -> None:  # this path has no job to report to
        return None

    out, _recipe = _render_recipe_fullres(fits_path, recipe_dict, _noop_progress)
    disp = np.clip(np.nan_to_num(np.asarray(out, dtype=np.float32)), 0.0, 1.0)
    if north_up:
        disp = _apply_north_up(disp, fits_path)
    u8 = pack_unit(disp)
    img = Image.fromarray(u8, mode="RGB")
    h, w = u8.shape[:2]
    long_edge = max(h, w)
    if long_edge > max_long_edge:
        scale = max_long_edge / long_edge
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                         Image.BOX)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_run_full_res_png(
    run, recipe_json: str | None, *,  # noqa: ANN001 — a StackRunRow, detached from the DB
    north_up: bool = False, max_long_edge: int = 8000,
) -> bytes:
    """PNG bytes of **the run's current picture** at native resolution.

    The one place that decides *which* full-resolution render a finished run
    means — the saved editor recipe when its preview is a baked display-space
    edit, otherwise the STF (or the asinh curve History's "Adjust" saved), plus
    the North-up turn the stored preview already carries. Both callers go
    through it: the per-run download button
    (``…/stack-runs/{id}/full-res-png``) and the whole-library archive
    (:func:`submit_pictures_archive`), so a picture in the zip cannot come out
    looking different from the same picture downloaded on its own.

    ``recipe_json`` is the run's saved editor recipe *when its preview is
    display-space* — the caller reads it, because only the caller has the
    project open. ``None`` (no recipe, or a corrupt one) renders the master.
    Blocking: run it in a threadpool from async code.
    """
    recipe_dict = None
    if recipe_json:
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(recipe_json)
            if isinstance(parsed, dict):
                recipe_dict = parsed

    # A run whose preview a past "Adjust → North up → Save" turned shows that
    # turned picture *everywhere* — the thumbnail, the big view, the share JPEG,
    # the wallpaper — because all of them serve the stored bytes. This render
    # starts from the FITS instead, which is on the canvas grid, so without this
    # it would hand back the same picture rotated back: a download that visibly
    # disagrees with the picture it claims to be. The turn is applied whenever
    # the stored bytes carry one, whether or not the caller asked for it — and
    # asking for it as well is the same render, not a second rotation, because
    # both mean "the run's own full North-up correction".
    render_north_up = bool(north_up) or bool(baked_north_up_deg(run))

    if recipe_dict is not None:
        return render_run_recipe_fullres_png(
            run.fits_path, recipe_dict,
            max_long_edge=max_long_edge, north_up=render_north_up)
    # A run the user tuned in History's "Adjust" has its stored preview baked
    # through the *asinh* curve, not the STF — and the thumbnail, share-JPEG and
    # wallpaper all serve those bytes. Carry the saved stretch/black into the
    # full-res render so this download shows the same picture instead of
    # silently reverting to the autostretch. An unadjusted run (columns NULL)
    # keeps the STF exactly as before.
    from seestack.render.thumbnail import render_preview_png_full_res

    return render_preview_png_full_res(
        run.fits_path, max_long_edge=max_long_edge, north_up=render_north_up,
        stretch=run.preview_stretch, black=run.preview_black)


def _apply_editor_to_run(lib: Library, safe: str, run_id: int,
                         recipe_dict: dict | None,
                         *, output_name: str | None, tiff_mode: str,
                         progress) -> dict[str, Any]:
    """Apply an editor recipe to one run's full-res FITS and record a NEW run.
    Non-destructive: the source run is untouched.

    ``recipe_dict=None`` means **this run's own saved recipe** — the "finish the
    edit I already saved" case. Resolved here, inside the project this function
    already opens, so the batch that finishes a whole library of saved edits
    needs no second export path and no extra project open per picture.
    """
    import json as _json
    from datetime import datetime, timezone

    import numpy as np

    from seestack.edit.recipe import recipe_from_json
    from seestack.io.project import Project, StackRunRow
    from seestack.stack.output import write_stack_outputs
    from webapp.routers.editor import RECIPE_META_PREFIX

    entry = lib.find_target(safe)
    if entry is None:
        raise FileNotFoundError(f"no target '{safe}'")
    proj = Project.open(lib.target_dir(entry))
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None or not run.fits_path or not Path(run.fits_path).exists():
            raise FileNotFoundError(f"run {run_id} has no FITS")
        if recipe_dict is None:
            # Validated on load (stale ops dropped, params clamped), like every
            # other read of a stored recipe.
            saved = recipe_from_json(proj.get_meta(f"{RECIPE_META_PREFIX}{run_id}"))
            if not saved.ops:
                raise ValueError(f"run {run_id} has no saved edit to export")
            recipe_dict = saved.to_dict()
        base = output_name or f"{run.output_basename}_edit"

        op_errors: list[str] = []
        out, recipe = _render_recipe_fullres(run.fits_path, recipe_dict, progress,
                                             errors=op_errors)

        n_ops = len([o for o in recipe.ops if o.enabled])
        edit_meta = _carry_provenance(run.fits_path)
        edit_meta["STACKMTD"] = (f"editor recipe ({n_ops} ops)",
                                 "how this image was produced")
        edit_meta["EDITFROM"] = (int(run_id), "source stack run id")
        edit_meta.update(_deconv_psf_meta(recipe))
        history = _recipe_history(recipe)
        if history:
            edit_meta["HISTORY"] = history

        coverage = np.ones(out.shape[:2], dtype=np.float32)
        # `out` is the recipe's display-space result (a stretch was applied), so
        # the TIFF/preview must be written as-is, not re-stretched/linear-rescaled.
        paths = write_stack_outputs(
            project_dir=proj.project_dir, rgb=out, coverage=coverage,
            wcs_text=_edit_export_wcs_text(run.fits_path, recipe),
            out_basename=base, tiff_mode=tiff_mode,
            header_meta=edit_meta, already_display=True,
        )
        # Re-exporting under an existing basename archives the prior export's
        # files; repoint its history row at them so it keeps serving its own
        # image rather than this new one (done before adding the new run).
        if paths.get("archived"):
            proj.repoint_stack_runs(paths["archived"])
        new_id = proj.add_stack_run(StackRunRow(
            id=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            output_basename=base,
            fits_path=str(paths["fits"]), tiff_path=str(paths["tiff"]),
            preview_path=str(paths["preview"]),
            n_frames_used=run.n_frames_used,
            canvas_h=out.shape[0], canvas_w=out.shape[1],
            coverage_min=1, coverage_max=1,
            options_json=_json.dumps({"editor_recipe": recipe.to_dict(),
                                      "derived_from": run_id,
                                      # The export is the recipe's tone-mapped
                                      # result, not a linear stack — so re-opening
                                      # it in the editor must not default-stretch
                                      # it again (matches the FITS SSDISPLY card).
                                      "display_space": True}),
            notes="edited",
            engine_version=APP_VERSION,
            # An export is the *same light* as the run it was edited from, so it
            # carries that run's capture window forward. Without this an edited
            # picture would lose the one date that says when it was shot and fall
            # back to no date at all — the export's own stamp is when the editor
            # ran, which is exactly the thing this window exists to stop us
            # quoting.
            capture_start_utc=run.capture_start_utc,
            capture_end_utc=run.capture_end_utc,
            capture_hours_json=getattr(run, "capture_hours_json", None),
        ))
        # Remember, on the *source* run, which edit this export rendered. Its
        # saved recipe is deliberately left alone — it is the user's document —
        # so this marker is the only thing that can tell "saved and never
        # exported" from "saved, and now exported", and without it every surface
        # that offers to finish the edit kept offering after it was finished
        # (see ``webapp.routers.stack._unexported_edit``). Best-effort: a picture
        # that was written must not be reported as failed because an annotation
        # couldn't be.
        from webapp.routers.editor import EXPORTED_RECIPE_META_PREFIX
        with contextlib.suppress(Exception):
            proj.set_meta(f"{EXPORTED_RECIPE_META_PREFIX}{run_id}", recipe.to_json())
    finally:
        proj.close()
    lib.refresh_target_stats(safe)
    return {"safe": safe, "run_id": new_id, "output_basename": base,
            "output_dir": str(Path(paths["fits"]).parent),
            "op_errors": op_errors}


def submit_editor_export(settings: Settings, jm: JobManager, safe: str, run_id: int,
                         recipe_dict: dict, *, output_name: str | None = None,
                         tiff_mode: str = "linear") -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            return _apply_editor_to_run(
                lib, safe, run_id, recipe_dict,
                output_name=output_name, tiff_mode=tiff_mode,
                progress=_progress(jm, job),
            )
        finally:
            lib.close()

    return jm.submit("editor_export", body, target=safe)


def submit_pictures_archive(settings: Settings, jm: JobManager) -> Job:
    """Build one zip holding **every finished picture at full resolution**.

    The bulk download that already exists streams each target's stored *preview*
    (1024 px) — right for a phone album, not for printing. A target's
    native-resolution picture has no file on disk, so the full-size answer has to
    be rendered target by target, which is minutes of work on a real library:
    hence a job, with progress and cancel, rather than a request that would time
    out. The finished archive's path comes back in the job result; the download
    endpoint hands it over.

    Nothing the user owns is written: no new run, no new preview, no export
    marker — just the archive, under ``<data_root>/exports/``, replacing the
    previous one so a NAS never carries two.
    """
    def body(job: Job) -> dict[str, Any]:
        from webapp import picturesarchive

        picks = picturesarchive.plan_full_size_pictures(settings)
        if not picks:
            raise FileNotFoundError("no finished pictures to put in an archive")
        report = picturesarchive.build_full_size_archive(
            settings, picks,
            progress=_progress(jm, job),
            should_stop=job.cancel_requested,
        )
        if report.cancelled:
            # The truthy-dict cancellation sentinel `JobManager` looks for, so a
            # cancelled build isn't recorded as a finished one with no file.
            return {"cancelled": True, "path": "", "n_pictures": 0}
        return {
            "path": report.path,
            "filename": report.filename,
            "n_pictures": report.n_pictures,
            "n_full_res": report.n_full_res,
            "n_preview_only": report.n_preview_only,
            "size_bytes": report.size_bytes,
            "skipped": report.skipped,
        }

    return jm.submit("pictures_archive", body)


def submit_editor_png(settings: Settings, jm: JobManager, safe: str, run_id: int,
                      recipe_dict: dict) -> Job:
    """Render an editor recipe at full resolution and write a downloadable PNG
    (no new stack run created). The PNG path is returned in the job result."""
    def body(job: Job) -> dict[str, Any]:
        from datetime import datetime, timezone

        from seestack.io.project import Project
        from seestack.stack.output import write_full_res_png

        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            entry = lib.find_target(safe)
            if entry is None:
                raise FileNotFoundError(f"no target '{safe}'")
            proj = Project.open(lib.target_dir(entry))
            try:
                run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
                if run is None or not run.fits_path or not Path(run.fits_path).exists():
                    raise FileNotFoundError(f"run {run_id} has no FITS")
                op_errors: list[str] = []
                out, _recipe = _render_recipe_fullres(
                    run.fits_path, recipe_dict, _progress(jm, job),
                    errors=op_errors)
                from seestack.stack.output import safe_basename
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                png = (Path(proj.project_dir) / "output"
                       / f"{safe_basename(run.output_basename)}_edit_{ts}.png")
                write_full_res_png(png, out)
            finally:
                proj.close()
            return {"safe": safe, "run_id": run_id,
                    "png_path": str(png), "filename": png.name,
                    "op_errors": op_errors}
        finally:
            lib.close()

    return jm.submit("editor_png", body, target=safe)


def submit_editor_print(settings: Settings, jm: JobManager, safe: str, run_id: int,
                        recipe_dict: dict, *, size_name: str | None = None,
                        nameplate: bool = False) -> Job:
    """Render an editor recipe to a **print-ready** JPEG: fitted onto a standard
    paper size and tagged with the DPI it should be printed at, so a photo lab
    prints it at the size the app promised instead of guessing from the pixel
    count. The file path, the chosen size and its DPI come back in the job result.

    ``size_name`` picks one of :data:`seestack.printexport.PAPER_SIZES` by name;
    omit it (the beginner default) to take the **largest size this picture can
    fill sharply**. A name the picture can't print sharply is refused rather than
    quietly upscaled — a soft A3 is exactly the surprise this feature exists to
    prevent. When ``nameplate`` is set, the same acquisition footer the share
    export bakes on is drawn onto the print, at the print's own resolution."""
    def body(job: Job) -> dict[str, Any]:
        from datetime import UTC, datetime

        from seestack.io.project import Project
        from seestack.printexport import print_advice, print_options, render_print
        from seestack.stack.output import safe_basename, save_display_jpeg

        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            entry = lib.find_target(safe)
            if entry is None:
                raise FileNotFoundError(f"no target '{safe}'")
            proj = Project.open(lib.target_dir(entry))
            try:
                run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
                if run is None or not run.fits_path or not Path(run.fits_path).exists():
                    raise FileNotFoundError(f"run {run_id} has no FITS")
                op_errors: list[str] = []
                out, _recipe = _render_recipe_fullres(
                    run.fits_path, recipe_dict, _progress(jm, job),
                    errors=op_errors)
                h, w = out.shape[0], out.shape[1]
                options = print_options(w, h)
                if not options:
                    raise ValueError(
                        "This picture doesn't have enough detail for a sharp "
                        "print yet — another night or two of subs will get it "
                        "there.")
                if size_name:
                    option = next((o for o in options if o.name == size_name), None)
                    if option is None:
                        raise ValueError(
                            f"{size_name} would have to be enlarged from this "
                            f"picture and would print soft. "
                            f"{print_advice(options)}")
                else:
                    option = options[0]
                img = render_print(out, option)
                if nameplate:
                    plate = _nameplate_fields(
                        run.fits_path, entry, run, settings.site_lon)
                    if plate is not None:
                        from seestack.nameplate import draw_nameplate
                        img = draw_nameplate(img, plate)
                ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                slug = option.name.replace("×", "x").replace(" ", "")
                jpeg = (Path(proj.project_dir) / "output"
                        / f"{safe_basename(run.output_basename)}_print_{slug}_{ts}.jpg")
                jpeg.parent.mkdir(parents=True, exist_ok=True)
                # The DPI tag is the whole point: without it a lab sizes the print
                # from the pixel count alone, which is how a 20-inch enlargement of
                # a 6-inch picture happens.
                save_display_jpeg(img, jpeg, quality=95,
                                  dpi=(option.dpi, option.dpi))
            finally:
                proj.close()
            return {"safe": safe, "run_id": run_id,
                    "jpeg_path": str(jpeg), "filename": jpeg.name,
                    "size_name": option.name, "dpi": option.dpi,
                    "width_px": option.width_px, "height_px": option.height_px,
                    "advice": print_advice(options), "op_errors": op_errors}
        finally:
            lib.close()

    return jm.submit("editor_print", body, target=safe)


def submit_editor_share(settings: Settings, jm: JobManager, safe: str, run_id: int,
                        recipe_dict: dict, *, nameplate: bool = False) -> Job:
    """Render an editor recipe to a social-ready JPEG (long edge ≤ 2048 px) of the
    image exactly as shown — for posting/sharing rather than re-processing. The
    JPEG path + a copy-friendly caption blurb are returned in the job result.

    When ``nameplate`` is set, a tasteful acquisition footer (target, integration,
    date, gear — read from the run's own FITS provenance) is baked onto the shared
    image. Off by default, so the shared pixels are byte-for-byte as before unless
    the user opts in."""
    def body(job: Job) -> dict[str, Any]:
        from datetime import datetime, timezone

        from seestack.io.project import Project
        from seestack.nightrange import format_night_range
        from seestack.sharecard import share_blurb
        from seestack.stack.output import safe_basename, write_share_jpeg
        from webapp.capture_nights import capture_night_range

        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            entry = lib.find_target(safe)
            if entry is None:
                raise FileNotFoundError(f"no target '{safe}'")
            proj = Project.open(lib.target_dir(entry))
            try:
                run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
                if run is None or not run.fits_path or not Path(run.fits_path).exists():
                    raise FileNotFoundError(f"run {run_id} has no FITS")
                op_errors: list[str] = []
                out, _recipe = _render_recipe_fullres(
                    run.fits_path, recipe_dict, _progress(jm, job),
                    errors=op_errors)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                jpeg = (Path(proj.project_dir) / "output"
                        / f"{safe_basename(run.output_basename)}_share_{ts}.jpg")
                plate = _nameplate_fields(
                    run.fits_path, entry, run, settings.site_lon) if nameplate else None
                write_share_jpeg(jpeg, out, nameplate=plate)
                # The night it was shot — the one fact the copyable caption was
                # missing while Target, History, Gallery and the baked nameplate
                # all carried it. Read off the run's capture window, never off
                # `timestamp_utc` (which is when the *stack* ran).
                night_start, night_end = capture_night_range(
                    run.capture_start_utc, run.capture_end_utc, settings.site_lon)
                blurb = share_blurb(
                    entry.name, run.n_frames_used, run.total_exposure_s,
                    format_night_range(night_start, night_end))
            finally:
                proj.close()
            return {"safe": safe, "run_id": run_id,
                    "jpeg_path": str(jpeg), "filename": jpeg.name,
                    "blurb": blurb, "op_errors": op_errors}
        finally:
            lib.close()

    return jm.submit("editor_share", body, target=safe)


def submit_editor_batch(settings: Settings, jm: JobManager, items: list[dict],
                        recipe_dict: dict | None, *, output_name: str | None = None,
                        tiff_mode: str = "linear") -> Job:
    """Export several pictures in one cancellable job.

    ``recipe_dict`` is the one look to apply to every item ("apply this to N
    pictures"); pass **None** to give each item its *own* saved recipe instead,
    which is what "finish every edit I saved and never exported" needs. Same loop
    either way — one item's failure is isolated and reported, never sinking the
    batch, and a cancel stops before the next picture rather than mid-write.
    """
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        exported: list[dict] = []
        errors: dict[str, str] = {}
        cancelled = False
        total = len(items)
        try:
            for i, item in enumerate(items, start=1):
                if job.cancel_requested():
                    cancelled = True
                    break
                safe = str(item.get("safe"))
                try:
                    # Parse the per-item fields *inside* the try: a malformed item
                    # (missing / non-numeric run_id) must be isolated like any other
                    # per-item failure, not raise out of the loop and sink the whole
                    # job — which would also discard the records of the items already
                    # exported earlier in the batch (their new runs are on disk, but
                    # the job would report a bare 'error' with result=None).
                    rid = int(item.get("run_id"))
                    job.set_progress("batch", i, total, f"{safe} run {rid}")
                    jm.maybe_flush(job)
                    res = _apply_editor_to_run(
                        lib, safe, rid, recipe_dict,
                        output_name=output_name, tiff_mode=tiff_mode,
                        progress=lambda *a: None,  # per-item detail not surfaced
                    )
                    exported.append(res)
                except Exception as exc:  # noqa: BLE001 — one item shouldn't sink the batch
                    rid_repr = item.get("run_id")
                    log.warning("batch edit failed for %s/%s: %s", safe, rid_repr, exc)
                    errors[f"{safe}:{rid_repr}"] = str(exc)
        finally:
            lib.close()
        result: dict[str, Any] = {"exported": exported, "errors": errors}
        if cancelled:
            # Surface the cancel at the top level so JobManager._run classifies the
            # job 'cancelled' rather than a misleading 'done'; any items already
            # exported are kept in `exported`.
            result["cancelled"] = True
        return result

    return jm.submit("editor_batch", body)


def _channel_combine(
    lib: Library, target_safe: str, items: list[dict], *,
    output_name: str | None, weights: dict[str, float] | None, progress,
) -> dict[str, Any]:
    """Combine several mono stacks into one LRGB/RGB run, recorded under
    ``target_safe``. Each item: ``{safe, run_id, channel}`` (channel ∈ L/R/G/B)."""
    import json as _json
    from datetime import datetime, timezone

    import numpy as np

    from seestack.io.project import Project, StackRunRow
    from seestack.stack.channel_combine import combine_channels
    from seestack.stack.output import write_stack_outputs

    entry = lib.find_target(target_safe)
    if entry is None:
        raise FileNotFoundError(f"no target '{target_safe}'")

    channels: dict[str, np.ndarray] = {}
    wcs_text: str | None = None
    total = len(items)
    for i, item in enumerate(items, start=1):
        ch = str(item.get("channel", "")).upper()
        if ch not in ("L", "R", "G", "B"):
            raise ValueError(f"bad channel {item.get('channel')!r} (expected L/R/G/B)")
        if ch in channels:
            raise ValueError(f"channel {ch} assigned more than once")
        safe = str(item.get("safe"))
        rid = int(item.get("run_id"))
        progress("loading", i, total, f"{ch} ← {safe} run {rid}")
        src = lib.find_target(safe)
        if src is None:
            raise FileNotFoundError(f"no target '{safe}'")
        proj = Project.open(lib.target_dir(src))
        try:
            run = next((r for r in proj.iter_stack_runs() if r.id == rid), None)
            if run is None or not run.fits_path or not Path(run.fits_path).exists():
                raise FileNotFoundError(f"run {rid} in {safe} has no FITS")
            rgb, wcs = _load_full_rgb_wcs(run.fits_path)
        finally:
            proj.close()
        # Mono stacks have identical channels; luminance == that single channel.
        channels[ch] = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
        if wcs_text is None and wcs is not None:
            from seestack.io.wcs_io import wcs_to_text
            wcs_text = wcs_to_text(wcs)

    progress("combining", total, total)
    out = combine_channels(channels, weights=weights)

    dst = Project.open(lib.target_dir(entry))
    try:
        base = output_name or "lrgb"
        coverage = np.isfinite(out).all(axis=2).astype(np.float32)
        combo = "".join(c for c in ("L", "R", "G", "B") if c in channels)
        combine_meta = {
            "NCOMBINE": (len(items), "source stacks combined"),
            "STACKMTD": (f"channel-combine ({combo})", "how this image was produced"),
        }
        paths = write_stack_outputs(
            project_dir=dst.project_dir, rgb=out, coverage=coverage,
            wcs_text=wcs_text, out_basename=base, tiff_mode="linear",
            header_meta=combine_meta,
        )
        # Re-combining under an existing basename archives the prior output;
        # repoint its history row so it keeps serving its own image.
        if paths.get("archived"):
            dst.repoint_stack_runs(paths["archived"])
        new_id = dst.add_stack_run(StackRunRow(
            id=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            output_basename=base,
            fits_path=str(paths["fits"]), tiff_path=str(paths["tiff"]),
            preview_path=str(paths["preview"]),
            n_frames_used=len(items),
            canvas_h=out.shape[0], canvas_w=out.shape[1],
            coverage_min=1, coverage_max=1,
            options_json=_json.dumps({"channel_combine": items, "weights": weights or {}}),
            notes="channel combine",
            engine_version=APP_VERSION,
        ))
    finally:
        dst.close()
    lib.refresh_target_stats(target_safe)
    return {"safe": target_safe, "run_id": new_id, "output_basename": base,
            "channels": list(channels.keys())}


def submit_channel_combine(
    settings: Settings, jm: JobManager, target_safe: str, items: list[dict],
    *, output_name: str | None = None, weights: dict[str, float] | None = None,
) -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            return _channel_combine(
                lib, target_safe, items,
                output_name=output_name, weights=weights,
                progress=lambda *a: (job.set_progress(*a), jm.maybe_flush(job))[0],
            )
        finally:
            lib.close()

    return jm.submit("channel_combine", body, target=target_safe)


def _solved_accepted_count(proj: Any) -> int:
    return sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)


def _solved_accepted_unreadable(proj: Any) -> int:
    """How many of a target's solved+accepted subs have **no readable file now**.

    The DB row for a sub survives its file going away, so every count derived
    from the database alone (``_solved_accepted_count`` included) is a count of
    subs the app *believes* it can stack, not of subs it can actually read. The
    stacker already skips an unreadable frame silently and benignly
    (``readable_frame_path`` → ``None``), which is right for one stack but means
    a storage hiccup shows up only as a mysteriously thin result.

    One ``stat()`` per solved+accepted frame — the same check the worker makes
    per frame anyway — so callers keep it off the every-scan path and only ask
    when the answer is about to change a decision.
    """
    return count_unreadable_frames(
        f for f in proj.iter_frames(accepted_only=True) if f.wcs_json)


def _detect_mixed_pointings(proj: Any) -> MixedPointings | None:
    """The mixed-pointing verdict over a target's accepted+solved subs, or ``None``.

    Reads exactly the frames the stacker would combine (accepted, plate-solved)
    and clusters their pointings — see :mod:`seestack.stack.pointings`.
    """
    radecs = [
        (f.ra_center_deg, f.dec_center_deg)
        for f in proj.iter_frames(accepted_only=True)
        if f.wcs_json
    ]
    return detect_mixed_pointings(radecs)


def _mixed_pointing_check(lib: Library, safe: str) -> MixedPointings | None:
    """Open ``safe`` and return its mixed-pointing verdict (``None`` if single)."""
    proj = lib.open_target(safe)
    try:
        return _detect_mixed_pointings(proj)
    finally:
        proj.close()


def _mixed_pointing_summary(mixed: MixedPointings) -> dict[str, Any]:
    """A small JSON-safe blob describing a bimodal batch for a job summary."""
    return {
        "pointings": mixed.pointings,
        "majority": mixed.majority,
        "others": mixed.others,
        "separation_deg": round(mixed.separation_deg, 1),
    }


def _mixed_pointing_message(mixed: MixedPointings) -> str:
    """Plain-language reason shown when the guard skips a walk-away stack."""
    total = mixed.majority + mixed.others
    return (
        f"This batch looks like {mixed.pointings} different targets "
        f"(the largest pointing has {mixed.majority} of {total} solved subs, "
        f"~{round(mixed.separation_deg)}° apart). Stacking would combine only one "
        f"pointing and silently drop the rest, so it was skipped. Open the Frames "
        f"table and reject the odd-target frames (the Target page's "
        f'"Reject the odd-target frames" button does this in one click), then stack.'
    )


def _auto_stack_frame_count(lib: Library, safe: str) -> int | None:
    """Solved+accepted frame count to stack now, or ``None`` to skip the target.

    Stacks the first time a target has solvable data, and again only when more
    accepted+solved frames exist than the last stack covered — so repeated scans
    don't redundantly re-stack unchanged targets. Every successful stack (auto or
    manual — Stack form / Process target / reprocess) records the solved+accepted
    count it covered in ``AUTO_STACK_ATTEMPT_META_KEY`` (see ``_stack_target``), so
    a stack that legitimately dropped subs at alignment (``n_frames_used <
    solved+accepted``) isn't misread as "new work". That marker also breaks a
    crash-loop: it's written *before* an auto-stack, so a process-crashing stack
    can't re-trigger forever. The ``n_frames_used`` check below is the fallback for
    a pre-existing run that predates the marker (upgrade-safe).

    The fallback compares against the *largest* coverage any prior run reached, not
    the newest run's count: a channel-combine or editor-export run records a tiny
    ``n_frames_used`` (a handful of source stacks / a copied count) and is *not* a
    genuine full stack, so if it happens to be the newest run, comparing against its
    small count would wrongly permit a redundant re-stack of unchanged data. Taking
    the max over all runs can only make this guard more conservative — it never
    blocks a legitimate re-stack (a non-genuine run's count is ≤ the genuine one's).
    """
    proj = lib.open_target(safe)
    try:
        solved_accepted = _solved_accepted_count(proj)
        if solved_accepted == 0:
            return None
        prior_max = max(
            (r.n_frames_used for r in proj.iter_stack_runs()), default=None)
        if prior_max is not None and solved_accepted <= prior_max:
            return None
        attempted = proj.get_meta(AUTO_STACK_ATTEMPT_META_KEY)
        if attempted is not None:
            with contextlib.suppress(TypeError, ValueError):
                if int(attempted) >= solved_accepted:
                    # Already tried this data — *unless* that attempt was
                    # crippled by subs whose files were missing at the time and
                    # have since come back. The marker is a DB-level count, so
                    # without this it cannot tell "covered" from "attempted with
                    # half the night unreadable"; a target hit by a transient
                    # storage problem would keep its thin, noisy result as the
                    # newest picture until brand-new subs happened to push the
                    # count past the stale marker. Re-firing only when *fewer*
                    # frames are missing than last time keeps a genuine, ongoing
                    # outage from re-stacking on every single scan.
                    if not _readability_recovered(proj):
                        return None
        return solved_accepted
    finally:
        proj.close()


def _readability_recovered(proj: Any) -> bool:
    """Did subs that were unreadable at the last stack attempt come back?

    ``False`` for every healthy target and every install that predates the
    marker (no key ⇒ 0 missing last time ⇒ nothing to recover), so this only
    ever *adds* a retry to a target that was demonstrably short-changed. The
    ``stat()`` pass is reached only when the marker says frames were missing,
    which is rare by construction.
    """
    raw = proj.get_meta(AUTO_STACK_UNREADABLE_META_KEY)
    if not raw:
        return False
    try:
        last_unreadable = int(raw)
    except (TypeError, ValueError):
        return False
    if last_unreadable <= 0:
        return False
    return _solved_accepted_unreadable(proj) < last_unreadable


def _restore_missing_frames(lib: Library, safe: str) -> int:
    """Re-accept ``safe``'s set-aside-as-missing subs whose files are back.

    The automatic half of the "those subs are gone, carry on without them"
    action (``POST …/frames/set-missing-aside``): the owner never has to undo it
    themselves. Costs one indexed predicate on a target that never used the
    button — every healthy install — and refreshes the registry only when
    something actually changed.

    Best-effort: a locked or read-only project must not sink a scan over a
    housekeeping step, so a failure is logged and the scan carries on exactly as
    it would have.
    """
    try:
        proj = lib.open_target(safe)
        try:
            back = proj.restore_missing_frames()
        finally:
            proj.close()
        if back:
            lib.refresh_target_stats(safe)
        return len(back)
    except Exception as exc:  # noqa: BLE001 — housekeeping never sinks a scan
        log.warning("restoring missing-file subs failed for %s: %s", safe, exc)
        return 0


def _auto_stack_readability_hold(
        lib: Library, safe: str, offered: int, min_frames: int) -> dict[str, Any] | None:
    """Why a walk-away stack of ``safe`` should be held back right now, or ``None``.

    The trigger above counts subs in the *database*; this is the only place that
    asks whether their files are actually on disk. A chunk of a night going
    briefly unreadable — a share that flapped, a drive unmounted, a folder moved
    or archived mid-session — is invisible to every DB-level count, so the stack
    fires, silently drops what it cannot read (``readable_frame_path`` → ``None``
    inside ``prepare``), and **publishes the thinner, noisier result as the
    target's newest picture**. That is the walk-away path quietly making the
    owner's image worse, which is the worst thing this app can do.

    So: hold back when stacking *now* would produce something materially worse
    than what the user already has — either below the same minimum-frames floor
    the thin guard uses, or thinner than the best stack this target has already
    produced. The caller holds without marking the attempt, exactly like
    ``held_thin``, so the moment the files come back the next scan stacks it.

    Deliberately gated on ``unreadable > 0``: when every sub's file is present
    (every healthy install, always) this returns ``None`` before comparing
    anything, so the guard cannot change the behaviour of a target that has no
    storage problem. It also never holds a target's *first* stack for lack of a
    better predecessor — there is no good picture to protect there, the loss may
    be permanent, and refusing to stack at all would be the bigger harm.
    """
    proj = lib.open_target(safe)
    try:
        unreadable = _solved_accepted_unreadable(proj)
        if unreadable <= 0:
            return None
        readable = max(0, offered - unreadable)
        prior_max = max(
            (r.n_frames_used for r in proj.iter_stack_runs()), default=None)
    finally:
        proj.close()
    if readable < min_frames:
        reason = "too few of its subs are readable right now"
    elif prior_max is not None and readable < prior_max:
        reason = "that would be a thinner stack than this target already has"
    else:
        return None
    return {
        "target": safe, "offered": offered, "readable": readable,
        "unreadable": unreadable, "prior_best": prior_max, "reason": reason,
    }


def _mark_auto_stack_attempt(lib: Library, safe: str, frame_count: int) -> None:
    proj = lib.open_target(safe)
    try:
        proj.set_meta(AUTO_STACK_ATTEMPT_META_KEY, str(frame_count))
    finally:
        proj.close()


def _clear_auto_stack_attempt(lib: Library, safe: str) -> None:
    """Drop the crash-loop marker so the next scan may retry the target.

    Called when an auto-stack raised a *recoverable* exception (the process
    survived): the marker was written before the stack purely to break a
    process-*crash* loop (an OOM kills the worker before it can clean up, so the
    guard must already be persisted). A survivable failure — a transient I/O
    error reading a calibration master off a flapping mount, a momentary lock —
    reaches the handler, so leaving the marker set would wrongly disable
    auto-stack for this target *forever* (until brand-new frames arrive), silently
    breaking the walk-away promise. Clearing it lets the next scan try again; a
    genuinely reproducible failure simply re-fails fast and is re-logged each
    scan, which is the acceptable cost of not stranding a transient one."""
    proj = lib.open_target(safe)
    try:
        proj.delete_meta(AUTO_STACK_ATTEMPT_META_KEY)
    finally:
        proj.close()


def _calib_fingerprint(bound: dict[str, Any]) -> str:
    """A stable fingerprint of a confident-master binding, used as the
    once-per-master-set marker for the calibration recheck. Only the master
    *path* keys matter (``scale_dark_to_light`` is a derived flag), so a re-run
    that binds the same masters produces the same string."""
    return "|".join(
        f"{k}={bound[k]}" for k in sorted(bound)
        if k.endswith("_path") and bound.get(k)
    )


def _auto_stack_calibration_recheck(
    settings: Settings, lib: Library, safe: str) -> tuple[int, str] | None:
    """``(frame_count, fingerprint)`` to *re-stack* an already-stacked target
    because a confident calibration master has newly become bindable for it — or
    ``None`` to skip.

    Closes the beginner loop the frame-count trigger can't: the app's own "How's
    my stack?" card advises "add darks", the user builds/drops a master and
    re-scans, but **no new subs arrived**, so :func:`_auto_stack_frame_count`
    never re-fires and the noisy *uncalibrated* result stands. This re-triggers a
    single restack (which the walk-away chain then auto-binds + calibrates) when
    **all** hold:

    * ``auto_bind_calibration`` is on — otherwise the restack couldn't apply the
      master and the retrigger would be pointless churn (``auto_stack`` is already
      checked by the caller). Both default off, so a default install is unchanged.
    * the target has at least one genuine stack run and **none** of its runs was
      calibrated (empty ``calstat``) — i.e. it has never had darks/flats applied;
    * a confident master now auto-binds for the target's acquisition params (the
      *same* confidence gates the walk-away path trusts, via
      :func:`_confident_master_binding`);
    * that master set's fingerprint differs from the last recheck's marker, so a
      given newly-available master set fires **once**, never every scan.

    Returns the current solved+accepted count (so the caller stacks exactly the
    frames it would have) and the fingerprint the caller persists before stacking.
    """
    if not settings.auto_bind_calibration:
        return None
    proj = lib.open_target(safe)
    try:
        solved_accepted = _solved_accepted_count(proj)
        if solved_accepted == 0:
            return None
        runs = list(proj.iter_stack_runs())
        if not runs:
            return None  # never stacked — the frame-count path owns first stacks
        if any(bool(r.calstat and r.calstat.strip()) for r in runs):
            return None  # already calibrated at some point — not our loop to close
        try:
            bound = _confident_master_binding(settings, proj)
        except Exception as exc:  # noqa: BLE001 — detection must never sink the scan
            log.warning("calibration recheck bind failed for %s: %s", safe, exc)
            return None
        if not any(bound.get(k) for k in
                   ("dark_path", "flat_path", "flat_dark_path", "bias_path")):
            return None  # no confident master available — nothing to apply
        fingerprint = _calib_fingerprint(bound)
        if proj.get_meta(AUTO_STACK_CALIB_META_KEY) == fingerprint:
            return None  # already re-stacked for this exact master set
        return solved_accepted, fingerprint
    finally:
        proj.close()


def _mark_auto_stack_calib_retrigger(lib: Library, safe: str, fingerprint: str) -> None:
    proj = lib.open_target(safe)
    try:
        proj.set_meta(AUTO_STACK_CALIB_META_KEY, fingerprint)
    finally:
        proj.close()


def _clear_auto_stack_calib_retrigger(lib: Library, safe: str) -> None:
    """Drop the calibration-recheck marker so the next scan may retry the restack.

    The marker is written *before* the calibration re-stack purely to break a
    process-*crash* loop on the recheck path (which deliberately bypasses the
    frame-count crash guard). A *survivable* failure or a user cancel reaches the
    loop's handlers, so — exactly as :func:`_clear_auto_stack_attempt` does for the
    frame-count marker — clearing it here avoids stranding a transient failure; a
    genuinely reproducible one simply re-fails fast and is re-logged each scan."""
    proj = lib.open_target(safe)
    try:
        proj.delete_meta(AUTO_STACK_CALIB_META_KEY)
    finally:
        proj.close()


def _auto_stack_degraded_recheck(
        lib: Library, safe: str) -> tuple[int, str, dict[str, Any]] | None:
    """``(frame_count, fingerprint, detail)`` to *re-stack* a target whose newest
    picture came out materially thinner than one it already made — or ``None``.

    The readability preflight (:func:`_auto_stack_readability_hold`) stops the
    walk-away path publishing a picture made thin by subs it couldn't read, and
    :func:`_readability_recovered` retries an attempt that *recorded* how many
    were missing. Neither can help a target that was **already** left sitting on
    a degraded picture — the owner's live install, whose three walk-away stacks of
    one growing night ran 787 → 575 → **271** frames before the guard existed.
    There, ``solved_accepted`` is back to 787 and the best run used 787, so
    :func:`_auto_stack_frame_count` correctly answers "already covered" and the
    271-frame result stands as the newest picture until a fresh clear night
    happens to push the count higher.

    So: when the data is demonstrably all there and the newest picture is
    demonstrably worse than one this target has already produced, re-stack it
    **once**. All of these must hold:

    * the target has ≥2 *genuine* stack runs (editor-export and channel-combine
      runs are recorded in ``stack_runs`` too, with a tiny ``n_frames_used`` that
      would read as a collapse — the trap the ``prior_max`` docstring names);
    * its newest genuine run is materially thinner than its best
      (``AUTO_STACK_DEGRADED_MAX_RATIO`` *and* ``AUTO_STACK_DEGRADED_MIN_LOSS``,
      so an ordinary handful of align drops never qualifies);
    * **every** solved+accepted sub is readable right now, so the re-stack can
      actually do better rather than reproducing the same thin result;
    * the accepted+solved population is still at least as large as that best run
      — this is what separates "a storage hiccup ate half the night" from "the
      user deliberately rejected half the subs and re-stacked", which is a
      legitimately thinner newest picture and must never be second-guessed;
    * the ``best:solved`` fingerprint differs from the last heal's marker, so a
      given situation fires once. Deliberately *not* keyed on the thin count: a
      heal that comes out thin again (for some reason of its own) must not shift
      the fingerprint and re-fire on the next scan.

    Reached only when the frame-count and calibration triggers both declined, and
    the ``stat()`` pass is the last check, so a healthy, up-to-date target pays
    nothing but a couple of DB reads.
    """
    proj = lib.open_target(safe)
    try:
        solved_accepted = _solved_accepted_count(proj)
        if solved_accepted == 0:
            return None
        genuine = [r for r in proj.iter_stack_runs()  # newest first
                   if _stack_options_from_run_json(r.options_json) is not None]
        if len(genuine) < 2:
            return None  # nothing better to compare the newest picture against
        newest_n = genuine[0].n_frames_used
        best_n = max(r.n_frames_used for r in genuine)
        if newest_n >= best_n * AUTO_STACK_DEGRADED_MAX_RATIO:
            return None
        if best_n - newest_n < AUTO_STACK_DEGRADED_MIN_LOSS:
            return None
        if solved_accepted < best_n:
            return None  # a legitimately smaller population — not a degradation
        fingerprint = f"{best_n}:{solved_accepted}"
        if proj.get_meta(AUTO_STACK_DEGRADED_META_KEY) == fingerprint:
            return None  # already healed this exact situation
        if _solved_accepted_unreadable(proj) > 0:
            # Still mid-outage: the readability preflight owns this case (it
            # holds the target back without marking anything), and re-stacking
            # now would just reproduce the thin picture.
            return None
    finally:
        proj.close()
    detail = {"target": safe, "frames": solved_accepted,
              "newest": newest_n, "best": best_n}
    return solved_accepted, fingerprint, detail


def _mark_auto_stack_degraded_heal(lib: Library, safe: str, fingerprint: str) -> None:
    proj = lib.open_target(safe)
    try:
        proj.set_meta(AUTO_STACK_DEGRADED_META_KEY, fingerprint)
    finally:
        proj.close()


def _clear_auto_stack_degraded_heal(lib: Library, safe: str) -> None:
    """Drop the degraded-heal marker so the next scan may retry the heal.

    Same reasoning as :func:`_clear_auto_stack_calib_retrigger`: the marker is
    written *before* the heal purely to break a process-*crash* loop, so a
    survivable failure or a user cancel — both of which reach the scan loop's
    handlers — must not strand the target on its degraded picture forever."""
    proj = lib.open_target(safe)
    try:
        proj.delete_meta(AUTO_STACK_DEGRADED_META_KEY)
    finally:
        proj.close()


def _reprocess_output_basename(existing: set[str], version: str) -> str:
    """A fresh, non-colliding output basename for a reprocessed run.

    Base is ``master_v<version>`` (self-documenting: the build that produced it),
    sanitised to safe filename chars. If a run already carries that basename (e.g.
    the user reprocessed twice on the same version), a ``_2``/``_3``/… suffix is
    appended so the new run never archives/overwrites the earlier one — the
    reprocess feature's non-destructive guarantee holds even in that edge case.

    ``existing`` is the set of the target's current ``output_basename`` values.
    """
    from seestack.stack.output import _sanitize_basename

    base = _sanitize_basename(f"master_v{version}")
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def _confident_master_binding(settings: Settings, proj: Any) -> dict[str, Any]:
    """The confidently-matching library master dark/flat/bias paths for a target's
    accepted frames — the ``StackOptions`` calibration keys an *unattended* stack
    would auto-bind — or ``{}`` when none is confident (leave it uncalibrated).

    Pure/read-only: it consults the library's masters against the target's own
    acquisition params (median exposure/gain/temp, modal frame dims) via
    :func:`calibration.auto_bind_master_paths` and never mutates the project. Shared
    by :func:`_auto_bind_calibration` (which binds it into a run's options) and
    :func:`_auto_stack_calibration_recheck` (which uses it to decide whether a
    now-available master should re-trigger a previously-uncalibrated target)."""
    from webapp import calibration

    frames = list(proj.iter_frames(accepted_only=True))
    if not frames:
        return {}

    def _med(vals: list[Any]) -> float | None:
        xs = sorted(v for v in vals if v is not None)
        if not xs:
            return None
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0

    masters = calibration.list_masters(settings.resolved_library_root)
    return calibration.auto_bind_master_paths(
        settings.resolved_library_root, masters,
        exposure_s=_med([f.exposure_s for f in frames]),
        gain=_med([f.gain for f in frames]),
        sensor_temp_c=_med([f.sensor_temp_c for f in frames]),
        width_px=calibration.modal_dim([f.width_px for f in frames]),
        height_px=calibration.modal_dim([f.height_px for f in frames]),
        bayer_pattern=calibration.modal_bayer([f.bayer_pattern for f in frames]),
    )


#: The per-target "Save as defaults" calibration picks (see
#: ``routers/stack.py::_MASTER_ID_KEYS``) mapped to the ``StackOptions`` path key
#: each resolves to, plus a human word for the log line. They are *ids*, not
#: paths: the file is always resolved server-side from the library's own master
#: registry, so a saved default can never smuggle a raw filesystem path into a run.
#: "not read yet" for a lazily-resolved value whose legitimate answer is ``None``
#: (the subs' colour-filter phase, which is unknown on a library that never
#: recorded one) — so the read happens at most once either way.
_UNREAD = object()

_SAVED_MASTER_BINDINGS = (
    ("dark_master_id", "dark_path", "dark"),
    ("flat_master_id", "flat_path", "flat"),
    ("flat_dark_master_id", "flat_dark_path", "flat-dark"),
    ("bias_master_id", "bias_path", "bias"),
)

#: Project-meta key prefix (``…:<run_id>``) under which a run records the saved
#: calibration picks its unattended stack had to *skip*, as a JSON list of
#: plain-language sentences. The skip itself is deliberately fail-soft (see
#: :func:`_apply_saved_calibration_masters`), but the user still ends up with a
#: less-calibrated picture than they asked for and a beginner won't read the
#: server log — so History reads this back and says why. Additive: an older run
#: simply has no such key and the History line stays exactly as it was.
CALIBRATION_SKIPPED_META_PREFIX = "calibration_skipped:"

#: Project-meta key prefix (``calibration_warnings:<run_id>``) holding a JSON list
#: of plain-language sentences about a master that *was* applied but doesn't match
#: the lights — a dark shot at another exposure or a very different sensor
#: temperature, which over/under-subtracts its pedestal on every frame. The engine
#: measures these (``CalibrationMasters.calibration_warnings``) and used to only
#: log them; stamped here so History can say it out loud beside the picture.
#: Additive: an older run has no such key and reads back as no warnings.
CALIBRATION_WARNINGS_META_PREFIX = "calibration_warnings:"


def _apply_saved_calibration_masters(
    settings: Settings, proj: Any, opts_dict: dict[str, Any],
    master_ids: dict[str, Any],
) -> list[str]:
    """Bind the calibration masters the user *explicitly chose and saved* for this
    target to an unattended stack (mutates ``opts_dict``).

    "Save as defaults" on the Stack form persists the four master picks alongside
    the engine options, and the toast promises they "drive auto-stacking for this
    target" — but the walk-away path (watcher auto-stack / Process target) used to
    drop them, because they aren't ``StackOptions`` fields and only the separate,
    off-by-default ``auto_bind_calibration`` applied any calibration at all (and
    that *auto-picks* masters, ignoring the user's choice). So a beginner who chose
    their darks once still got uncalibrated walk-away stacks. This resolves the
    saved ids to server-side paths — the same ``calibration`` registry lookup the
    manual Stack form's trigger uses — so an explicit pick wins.

    Runs *before* :func:`_auto_bind_calibration`, which self-skips once any
    calibration path is set, so the user's choice beats the auto-picker.

    Deliberately fail-soft, per slot: a master that was deleted since it was saved
    (or whose file has gone) is skipped with a warning rather than failing the whole
    unattended run, and a master whose *recorded dimensions* provably disagree with
    the target's subs is skipped too — binding it would make ``run_stack`` hard-fail
    at ``CalibrationMasters.validate``, turning a walk-away stack into an error. The
    dimension check only refuses on a **positive** conflict (both sides known and
    different); when either side never recorded its size we trust the explicit pick,
    exactly as the manual Stack form does.

    Returns the plain-language reasons for any picks it skipped (empty when every
    saved pick bound, or when there was nothing to bind), so the caller can stamp
    them on the run record and History can explain the uncalibrated result instead
    of leaving the reason in the server log.
    """
    from webapp import calibration

    if any(opts_dict.get(k) for _, k, _ in _SAVED_MASTER_BINDINGS):
        return []  # a path is already set (reused run options) — leave it alone

    dims: tuple[int | None, int | None] | None = None
    cfa: str | None | object = _UNREAD

    def _sub_dims() -> tuple[int | None, int | None]:
        """The subs' modal raw dimensions, read once and only when needed."""
        nonlocal dims
        if dims is None:
            frames = list(proj.iter_frames(accepted_only=True))
            dims = (calibration.modal_dim([f.width_px for f in frames]),
                    calibration.modal_dim([f.height_px for f in frames]))
        return dims

    def _sub_bayer() -> str | None:
        """The subs' modal colour-filter phase, read once and only when needed."""
        nonlocal cfa
        if cfa is _UNREAD:
            frames = list(proj.iter_frames(accepted_only=True))
            cfa = calibration.modal_bayer([f.bayer_pattern for f in frames])
        return cfa  # type: ignore[return-value]

    def _dims_conflict(entry: dict[str, Any]) -> bool:
        return calibration.dims_conflict(entry, *_sub_dims())

    bound: list[str] = []
    skipped: list[str] = []
    for id_key, path_key, word in _SAVED_MASTER_BINDINGS:
        mid = master_ids.get(id_key)
        if mid in (None, "", "none"):
            continue
        try:
            entry = calibration.get_master(settings.resolved_library_root, int(mid))
            path = calibration.master_path(settings.resolved_library_root, int(mid))
        except (TypeError, ValueError, OSError) as exc:  # noqa: PERF203
            log.warning("saved %s master %r for %s is unusable: %s",
                        word, mid, opts_dict.get("output_name", "?"), exc)
            skipped.append(_skip_sentence(
                word, "it couldn't be read from your calibration library"))
            continue
        if entry is None or path is None:
            log.warning("saved %s master %r for %s no longer exists — "
                        "stacking without it", word, mid,
                        opts_dict.get("output_name", "?"))
            skipped.append(_skip_sentence(
                word, "it's no longer in your calibration library"))
            continue
        if _dims_conflict(entry):
            log.warning("saved %s master %r is %sx%s, but this target's subs are "
                        "%sx%s — skipping it rather than failing the stack", word,
                        mid, entry.get("width_px"), entry.get("height_px"),
                        *_sub_dims())
            skipped.append(_skip_sentence(word, _dims_reason(entry, _sub_dims())))
            continue
        # Same fail-soft reasoning, one axis over: a saved *flat* built on another
        # colour-filter phase is refused by ``CalibrationMasters.validate`` (it
        # would divide red photosites by a green correction and tint every frame),
        # so binding it would turn a walk-away stack into an error. Flats only —
        # a dark or bias corrects each physical pixel, so its phase is irrelevant
        # and the engine merely mentions it.
        if path_key == "flat_path" and calibration.bayer_conflict(
                entry, _sub_bayer()):
            log.warning("saved %s master %r has a %s colour-filter layout, but "
                        "this target's subs are %s — skipping it rather than "
                        "failing the stack", word, mid,
                        entry.get("bayer_pattern"), _sub_bayer())
            skipped.append(_skip_sentence(word, _bayer_reason(entry, _sub_bayer())))
            continue
        opts_dict[path_key] = str(path)
        bound.append(word)
    if bound:
        log.info("applied saved calibration masters: %s", ", ".join(bound))
    elif opts_dict.get("scale_dark_to_light"):
        # No saved dark survived, so a saved ``scale_dark_to_light`` would ask the
        # engine to exposure-scale a dark that isn't there. Mirror
        # ``_auto_bind_calibration``'s handling of the same stray flag.
        opts_dict.pop("scale_dark_to_light", None)
    return skipped


def _skip_sentence(word: str, reason: str) -> str:
    """One plain-language sentence for a saved calibration pick that was skipped.

    Written for a beginner reading the History Info panel, not for the log: it
    names *which* pick was dropped and why, in the second person, so the reader
    knows their explicit choice didn't silently apply."""
    return f"Your saved master {word} wasn't used: {reason}."


def _dims_reason(entry: dict[str, Any],
                 sub_dims: tuple[int | None, int | None]) -> str:
    """The size-mismatch half of :func:`_skip_sentence` (both sides are known —
    :func:`calibration.dims_conflict` only fires on a positive conflict)."""
    return (f"it's {entry.get('width_px')}×{entry.get('height_px')} pixels, but "
            f"this target's subs are {sub_dims[0]}×{sub_dims[1]}")


def _bayer_reason(entry: dict[str, Any], sub_bayer: str | None) -> str:
    """The colour-filter-layout half of :func:`_skip_sentence` (both sides are
    known — :func:`calibration.bayer_conflict` only fires on a positive
    conflict)."""
    return (f"it was built on a {entry.get('bayer_pattern')} colour-filter "
            f"layout, but this target's subs are {sub_bayer} — a different "
            f"camera or readout mode, so dividing by it would tint every frame")


def _auto_bind_calibration(settings: Settings, proj: Any, opts_dict: dict[str, Any]) -> None:
    """Best-effort: bind confidently-matching library master darks/flats/bias to
    an unattended stack when it has no calibration chosen (mutates ``opts_dict``).

    Skips entirely when the merged options already carry any calibration path (so
    a per-target default or reused run's masters win), and never raises into the
    stack — an unresolvable master or a bad frame set just leaves it uncalibrated,
    exactly as today. The applied masters flow through the normal stack path, so
    the run's ``CALSTAT`` provenance records what was calibrated."""
    if any(opts_dict.get(k) for k in
           ("dark_path", "flat_path", "flat_dark_path", "bias_path")):
        return
    try:
        bound = _confident_master_binding(settings, proj)
    except Exception as exc:  # noqa: BLE001 — calibration binding is a best-effort nicety
        log.warning("auto-bind calibration failed for %s: %s",
                    opts_dict.get("output_name", "?"), exc)
        return
    if bound:
        opts_dict.update(bound)
        log.info("auto-bound calibration masters: %s", ", ".join(sorted(bound)))
    # A stray ``scale_dark_to_light`` left in the global defaults is only
    # meaningful when auto-bind itself bound a bias-scaled dark; otherwise it
    # asks the engine to exposure-scale a dark with no bias to scale against —
    # a no-op that misrepresents the run's calibration intent (and, if a plain
    # matched-exposure dark was just bound, contradicts it). This function only
    # runs when no calibration path was pre-set, so any flag here is a leftover
    # from ``default_stack_options`` (whose paths are stripped) — drop it unless
    # we set it ourselves.
    if opts_dict.get("scale_dark_to_light") and not bound.get("scale_dark_to_light"):
        opts_dict.pop("scale_dark_to_light", None)


def _stack_target(
    settings: Settings,
    jm: JobManager,
    job: Job,
    lib: Library,
    safe: str,
    *,
    options: dict[str, Any] | None = None,
    output_name: str | None = None,
    auto_bind_calibration: bool = False,
    auto: bool = False,
) -> dict[str, Any]:
    """Run a stack for one target and record it. Returns a small summary.

    ``output_name``, when given, overrides the output basename *after* the option
    merge — used by reprocess-all to force a fresh, non-colliding name so a
    restack doesn't archive/overwrite the target's existing output.

    ``auto_bind_calibration`` (set by the *unattended* chains — watcher
    auto-stack, Process target, reprocess-all — from ``settings.auto_bind_calibration``)
    binds the library's best confidently-matching master dark/flat/bias when the
    merged options carry no explicit calibration, so a walk-away stack is still
    calibrated. The interactive Stack form never sets it — it honours exactly what
    the user picked (or deliberately left blank).

    ``auto`` (set by the walk-away chains — watcher auto-stack and Process target —
    where the user made *no* stacking choices) turns on the engine's
    ``StackOptions.auto_reject`` when the merged options carry no explicit rejection
    preference. That resolves (per ``_resolve_auto_reject``) to order-statistic
    min/max on a small stack — the only method that removes a lone satellite/plane
    trail below ~11 frames, which plain κ-σ is mathematically blind to — and to
    weight-respecting κ-σ once the stack is large enough for κ-σ to bite, all with
    zero user decisions. It is applied **only** when the user has expressed no
    rejection choice (no ``auto_reject``/``sigma_clip``/``min_max_reject`` key in the
    merged options), so a saved per-target default or the manual Stack form is always
    honoured verbatim; reprocess-all likewise reuses the prior run's options
    untouched. Off (the default) leaves the built options byte-for-byte unchanged.

    ``auto`` also turns on ``StackOptions.quality_weighted`` when the merged options
    carry no explicit preference, for the same reason and with the same guard: a
    walk-away stack spanning many nights of different seeing, haze and moon would
    otherwise trust a soft or cloud-thinned sub exactly as much as a sharp one.
    ``compute_frame_weights`` derives the weights from QC metrics that are already
    measured, gives a neutral 1.0 to any metric it couldn't measure and floors every
    weight at 0.1, so it can only demote a genuinely worse sub and never drops one.
    The engine default stays **False** — a manual stack, a stored config and every
    existing run record are untouched; this only picks a better default for a user
    who clicked "just do it".

    ``auto`` finally turns on ``StackOptions.drizzle_reject`` when the run drizzles
    and the merged options express no preference. Drizzle accumulates in one shot,
    so ``auto_reject`` — and every method it resolves to — is a **no-op** there;
    without this a drizzled walk-away stack combined with no outlier rejection at
    all, keeping every satellite, plane trail and cosmic ray that slipped past
    frame-level QC. Drizzle's own two-pass rejection is the equivalent, and this is
    the same "the user chose nothing" guard the two above use. Whether that pass is
    *affordable* is settled later, in the engine: it holds ~7 canvas planes against
    the single pass's 4, and only ``run_stack`` knows the real (for a mosaic, union)
    canvas it would allocate them on. An auto-enabled rejection the memory budget
    can't take is quietly skipped rather than refusing the run — see
    ``stacker._afford_drizzle_reject``. A run somebody is *watching* still refuses
    loudly, because that user can act on the advice.

    ``auto`` finally sets ``StackOptions.unattended`` — the plain "nobody is
    watching this run" posture, written after every option merge so it can't be
    spoofed by a saved default or a POST body. It is not a preference and changes
    no picture by itself; the engine reads it wherever the right answer to an
    over-budget run depends on whether there is a human there to act on the fix.
    It replaces ``auto_reject`` in that role, which only *looked* like the same
    question: ``get_stack_defaults`` seeds ``auto_reject=True`` into the manual
    Stack form for a never-configured target, so a watching beginner sent it too.
    """
    from seestack.stack.stacker import run_stack

    # Option precedence:
    #   global settings.default_stack_options
    #     → per-target "Save as defaults" (used by auto-stack)
    #       → explicit options passed for this run (manual stack from the form)
    # Never let a calibration master *path* in the global defaults reach the
    # stacker: those are resolved server-side from master ids and applied later
    # (explicit run options / auto-bind), so a raw path in default_stack_options
    # would only be a leaked client value. Strip the base defensively.
    opts_dict = strip_non_form_keys(settings.default_stack_options)
    proj = lib.open_target(safe)
    # The calibration-master *ids* the user saved for this target, if any. Only
    # ever taken from the per-target "Save as defaults" blob (never the global
    # config), so a crafted settings PUT can't reach the calibration registry.
    saved_master_ids: dict[str, Any] = {}
    try:
        if options is None:
            # ``parse_saved_stack_defaults`` is the shared reader for this row
            # (webapp/walkaway.py): a malformed or non-dict blob degrades to "no
            # saved defaults" rather than failing the walk-away job, and the
            # read-only surfaces that have to *say* what this chain will do use
            # the same reader so they cannot answer for a different blob.
            saved = parse_saved_stack_defaults(proj.get_meta(STACK_DEFAULTS_META_KEY))
            opts_dict.update(saved)
            saved_master_ids = {
                k: saved[k] for k, _, _ in _SAVED_MASTER_BINDINGS
                if saved.get(k) is not None
            }
        else:
            opts_dict.update(options)
        if output_name is not None:
            opts_dict["output_name"] = output_name
        if auto:
            # Walk-away stack: fill in the rejection choices this user never made
            # — ``auto_reject`` when no method was picked at all, and
            # ``drizzle_reject`` on a drizzled run (``auto_reject`` is a no-op
            # under drizzle, which has its own two-pass rejection and which
            # nothing ever turned on, so a drizzled walk-away stack used to
            # combine completely unfiltered). Both are gated on the merged
            # options expressing no preference, so a saved per-target default and
            # the manual Stack form are honoured verbatim. The definition lives in
            # ``webapp/walkaway.py`` because the Target page has to be able to say
            # what this chain will do *before* the night, and a second copy of the
            # rule is how the two would come to disagree.
            # ``auto_reject_on_unattended`` (opt-in, off by default) additionally
            # lets the chain pick the method for a target whose saved defaults
            # name one — a method saved once is a decision made at one depth and
            # then applied to every night after it. Off ⇒ this call is exactly
            # what it has always been.
            apply_unattended_rejection(
                opts_dict,
                override_saved_choice=settings.auto_reject_on_unattended,
            )
        if (auto and "quality_weighted" not in opts_dict
                and not (opts_dict.get("min_max_reject") and not opts_dict.get("drizzle"))):
            # Same walk-away reasoning: with no user choice, weight each sub by the
            # QC metrics we already measured so a soft / hazy night doesn't pull the
            # stack down as hard as a sharp one. Missing metrics fall back to a
            # neutral 1.0 and the weight floor is 0.1, so nothing is ever dropped.
            # Only when nothing explicit was set — a saved per-target default and
            # the manual Stack form (either way) are honoured verbatim.
            #
            # …and not when the user's own saved defaults already ask for min/max
            # rejection on the standard path, because that combine works by *rank*
            # and ignores per-frame weights entirely. Turning weighting on there
            # would change nothing in the picture but would make the run stamp
            # WGTSKIP with ``auto=False`` — which History renders as "Quality
            # weighting was on, but … use sigma clipping instead", advice to undo a
            # setting the user never chose. (The auto_reject branch above resolving
            # itself to min/max on a small stack is a different case and stays: it
            # stamps ``auto=True``, whose wording correctly says weighting starts
            # counting once there are more subs.) Drizzle is exempt — it honours
            # per-frame weights and runs its own rejection.
            opts_dict["quality_weighted"] = True
        # The posture, written **last** so nothing can spoof it: a stale saved
        # per-target default, a crafted POST body or a reused prior-run option
        # blob may all carry ``unattended``, and only this function knows whether
        # anybody is actually watching. ``auto`` is exactly that question — it is
        # set by the watcher auto-stack and "Process target" and by nothing else,
        # so the manual Stack form and reprocess-all resolve to False. The engine
        # reads it where "refuse loudly with a fix" and "degrade quietly and still
        # make a picture" are the two right answers to the same over-budget run
        # (see ``stacker._afford_drizzle_reject``). Always written, so the value is
        # a property of *this* run rather than of whatever was merged into it.
        opts_dict["unattended"] = bool(auto)
        calibration_skipped: list[str] = []
        if saved_master_ids:
            # The user's own "Save as defaults" calibration picks win over the
            # auto-picker below (which self-skips once a path is set).
            calibration_skipped = _apply_saved_calibration_masters(
                settings, proj, opts_dict, saved_master_ids)
        if auto_bind_calibration:
            _auto_bind_calibration(settings, proj, opts_dict)
        if opts_dict.get("max_workers") is None and settings.cpu_workers:
            opts_dict["max_workers"] = settings.cpu_workers
        opts = coerce_stack_options(opts_dict)

        result = run_stack(
            proj, opts,
            progress=lambda phase, done, total: (
                job.set_progress(f"stack:{phase}", done, total), jm.maybe_flush(job)
            )[0],
            cancel=job.cancel_requested,
            memory_budget_gb=settings.max_stack_memory_gb,
            app_version=APP_VERSION,
        )
        if not result.cancelled:
            # Record how many solved+accepted subs this stack covered, so the
            # watcher auto-stack won't redundantly re-stack this target until
            # genuinely *new* solved frames arrive. Keyed on the solved+accepted
            # count — not the align-reduced ``n_frames_used`` — because a normal
            # stack that drops subs at alignment (mosaics, mixed sessions, a few
            # bad solves) has ``n_frames_used < solved+accepted``, which the
            # ``n_frames_used`` guard alone misreads as "new work" and re-stacks.
            # Reuses the auto-stack crash-loop marker key so the manual Stack-form
            # / Process-target / reprocess paths (which otherwise write no marker)
            # are covered too; a user cancel writes nothing (the outer auto-stack
            # handler clears the pre-stack marker for that survivable case).
            proj.set_meta(AUTO_STACK_ATTEMPT_META_KEY,
                          str(_solved_accepted_count(proj)))
            # …and alongside it, how many of those subs had no file on disk for
            # this run. That count is what turns the marker from "covered" into
            # "attempted, but N subs were missing at the time" — so if the files
            # come back, the trigger knows to try again instead of leaving the
            # thin result standing (see AUTO_STACK_UNREADABLE_META_KEY). A run
            # where everything was readable *deletes* the key rather than
            # writing "0", so a healthy target's meta table is byte-for-byte
            # what it is today and a stale count can never outlive its outage.
            with contextlib.suppress(Exception):
                _n_unreadable = _solved_accepted_unreadable(proj)
                if _n_unreadable > 0:
                    proj.set_meta(AUTO_STACK_UNREADABLE_META_KEY,
                                  str(_n_unreadable))
                else:
                    proj.delete_meta(AUTO_STACK_UNREADABLE_META_KEY)
            # Stamp any saved calibration picks this run had to skip, so History
            # can say *why* the picture came out less calibrated than the user
            # asked for. Best-effort and additive: a run that skipped nothing
            # writes no key, so every existing run reads back as it does today.
            if calibration_skipped and result.run_id is not None:
                with contextlib.suppress(Exception):
                    proj.set_meta(
                        f"{CALIBRATION_SKIPPED_META_PREFIX}{result.run_id}",
                        json.dumps(calibration_skipped))
            # Stamp the mismatches between a master that *was* applied and the
            # lights it calibrated (a dark at the wrong exposure/temperature).
            # Same fail-soft, additive shape as the skipped picks above: a run
            # with a matching dark writes no key.
            _cal_warnings = list(getattr(result, "calibration_warnings", []) or [])
            if _cal_warnings and result.run_id is not None:
                with contextlib.suppress(Exception):
                    proj.set_meta(
                        f"{CALIBRATION_WARNINGS_META_PREFIX}{result.run_id}",
                        json.dumps(_cal_warnings))
    finally:
        proj.close()
    lib.refresh_target_stats(safe)

    return {
        "output_dir": str(result.output_dir),
        "run_id": result.run_id,
        "n_frames_used": result.n_frames_used,
        "canvas_shape": list(result.canvas_shape),
        "cancelled": result.cancelled,
        "errors": result.errors,
        "excluded_frames": result.excluded_frames,
        # Honest frame accounting for the Jobs summary — how many subs were
        # attempted and how many couldn't be aligned. getattr-guarded so a partial
        # result stand-in (older code path / test double) degrades to 0 rather
        # than raising; the real StackResult always carries them.
        "n_offered": getattr(result, "n_offered", 0),
        "n_align_failed": getattr(result, "n_align_failed", 0),
        # Of those failures, how many were simply missing files (cleared cache +
        # offline share, unmounted drive) — so the walk-away user is pointed at
        # the storage, not sent hunting for mixed targets or bad plate-solves.
        "n_unreadable": getattr(result, "n_unreadable", 0),
        # The other storage failure: subs whose file *was* there and then failed
        # mid-read (a flaking share, a bad sector), counted per sub rather than
        # left as raw strings in `errors` that no screen reads — and how many of
        # those a two-pass run read fine on its other pass and combined anyway.
        "n_read_errors": getattr(result, "n_read_errors", 0),
        "n_read_recovered": getattr(result, "n_read_recovered", 0),
        # The outlier-rejection tally, so the Jobs "Process target" result can
        # name the invisible clean-up (e.g. a lone satellite/plane trail that a
        # walk-away small-stack auto-picked min/max removed) right where the
        # finished picture lands. None/None when no rejection pass ran.
        "rejection_mode": getattr(result, "rejection_mode", None),
        "rejection_fraction": getattr(result, "rejection_fraction", None),
        # A master dark that doesn't match the subs it calibrated (wrong exposure
        # or a very different sensor temperature). Reported on the job result too,
        # not only on History, so the walk-away user reads it the moment the
        # unattended stack lands rather than having to go looking.
        "calibration_warnings": list(getattr(result, "calibration_warnings", []) or []),
    }


def _rendered_preview_crop(project_dir: Path, run_id: int, recipe,
                           out_shape: tuple[int, int]) -> str | None:
    """The ``stack_runs.preview_crop_json`` value for a preview just rendered from
    ``recipe``, or ``None`` when the render still shows the whole canvas.

    Reads the crop the recipe *asks* for and then checks it against what the
    render actually produced: the rendered array should be the recipe's fraction
    of the cached proxy the render ran on. If it isn't (``geometry.crop`` ignores
    a crop that is degenerate at full resolution, and clamps a sliver to 1 px),
    the recorded geometry would be a lie — so record
    :data:`~seestack.previewcrop.UNKNOWN` and let the consumers decline to place
    anything rather than place it wrong. When the proxy's own size can't be read
    the recipe's bounds are taken at face value, which is the pre-check
    behaviour and still strictly better than recording nothing."""
    from seestack.edit.proxy import cached_proxy_shape
    from seestack.edit.recipe import preview_crop_of_recipe
    from seestack.previewcrop import UNKNOWN, PreviewCrop, preview_crop_json

    crop = preview_crop_of_recipe(recipe)
    if crop is None or crop == UNKNOWN:
        return preview_crop_json(crop)
    assert isinstance(crop, PreviewCrop)
    src = cached_proxy_shape(project_dir, run_id)
    if src is not None:
        got_h, got_w = int(out_shape[0]), int(out_shape[1])
        want_h = int(round(crop.h_frac * src[0]))
        want_w = int(round(crop.w_frac * src[1]))
        # One pixel of slack per axis: the op rounds each edge independently.
        if abs(got_h - want_h) > 1 or abs(got_w - want_w) > 1:
            return preview_crop_json(UNKNOWN)
    return preview_crop_json(crop)


def _auto_edit_process_run(lib: Library, safe: str, run_id: int,
                           auto_crop: bool = True) -> int | None:
    """Chain the one-click Auto recipe onto a freshly-produced stack run so the
    "Process target" result is a finished picture: persist the Auto recipe as the
    run's editor recipe (the editor then opens on the edited image) and re-render
    the run's preview thumbnail through it (History/Target show the picture, not a
    flat linear master).

    Additive and reversible — only runs the user explicitly asked to *Process* get
    this; the recipe is a normal saved editor recipe (Reset/undo restores linear)
    and only this run's own preview PNG is rewritten. Returns the number of enabled
    ops applied, or ``None`` when it was skipped (no such run / no FITS) or failed
    (best-effort — never fails the Process job).

    ``auto_crop`` carries the owner's ``auto_crop_border`` preference through to the
    recipe, so an unattended auto-edit frames the picture the same way clicking Auto
    in the editor would."""
    from webapp.routers.editor import (
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        AUTO_EDIT_COLORCAL_PREFIX,
        AUTO_EDIT_NOTE_PREFIX,
        AUTO_EDIT_SKYCAST_PREFIX,
        RECIPE_META_PREFIX,
        _read_auto_preferences,
        build_auto_analysis_for_run,
        build_auto_recipe_for_run,
        render_run_display_array,
    )
    from seestack.edit import presets as presets_mod
    from seestack.edit.histogram import measure_sky_cast
    from seestack.io.project import Project
    from seestack.stack.output import _write_preview_png

    try:
        entry = lib.find_target(safe)
        if entry is None:
            return None
        proj = Project.open(lib.target_dir(entry))
        try:
            run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
            if run is None or not run.fits_path or not Path(run.fits_path).exists():
                return None
            median_fwhm = proj.median_fwhm()
            # Apply the library's Adaptive-Auto taste profile (neutral if unset)
            # so an unattended "Process target" auto-edit matches what the owner
            # would get clicking Auto interactively.
            prefs = _read_auto_preferences(lib)
            recipe = build_auto_recipe_for_run(
                proj.project_dir, run, median_fwhm, prefs=prefs,
                auto_crop=auto_crop)
            proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe.to_json())
            # Stamp a plain-language "what Auto did (and why)" note so the History
            # Info panel can explain this silently-applied edit — the same reasoning
            # the interactive editor shows when a user clicks Auto themselves.
            try:
                analysis = build_auto_analysis_for_run(
                    proj.project_dir, run, median_fwhm, auto_crop=auto_crop)
                note = presets_mod.auto_edit_summary(recipe, analysis)
            except Exception:  # noqa: BLE001 — the note is a nicety, never fatal
                note = presets_mod.auto_edit_summary(recipe, None)
            if note:
                proj.set_meta(f"{AUTO_EDIT_NOTE_PREFIX}{run_id}", note)
            if run.preview_path:
                out, render_ctx = render_run_display_array(
                    proj.project_dir, run, recipe, return_ctx=True)
                _write_preview_png(Path(run.preview_path), out, already_display=True)
                # Record *which* look these bytes show. The recipe stamped above and
                # this preview agree right now, and several surfaces lean on that —
                # but a later "open in editor, tweak, Save" rewrites the recipe and
                # leaves these bytes untouched, and nothing else on disk can tell.
                # Stored as the look rather than the recipe so it is compared the
                # same uid-/timestamp-blind way everywhere else (``_recipe_look``).
                # Imported here, not at module scope: ``routers.stack`` imports this
                # module.
                from webapp.routers.stack import _recipe_look
                proj.set_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}",
                              json.dumps(_recipe_look(recipe.to_json())))
                # This render is on the master's own (un-rotated) grid, so any
                # North-up rotation an earlier "Adjust → North up → Save" baked
                # into the old bytes is gone. Clear the recorded angle with them:
                # every surface that lines up with the stored preview — the Sky
                # map's footprint and tile, the share/wallpaper North-up turn —
                # reads that column, and a stale one would have them correcting
                # for a rotation that is no longer there.
                proj.set_stack_preview_north_up(run_id, 0.0)
                # ...and record the other way this render can stop being a plain
                # downscale of the canvas: Auto ends with a `geometry.crop` that
                # trims a mosaic's ragged border (`auto_crop_border`, on by
                # default), so the bytes we just wrote can be a *crop*. Recorded
                # from what the render actually did — the recipe's composed
                # bounds, checked against the shape the render came out — so a
                # crop the op declined (degenerate on the proxy) can't be
                # recorded as one. NULL for every un-cropped render, which is
                # what every consumer already assumes.
                proj.set_stack_preview_crop(
                    run_id, _rendered_preview_crop(proj.project_dir, run_id,
                                                   recipe, out.shape[:2]))
                # The preview is now the Auto recipe's tone-mapped result, but the
                # run's FITS stays linear (the recipe is stored separately and is
                # reversible). Mark the run so the parity surfaces — the one-sub-vs-
                # stack reveal and the Adjust stretch suggestion — self-hide instead
                # of comparing a raw STF sub / anchoring an asinh curve to this
                # recipe-toned thumbnail (they already do for a display-space export).
                proj.set_run_preview_display_space(run_id)
                # Stamp which colour-calibration (white-balance) path Auto actually
                # ran and on how many stars — star-based, the v0.107.9
                # background-neutral fallback, or a no-op — so the History Info panel
                # can tell the user whether their hands-off image was really
                # white-balanced. Read-only + best-effort (a nicety, never fatal).
                cc = render_ctx.op_notes.get("tone.color_calibrate")
                if isinstance(cc, dict) and cc.get("mode_used"):
                    proj.set_meta(f"{AUTO_EDIT_COLORCAL_PREFIX}{run_id}",
                                  json.dumps(cc))
                # Measure the finished picture's residual sky-background colour
                # cast on the render we just produced and stamp it into the run's
                # provenance, so History can show whether this hands-off Auto
                # result landed neutral — and the owner gets a passive real-data
                # read on Auto's colour path across every walk-away run. Read-only
                # + best-effort (a measurement is a nicety, never fatal).
                try:
                    sky_cast = measure_sky_cast(out)
                    proj.set_meta(f"{AUTO_EDIT_SKYCAST_PREFIX}{run_id}",
                                  json.dumps(sky_cast))
                except Exception:  # noqa: BLE001 — the sky-cast read is a nicety
                    pass
        finally:
            proj.close()
        return len([o for o in recipe.ops if o.enabled])
    except Exception as exc:  # noqa: BLE001 — auto-edit is a non-critical nicety
        log.warning("Process-target auto-edit skipped for run %s: %s", run_id, exc)
        return None
