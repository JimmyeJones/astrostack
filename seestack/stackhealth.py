"""Plain-language "How's my stack?" health check for a finished stack.

After a stack finishes, a beginner has no easy way to know whether the image is
*good* or what one thing would most improve it — the readiness card only speaks
to *integration time*, not the actual result. ``stack_health`` reads the cues we
**already compute** (the run record's stamped fields + the target's frame QC
metrics — no new heavy analysis) and turns them into a short, ranked list of
friendly notes: what's strong and the single highest-value next step.

It is strictly a **read-only suggestion, never a gate** (mirrors "Is it enough
yet?"). Each note maps to one sentence and at most one suggested action; the
card shows only the top one or two, never a wall of warnings.

Pure and offline: no I/O, no network, no new dependency. Lives in the engine
(no webapp imports) so it's unit-testable on plain records.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable

from seestack.io.project import FrameRow, StackRunRow
from seestack.session_recap import bucket_reject_reason

# Median eccentricity (0 = round, →1 = elongated) at/above which stars read as
# visibly stretched. QC grades eccentricity *relatively* (percentile), so there's
# no in-repo absolute threshold to borrow; this is a deliberately gentle floor —
# well-tracked Seestar subs sit ~0.3–0.5, so 0.6 only fires on genuinely elongated
# stars, and the note is soft ("won't ruin the picture") and never a gate.
_ECC_ELONGATED = 0.6

# Only *located* (plate-solved) subs reach the stacker, so a field where ASTAP
# fails to solve most subs stacks just the solved handful — a thin, speckly result
# from a night that looks fully "accepted" (the documented root of the faint-field
# "gibberish" report). Surface that loss with the concrete fix once it's large.
# We can only speak to solve success when at least one sub *did* locate; if we see
# zero located subs, plate-solve simply hasn't run yet, so stay silent rather than
# nag. Needs a handful of accepted subs for the fraction to be meaningful.
_UNSOLVED_MIN_ACCEPTED = 8
_UNSOLVED_NOTE_FRACTION = 0.30  # ≥30% of accepted subs unlocated → worth surfacing

# A pixel is "thin coverage" when far fewer frames overlap it than the best-covered
# region. Only fires when there's real unevenness (a dithered/mosaic border), so a
# flat single-field stack (min≈max) never trips it. Needs a few frames at the peak
# for the ratio to mean anything.
_COVERAGE_RAGGED_RATIO = 0.25
_COVERAGE_MIN_PEAK = 4

# The κ-σ / drizzle outlier-rejection fraction band in which the "we cleaned the
# trails out" reassurance is both meaningful and honest. Below the floor a stack
# rejected essentially nothing (data was already clean — no clean-up to claim);
# above the ceiling the clip is suspiciously large (κ may be eating real signal,
# which the History Info panel already flags as a caution), so a cheerful
# beginner "we removed passing lights" note would be over-claiming — stay silent.
_REJECTION_NOTE_MIN_FRACTION = 0.0005  # 0.05% of samples
_REJECTION_NOTE_MAX_FRACTION = 0.08    # 8% — matches the History "high, check κ" line


def _format_reject_pct(frac: float) -> str:
    """A plain, honest percentage for a rejection fraction (mirrors the History
    Info-panel wording): ``<0.1%`` for a sliver, one decimal below 10%, whole
    percent above."""
    pct = frac * 100
    if pct < 0.1:
        return "<0.1%"
    if pct < 10:
        return f"{pct:.1f}%"
    return f"{round(pct)}%"


@dataclass(frozen=True)
class HealthNote:
    """One plain-language observation about a finished stack.

    ``kind`` is a stable id (for tests / the frontend); ``severity`` is
    ``"good"`` | ``"info"`` (colour only, never alarming); ``action`` is an
    optional key the UI can wire to the page that already does it
    (``"trim_border"`` | ``"calibration"`` | ``"solve_help"`` | ``None``)."""

    kind: str
    severity: str
    message: str
    action: str | None = None


def _median_eccentricity(accepted: list[FrameRow]) -> float | None:
    vals = [f.eccentricity_median for f in accepted
            if f.eccentricity_median is not None]
    return statistics.median(vals) if vals else None


def stack_health(run: StackRunRow, frames: Iterable[FrameRow]) -> list[HealthNote]:
    """Return a ranked list of plain-language health notes for ``run``.

    ``frames`` is the target's frame records (the run doesn't store which frames
    it combined, so we read the currently-accepted set for star-shape — the same
    approximation the readiness/session cards make). Best-first; the caller shows
    the top one or two. Always returns at least one note (a positive fallback)."""
    frame_list = list(frames)
    accepted = [f for f in frame_list if f.accept]
    rejected = [f for f in frame_list if not f.accept]

    # (priority, note) — lower priority shown first. Actionable next-steps lead;
    # reassurance and the positive summary trail.
    scored: list[tuple[int, HealthNote]] = []

    # --- Most subs couldn't be located (plate-solve failures) ------------------
    # Only plate-solved subs stack, so a field where ASTAP fails on most of them
    # collapses a whole night to the solved handful — a thin, noisy result even
    # though the frames all read as "accepted". This is the single highest-value
    # lever when it fires (it explains the faint-field "gibberish"), so it ranks
    # first. Guarded on ≥1 located sub so we only speak once solve has actually run
    # (all-unsolved = solve pending, not a failure to report), and on a handful of
    # accepted subs so the fraction is meaningful.
    located = [f for f in accepted if f.wcs_json]
    n_acc = len(accepted)
    n_loc = len(located)
    if (n_loc > 0 and n_acc >= _UNSOLVED_MIN_ACCEPTED
            and (n_acc - n_loc) >= _UNSOLVED_NOTE_FRACTION * n_acc):
        scored.append((5, HealthNote(
            kind="unsolved",
            severity="info",
            message=(f"Only {n_loc} of {n_acc} subs could be located (plate-solved), "
                     f"so the other {n_acc - n_loc} couldn't be stacked and this "
                     "result is thinner than your night. Installing ASTAP's star "
                     "database (Settings) helps far more subs solve — especially on "
                     "faint or sparse-star fields."),
            action="solve_help",
        )))

    # --- Calibration: were darks/flats applied? (robust presence check) --------
    calibrated = bool(run.calstat and run.calstat.strip())
    if not calibrated:
        scored.append((10, HealthNote(
            kind="calibration",
            severity="info",
            message=("No darks or flats were applied to this stack. Adding master "
                     "darks would cut the background speckle and hot pixels."),
            action="calibration",
        )))

    # --- Ragged low-coverage border (dithered/mosaic edges) --------------------
    if (run.coverage_max >= _COVERAGE_MIN_PEAK
            and run.coverage_min <= run.coverage_max * _COVERAGE_RAGGED_RATIO):
        scored.append((20, HealthNote(
            kind="coverage",
            severity="info",
            message=("The edges have far fewer frames than the centre, so the "
                     "border is noisier and uneven. Trim border gives a clean, "
                     "even rectangle."),
            action="trim_border",
        )))

    # --- Star shape: elongation (unitless, gentle) -----------------------------
    med_ecc = _median_eccentricity(accepted)
    if med_ecc is not None and med_ecc >= _ECC_ELONGATED:
        scored.append((30, HealthNote(
            kind="stars",
            severity="info",
            message=("Stars are a little elongated (a sign of tracking or tilt). "
                     "It won't ruin the picture, but rounder subs stack sharper."),
            action=None,
        )))

    # --- Reassurance: subs set aside is normal ---------------------------------
    n_total = len(frame_list)
    if rejected and n_total > 0:
        buckets: dict[str, int] = {}
        for f in rejected:
            b = bucket_reject_reason(f.reject_reason)
            buckets[b] = buckets.get(b, 0) + 1
        top_bucket = max(buckets, key=lambda b: buckets[b])
        scored.append((60, HealthNote(
            kind="rejects",
            severity="good",
            message=(f"{len(rejected)} of {n_total} subs were set aside "
                     f"(mostly {top_bucket}). That's normal — keeping only the "
                     f"good frames makes a cleaner result."),
            action=None,
        )))

    # --- Rejection clean-up: name the invisible "we removed the trails" work ----
    # The per-pixel outlier rejection quietly discards satellite/plane trails and
    # cosmic-ray hits that cross individual subs — a beginner never sees that work,
    # they just get a clean picture — so turn the stored tally into a reassuring,
    # plain-language trust cue. Only the *data-driven* κ-σ / drizzle fraction is a
    # real clean-up figure; min-max rejection is structural (it always drops the
    # extreme sample per pixel regardless), so name only its guarantee, no
    # (misleading) percentage.
    rej_mode = (run.rejection_mode or "").strip()
    rej_frac = run.rejection_fraction
    if rej_mode in ("sigma-clip", "drizzle-reject"):
        if (rej_frac is not None and math.isfinite(rej_frac)
                and _REJECTION_NOTE_MIN_FRACTION <= rej_frac < _REJECTION_NOTE_MAX_FRACTION):
            scored.append((65, HealthNote(
                kind="rejection",
                severity="good",
                message=(f"Cleaned ~{_format_reject_pct(rej_frac)} of pixels — passing "
                         "satellites, planes and cosmic-ray hits were rejected, so "
                         "they're not in your final image."),
                action=None,
            )))
    elif rej_mode == "min-max-reject":
        scored.append((65, HealthNote(
            kind="rejection",
            severity="good",
            message=("Dropped the brightest and darkest value at each pixel, so a lone "
                     "satellite or plane trail can't show up in your final image."),
            action=None,
        )))

    # --- Positive summary / strength note --------------------------------------
    strengths: list[str] = []
    if calibrated:
        strengths.append(f"calibrated ({run.calstat})")
    if med_ecc is not None and med_ecc < _ECC_ELONGATED:
        strengths.append("round stars")
    if (run.coverage_max > 0
            and run.coverage_min > run.coverage_max * _COVERAGE_RAGGED_RATIO):
        strengths.append("even coverage")
    if strengths:
        scored.append((70, HealthNote(
            kind="solid",
            severity="good",
            message="This looks like a solid stack — " + ", ".join(strengths) + ".",
            action=None,
        )))

    # Guarantee at least one note so the card always has something friendly to say.
    if not scored:
        scored.append((99, HealthNote(
            kind="ok",
            severity="good",
            message="Your stack looks healthy — nothing stands out to fix.",
            action=None,
        )))

    scored.sort(key=lambda pn: pn[0])
    return [note for _, note in scored]
