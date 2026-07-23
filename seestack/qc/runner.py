"""
Drive the QC pipeline across all frames in a project.

Reads frame paths from the project DB, fans them out to a JobRunner, writes
results back to the DB and the model as they arrive. The actual QC function
``compute_for_db_row`` is module-level and pickleable so it can run in a child
process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from seestack.io.project import readable_frame_path
from seestack.qc.metrics import FrameMetrics, compute_frame_metrics

log = logging.getLogger(__name__)


@dataclass
class QCResult:
    """What a worker returns. Keep simple types — must pickle."""

    frame_id: int
    metrics: FrameMetrics | None
    error: str | None


def compute_for_db_row(
    frame_id: int,
    fits_path: str,
    bayer_pattern: str | None,
    detect_streaks: bool = True,
) -> QCResult:
    """Module-level entry point used by JobRunner. Pickleable."""
    try:
        m = compute_frame_metrics(
            fits_path,
            bayer_pattern=bayer_pattern,
            detect_streaks=detect_streaks,
        )
        return QCResult(frame_id=frame_id, metrics=m, error=None)
    except Exception as exc:  # noqa: BLE001
        return QCResult(frame_id=frame_id, metrics=None, error=f"{type(exc).__name__}: {exc}")


def build_qc_arglist(project, *, only_new: bool = False) -> list[tuple[int, str, str | None, bool]]:
    """Build ``[(frame_id, path, bayer, detect_streaks), ...]`` from a project.

    With ``only_new`` (used by the auto-pipeline), skip frames that have already
    been QC'd successfully (``star_count`` populated) so a re-scan of a large
    library only processes genuinely new frames instead of recomputing metrics
    for everything every time.

    A frame that *failed* QC once (``qc_error:…`` — a transient read blip such as
    a NAS hiccup or a file still being written) is **re-offered once** so the
    auto-pipeline gets a second chance at it automatically, mirroring the ingest
    cache-copy retry. A second consecutive failure is stamped terminal
    (``qc_error_final:…`` by ``apply_qc_result_to_db``) and skipped thereafter, so
    a genuinely-corrupt file isn't re-QC'd on every scan forever; a manual full
    re-QC (``only_new=False``) still retries even terminal frames.
    """
    out: list[tuple[int, str, str | None, bool]] = []
    for f in project.iter_frames():
        if f.id is None:
            continue
        if only_new and (f.star_count is not None
                         or (f.reject_reason or "").startswith("qc_error_final")):
            continue
        path = readable_frame_path(f)
        if not path:
            continue
        out.append((f.id, path, f.bayer_pattern, True))
    return out


def apply_qc_result_to_db(project, result: QCResult, *, auto_reject: bool = True) -> None:
    """
    Write one QC result into the project DB. If ``auto_reject`` is True, frames
    with detected streaks are auto-rejected (unless the user has overridden).
    """
    existing = project.get_frame(result.frame_id)
    prior_reason = (existing.reject_reason if existing is not None else None) or ""

    if result.metrics is None:
        # A frame that already failed QC once and fails again is marked terminal
        # (``qc_error_final``) so ``build_qc_arglist(only_new=True)`` stops
        # re-offering a genuinely-corrupt file every re-scan; the first failure
        # stays retryable (``qc_error``) for a transient read blip.
        reason = "qc_error_final" if prior_reason.startswith("qc_error") else "qc_error"
        project.update_frame(result.frame_id, reject_reason=f"{reason}:{result.error or 'unknown'}")
        return
    m = result.metrics
    fields: dict = {
        "fwhm_px": m.fwhm_px,
        "star_count": m.star_count,
        "sky_adu_median": m.sky_adu_median,
        "eccentricity_median": m.eccentricity_median,
        "transparency_score": m.transparency_score,
        "streak_detected": m.streak_detected,
        "streak_count": m.streak_count,
    }
    if auto_reject and m.streak_detected:
        # Don't overwrite a user-driven decision.
        if existing is not None and not existing.user_override:
            fields["accept"] = False
            fields["reject_reason"] = "auto:streak"
    elif prior_reason.startswith("qc_error"):
        # QC previously failed on this frame (a transient error) but now succeeds:
        # clear the stale ``qc_error`` reject reason so it no longer shows as
        # "couldn't be quality-checked". Only ever clears a QC-error reason —
        # a user/auto reject is left untouched.
        fields["reject_reason"] = None
    elif prior_reason == "auto:streak" and not (
        existing is not None and existing.user_override
    ):
        # A frame the streak detector previously auto-rejected is now clean
        # (no streak on re-QC — e.g. a borderline detection that no longer
        # fires, or a detector/parameter change between versions). Self-heal it
        # the same way the ``qc_error`` branch above does, so a good frame isn't
        # silently kept out of the stack with a contradictory
        # ``accept=False`` / ``streak_detected=False`` record. Only ever
        # *un*-rejects an auto:streak reason on a clean, non-override re-QC —
        # mirrors ``reconcile_streak_rejections``' un-reject-only contract.
        fields["accept"] = True
        fields["reject_reason"] = None
    project.update_frame(result.frame_id, **fields)


# The streak detector (``qc/streaks.py``) is shape-based and per-frame: it flags
# any bright, long, elongated connected component. A *transient* satellite/plane
# trail hits only a small minority of a target's subs, which is exactly the case
# the whole-frame auto-reject is meant for. But a *stationary* bright extended
# object — an edge-on galaxy (NGC 4565, NGC 891), the Sombrero's dust lane, an
# elongated nebula — forms such a component on essentially *every* sub, so the
# shape-only detector flags a large fraction of the target and the auto-reject
# would then silently discard the WHOLE target's data. Guard against that here:
# a streak flagged on more than half a target's frames cannot be a transient
# trail, so those auto:streak rejections are re-accepted (any genuine trail is
# still cleaned per-pixel by the stack's sigma-clip/drizzle rejection — the same
# fallback ``keep_streaked_frames`` relies on). This only ever *un*-rejects, only
# above an implausible-for-satellites majority, never touches a user override or
# a non-streak reject reason, and only engages on a target large enough for the
# fraction to be meaningful.
STREAK_MASS_REJECT_FRACTION = 0.5
STREAK_RECONCILE_MIN_FRAMES = 10

# Small-target escape. Below the main floor the plain >50% fraction is too noisy
# to trust — a tiny target's *couple* of streaks could genuinely be satellites,
# so a bare majority isn't enough. But a stationary bright extended object (an
# edge-on galaxy on a beginner's first short session, well under 10 subs) trips
# the shape-only detector on *essentially every* sub, so a near-total flag rate
# is still an unambiguous "not transient" signal even on a small target — a lone
# satellite pass can't produce it. Without this, that first short session was
# silently discarded to ``auto:streak`` with "0 frames used" and no explanation.
# Require a higher fraction (near-all) and a floor of a few frames so a single
# transient can never trigger it; re-accepting stays fail-safe because the
# stack's own per-pixel sigma-clip/drizzle rejection still cleans any real trail.
STREAK_RECONCILE_SMALL_MIN_FRAMES = 3
STREAK_MASS_REJECT_FRACTION_SMALL = 0.8


def reconcile_streak_rejections(project) -> list[int]:
    """Re-accept auto:streak frames when they cover a majority of the target.

    Returns the ids re-accepted (empty when the guard doesn't fire), so the
    caller can log/summarise. Pure DB reconciliation — safe to call after any
    QC pass; a no-op when auto:streak rejection wasn't mass.
    """
    frames = list(project.iter_frames())
    # The population the streak auto-reject could plausibly act on: exclude hard
    # QC errors (unreadable frames, handled separately) and user decisions.
    eligible = [
        f for f in frames
        if not (f.reject_reason or "").startswith("qc_error")
        and not f.user_override
    ]
    n_eligible = len(eligible)
    streaked = [f for f in eligible if (f.reject_reason or "") == "auto:streak"]
    n_streaked = len(streaked)
    # Two tiers: a normal-sized target reconciles above a simple majority; a small
    # target (below the main floor) only above a near-total flag rate — see the
    # constants above. Below the small floor there's no meaningful fraction, so
    # leave the frames rejected.
    if n_eligible >= STREAK_RECONCILE_MIN_FRAMES:
        fires = n_streaked > STREAK_MASS_REJECT_FRACTION * n_eligible
    elif n_eligible >= STREAK_RECONCILE_SMALL_MIN_FRAMES:
        fires = n_streaked > STREAK_MASS_REJECT_FRACTION_SMALL * n_eligible
    else:
        fires = False
    if not fires:
        return []
    restored: list[int] = []
    for f in streaked:
        if f.id is None:
            continue
        # Only the streak reason kept these out; clear it and re-accept. The
        # ``streak_detected`` flag stays set, so the UI still shows "N streaked"
        # and the user can bulk-reject them if they really are trails.
        project.update_frame(f.id, accept=True, reject_reason=None)
        restored.append(f.id)
    log.info(
        "streak reconcile: re-accepted %d of %d frames auto-rejected as streaks "
        "(a majority — a stationary extended object, not transient trails)",
        len(restored), len(eligible),
    )
    return restored
