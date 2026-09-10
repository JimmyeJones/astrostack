"""
Drive the QC pipeline across all frames in a project.

Reads frame paths from the project DB, fans them out to a JobRunner, writes
results back to the DB and the model as they arrive. The actual QC function
``compute_for_db_row`` is module-level and pickleable so it can run in a child
process.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from seestack.io.project import readable_frame_path, restoration_stamp
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

    One more frame is re-offered under ``only_new``: a sub still sitting on an
    ``auto:streak`` rejection with **no recorded streak position** — i.e. one
    QC'd before those existed. That position is the only evidence
    :func:`stationary_streak_frames` can rescue it with, so without this an
    upgraded install keeps discarding the very subs the new guard exists for,
    forever. Strictly bounded and self-terminating: only frames that are
    *currently rejected as streaks* qualify (never a clean or accepted one), and
    one pass gives each of them a position, a clean re-QC that un-rejects it, or
    a ``qc_error`` — all three leave the set.
    """
    out: list[tuple[int, str, str | None, bool]] = []
    for f in project.iter_frames():
        if f.id is None:
            continue
        needs_streak_position = (
            (f.reject_reason or "") == "auto:streak"
            and f.streak_cx is None
            # A user override is never reconciled, so a position would buy it
            # nothing — and it is the one state a re-QC cannot clear, which
            # would make this re-offer the same frame on every scan.
            and not f.user_override)
        if only_new and not needs_streak_position and (
                f.star_count is not None
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
        # Written on every QC pass, including the clean one that stores None —
        # otherwise a frame that used to flag a streak would keep a stale
        # position and could be clustered with frames it has nothing to do with.
        "streak_cx": m.streak_cx,
        "streak_cy": m.streak_cy,
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


# ---------------------------------------------------------------------------
# The *stationary object* reconciliation — the half the fraction tiers can't do.
#
# The tiers above answer "was a majority of this target flagged?", which is the
# only question a shape-only detector's own output can support. It leaves a real
# gap: a marginal Hough decision flags a *variable subset* of the subs, so an
# edge-on galaxy is flagged on (say) 40 % of a session — under the >50 % tier,
# over the small tier's floor — and those good subs stay discarded. A target
# whose accepted-but-unsolved subs dilute the denominator hides the same way.
#
# Position separates the two causes where shape cannot. The scope tracks the
# target, so a bright extended object forms its component in the *same place in
# the frame* on every sub, all night. A satellite, plane or meteor lands
# somewhere different every time — and even a Starlink train, whose members do
# follow one track, is over in minutes. So: a cluster of flagged components at
# one spot, seen across a span no transient could survive, is a stationary
# object, whatever fraction of the target it covers.
#
# Contract, unchanged from the tiers: this only ever **un**-rejects, only frames
# whose own recorded position is in the cluster (a genuine trail among them stays
# rejected on its own evidence), never a user override, never a non-streak
# reason. A frame with no recorded position — every frame QC'd before the columns
# existed — is not evidence and is left exactly as the tiers left it.

#: How far from the cluster's median position a flagged component may sit and
#: still count as the same object, in normalised frame widths/heights. Generous
#: enough for dithering and for the field rotation an alt-az Seestar accumulates
#: over a night; small enough that independent trails clustering by chance is
#: implausible (~3 % of the frame area per trail, so four of them agreeing is a
#: one-in-a-million coincidence — and they would still have to span the hours
#: below).
STATIONARY_CLUSTER_RADIUS = 0.10

#: How many flagged frames must agree on the position. Four is where chance
#: agreement stops being worth worrying about, and no smaller number can
#: distinguish a cluster from a coincidence.
STATIONARY_MIN_FRAMES = 4

#: How long the clustered frames must span. A satellite pass is seconds; a
#: Starlink train is minutes; an aircraft is one frame. Nothing transient puts a
#: bright elongated feature in the *same* part of the frame an hour apart, and a
#: session long enough to be worth rescuing clears this easily.
STATIONARY_MIN_SPAN_S = 3600.0

#: How likely a cluster may be to have happened by chance and still count as an
#: object. Anchoring on one median asked "are the flagged frames at *this* one
#: place?" once; searching every candidate centre asks it once per flagged frame,
#: and that many tries turns the radius's own "four trails agreeing is a
#: one-in-a-million coincidence" into something that happens — measured, twenty
#: trails scattered over a night throw up a chance four in about one set in eight.
#: So a cluster is also scored against the null that the flagged components are
#: scattered at random over the frame (see :func:`_chance_cluster_p`), and one
#: that is not surprising under it decides nothing. Inert on a real object, which
#: is in *essentially every* sub of its pointing rather than four of them.
STATIONARY_CLUSTER_MAX_P = 0.05

#: How many distinct stationary objects one target may be credited with. A
#: **mosaic** is why this is not 1: its panels point at different sky, so an
#: elongated nebula spanning the mosaic forms its component at a *different*
#: place in each panel's frames, and a target can honestly carry one cluster per
#: panel. The cap exists only to bound the work (each round is a pass over the
#: flagged set), and clusters are taken largest-first so it can only ever drop
#: the least significant ones — comfortably above the panel count of any Seestar
#: mosaic (a 3×3 is 9), and far below "this flagged set is just trails".
STATIONARY_MAX_CLUSTERS = 16


def _chance_cluster_p(size: int, n_flagged: int) -> float:
    """How often ``size`` of ``n_flagged`` scattered marks land in one radius.

    The null model is the one that describes real trails: each flagged component
    lands somewhere independent and uniform in the frame, so the number joining a
    given mark inside :data:`STATIONARY_CLUSTER_RADIUS` is Poisson with mean
    ``(n_flagged - 1) × the disc's share of the frame``. The returned figure is
    that tail multiplied by ``n_flagged`` — the number of centres the search
    tries — because a coincidence anywhere is a coincidence, and forgetting to
    pay for the tries is exactly how a searched cluster fools itself. It is
    therefore an expected count, not a probability: it can exceed 1, which simply
    means "expect one of these by chance".
    """
    if size < 2 or n_flagged < 2:
        return 1.0
    lam = (n_flagged - 1) * math.pi * STATIONARY_CLUSTER_RADIUS ** 2
    # P(X >= size - 1), the neighbours a member needs beyond itself.
    term = math.exp(-lam)
    below = term
    for i in range(1, size - 1):
        term *= lam / i
        below += term
    return n_flagged * max(0.0, 1.0 - below)


def stationary_streak_frames(
    marks: list[tuple[int, float | None, float | None, str | None]],
) -> list[int]:
    """Which of these flagged frames show a *stationary* object.

    ``marks`` is ``(frame_id, cx, cy, timestamp_utc)`` for the frames under
    consideration. Returns the ids whose flagged component sits in a cluster of
    at least :data:`STATIONARY_MIN_FRAMES` frames within
    :data:`STATIONARY_CLUSTER_RADIUS` of one place in the frame **and** whose
    cluster spans :data:`STATIONARY_MIN_SPAN_S`; ``[]`` when there is no such
    cluster, which is the answer for real trails, for too small a sample, and
    for anything undated.

    Each cluster's centre is the **median** of its own members rather than their
    mean, so a genuine trail that happens to sit near the object can't drag the
    centre off it.

    **Clusters are found, not assumed** — the set may hold more than one, and
    this is what a mosaic needs. Its panels point at different sky, so one
    extended object spanning the mosaic lands in a different part of the frame in
    each panel's subs; anchoring on a single centre for the whole target then
    finds nothing at all (the centre falls between the panels' clusters and no
    frame is within the radius of it), and every panel stays rejected. Rounds are
    taken largest-cluster-first, up to :data:`STATIONARY_MAX_CLUSTERS`, with each
    round's members removed before the next — so a set holding exactly one
    cluster gives byte-for-byte the previous answer.

    Pure and side-effect free, so the rule can be tested without a database.
    """
    from seestack.activity_calendar import parse_utc

    usable: list[tuple[int, float, float, object]] = []
    for fid, cx, cy, stamp in marks:
        if fid is None or cx is None or cy is None:
            continue
        if not (np.isfinite(cx) and np.isfinite(cy)):
            continue
        when = parse_utc(str(stamp)) if stamp else None
        if when is None:
            continue  # undated: the span test can't be answered, so no verdict
        usable.append((fid, float(cx), float(cy), when))
    if len(usable) < STATIONARY_MIN_FRAMES:
        return []

    xs = np.asarray([m[1] for m in usable], dtype=float)
    ys = np.asarray([m[2] for m in usable], dtype=float)
    # Squared radius, so the search never takes a square root: the flagged sets
    # this runs on are per *target*, and on a mosaic of an elongated nebula that
    # is essentially every sub the owner has shot of it.
    r2 = STATIONARY_CLUSTER_RADIUS ** 2
    live = np.ones(len(usable), dtype=bool)

    def _members(cx: float, cy: float) -> np.ndarray:
        """Indices of the still-unclaimed marks within the radius of a centre."""
        within = ((xs - cx) ** 2 + (ys - cy) ** 2) <= r2
        return np.flatnonzero(within & live)

    keep: list[int] = []
    for _ in range(STATIONARY_MAX_CLUSTERS):
        n_live = int(live.sum())
        if n_live < STATIONARY_MIN_FRAMES:
            break
        # The floor for this round: the absolute minimum, raised to whatever size
        # stops being a coincidence in a set this big (see
        # :data:`STATIONARY_CLUSTER_MAX_P`). Solved once per round by walking up
        # from the minimum rather than tested per candidate, so the scan below can
        # reject most centres on their raw count alone.
        floor = STATIONARY_MIN_FRAMES
        while (floor <= n_live
               and _chance_cluster_p(floor, n_live) > STATIONARY_CLUSTER_MAX_P):
            floor += 1
        best: np.ndarray | None = None
        seen: set[tuple[float, float]] = set()
        # Every remaining mark is a candidate centre. Anchoring on one global
        # median instead is what missed the multi-panel case above.
        for i in np.flatnonzero(live):
            near = _members(xs[i], ys[i])
            if near.size < floor:
                continue
            # Re-centre on the candidate cluster's own median and re-collect, so
            # the accepted set is the same "median centre" one as before.
            centre = (float(np.median(xs[near])), float(np.median(ys[near])))
            if centre in seen:
                continue  # every mark of one cluster re-centres on the same spot
            seen.add(centre)
            group = _members(*centre)
            if group.size < floor:
                continue
            times = sorted(usable[j][3] for j in group)
            if (times[-1] - times[0]).total_seconds() < STATIONARY_MIN_SPAN_S:
                continue  # a Starlink train at one spot, not a tracked object
            if best is None or group.size > best.size:
                best = group
        if best is None:
            break
        keep.extend(int(j) for j in best)
        live[best] = False

    if not keep:
        return []
    # Back in the order the caller handed them over, so the verdict reads the
    # same way whichever cluster was found first.
    return [usable[j][0] for j in sorted(keep)]


def reconcile_streak_rejections(project) -> list[int]:
    """Re-accept auto:streak frames the detector can't have meant.

    Two independent guards, tried in order and both un-reject-only:

    1. **Fraction** — a streak flagged on a majority of the target can't be a
       transient trail (:data:`STREAK_MASS_REJECT_FRACTION` and its small-target
       tier). Unchanged.
    2. **Position** — failing that, flagged components that sit at one spot in
       the frame across hours are a stationary object however small a share of
       the target they are (:func:`stationary_streak_frames`). This is what
       rescues the marginal-detection case the fraction tiers structurally
       cannot see, and it needs the positions QC now records, so it simply never
       fires on frames checked before those existed.

    Returns the ids re-accepted (empty when neither guard fires), so the caller
    can log/summarise. Pure DB reconciliation — safe to call after any QC pass.
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
        return _reconcile_stationary(project, streaked)
    restored: list[int] = []
    stamp = restoration_stamp()
    for f in streaked:
        if f.id is None:
            continue
        # Only the streak reason kept these out; clear it and re-accept. The
        # ``streak_detected`` flag stays set, so the UI still shows "N streaked"
        # and the user can bulk-reject them if they really are trails. The stamp
        # records *when* the sub came back, so the Target page can tell that a
        # picture stacked earlier was made without it.
        project.update_frame(f.id, accept=True, reject_reason=None,
                             restored_utc=stamp)
        restored.append(f.id)
    log.info(
        "streak reconcile: re-accepted %d of %d frames auto-rejected as streaks "
        "(a majority — a stationary extended object, not transient trails)",
        len(restored), len(eligible),
    )
    return restored


def _reconcile_stationary(project, streaked: list) -> list[int]:
    """Guard 2 of :func:`reconcile_streak_rejections` — see its docstring.

    ``streaked`` is the already-filtered ``auto:streak`` population (no user
    overrides, no QC errors), so this only has to decide *which* of them sit at
    one place in the frame across a transient-implausible span.
    """
    marks = [
        (f.id, f.streak_cx, f.streak_cy, f.timestamp_utc)
        for f in streaked if f.id is not None
    ]
    keep = set(stationary_streak_frames(marks))
    if not keep:
        return []
    restored: list[int] = []
    stamp = restoration_stamp()
    for f in streaked:
        if f.id not in keep:
            continue
        # Same as the fraction guard: clear only the streak reason, leave
        # ``streak_detected`` set so the UI still counts them and the user can
        # bulk-reject if they disagree, and stamp when the sub came back.
        project.update_frame(f.id, accept=True, reject_reason=None,
                             restored_utc=stamp)
        restored.append(f.id)
    log.info(
        "streak reconcile: re-accepted %d of %d frames auto-rejected as streaks "
        "(their flagged feature stays in one place for hours — a tracked "
        "extended object, not a transient trail)",
        len(restored), len(streaked),
    )
    return restored
