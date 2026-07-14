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

# A pixel is "thin coverage" when far fewer frames overlap it than the best-covered
# region. Only fires when there's real unevenness (a dithered/mosaic border), so a
# flat single-field stack (min≈max) never trips it. Needs a few frames at the peak
# for the ratio to mean anything.
_COVERAGE_RAGGED_RATIO = 0.25
_COVERAGE_MIN_PEAK = 4


@dataclass(frozen=True)
class HealthNote:
    """One plain-language observation about a finished stack.

    ``kind`` is a stable id (for tests / the frontend); ``severity`` is
    ``"good"`` | ``"info"`` (colour only, never alarming); ``action`` is an
    optional key the UI can wire to the button that already does it
    (``"trim_border"`` | ``"calibration"`` | ``None``)."""

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
