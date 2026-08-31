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

# A pixel is "thin coverage" when far fewer frames overlap it than the
# best-covered region — under a quarter of the peak frame count, the ratio
# :func:`seestack.stack.stacker.coverage_thin_fraction` measures the share with.
# Needs a few frames at the peak for any of it to mean anything.
_COVERAGE_MIN_PEAK = 4
# …and a *picture* has a ragged border when enough of it is thin to be worth
# trimming. This is the share of the covered canvas, not the single thinnest
# pixel: judging it on ``coverage_min`` (as this did until v0.320.2) meant judging
# it on the fringe pixel that exactly one frame touched, so the test was really
# "1/N ≤ 0.25", which every dithered stack of ≥4 subs passes — and every mosaic,
# whose canvas corners are uncovered, so ``coverage_min`` is 0. Measured on real
# ``run_stack`` output: a ±6 px-dithered single field is 0.2–0.6 % thin at 8, 32
# and 128 subs (stable in N, where the old ratio ran 0.00 → 0.03 → 0.06), an even
# three-panel mosaic is 0.0 %, and a genuinely lopsided 12/1/1 mosaic is 62 %. The
# 5 % floor sits an order of magnitude above the honest cases and two below the
# ragged one.
_COVERAGE_THIN_SHARE = 0.05

# The κ-σ / drizzle outlier-rejection fraction band in which the "we cleaned the
# trails out" reassurance is both meaningful and honest. Below the floor a stack
# rejected essentially nothing (data was already clean — no clean-up to claim);
# above the ceiling the clip is suspiciously large (κ may be eating real signal,
# which the History Info panel already flags as a caution), so a cheerful
# beginner "we removed passing lights" note would be over-claiming — stay silent.
_REJECTION_NOTE_MIN_FRACTION = 0.0005  # 0.05% of samples
_REJECTION_NOTE_MAX_FRACTION = 0.08    # 8% — matches the History "high, check κ" line

# When sub-pixel refine can't lock a sub within its shift cap it stacks the frame
# unshifted (only *roughly* aligned) — soft/doubled stars with nothing pointing at
# alignment. Surface it only once it's a materially large share of the contributing
# subs, on a stack big enough for the fraction to mean something — the SAME
# ≥20%-of-≥10 gate the frontend ``roughlyAlignedNote`` uses, so the two surfaces
# never disagree. ``n_frames_used`` (contributing subs) is the honest denominator:
# only a sub that made it into the stack can be roughly aligned.
_ROUGHLY_ALIGNED_MIN_USED = 10
_ROUGHLY_ALIGNED_NOTE_FRACTION = 0.20

# The finished stack's own median star size (``stack_fwhm_px``) should be no
# *fatter* than its contributing subs' median FWHM — a well-registered stack
# holds the subs' sharpness (averaging can even tighten it). When the stacked
# stars come out materially bloated *relative to the subs that built them*, the
# combine smeared them: the classic fingerprint of accumulated sub-pixel /
# field-rotation registration error over the night (which each frame's own
# refine didn't individually flag). This is a *relative* signal — it compares
# the stack to the target's own subs, both in native-frame px — so it needs no
# absolute/per-camera FWHM threshold. The ratio floor is deliberately gentle so
# a normal well-aligned stack never trips it (a good stack sits ~≤1.0×); it only
# fires on real bloat. Needs a handful of subs with a measured FWHM for the sub
# median to mean anything.
_SOFT_STARS_BLOAT_RATIO = 1.5
_SOFT_STARS_MIN_SUB_FWHM = 5

# A mosaic's ``seam_residual`` is the sky step still left between coverage levels
# divided by the picture's own grain, so the two thresholds below are read in
# units of noise. Below the "flat" bar the joins are well inside the grain and we
# can honestly say the panels matched; above the "visible" bar a coherent step
# that size shows as a seam once the image is stretched. The gap between them is
# deliberately left **silent**: real large-scale structure crossing panels (a big
# nebula) puts a floor under the measurement that has nothing to do with seams,
# so a middling number is genuinely ambiguous and neither claim would be honest.
# Measured on a realistic 4-panel synthetic scene: a correctly-leveled canvas
# reads 0.56 with a nebula across it and 0.02 without; deliberately stranding one
# level by 2× / 3× the true noise reads 1.39 / 2.08; leaving the panel offsets in
# entirely reads 15.7.
_SEAM_FLAT_RATIO = 1.0
_SEAM_VISIBLE_RATIO = 1.5


def seam_verdict(seam_residual: float | None) -> str | None:
    """The panel-flatness verdict for a run, or ``None`` when there is nothing
    honest to say.

    ``"flat"`` — the joins are well inside the picture's own grain.
    ``"check"`` — a coherent step big enough to show once the image is stretched.
    ``None`` — no measurement (a single-field stack, a pre-schema-15 run, a
    broken/non-finite figure), or the deliberately silent middle band above.

    Shared by the "How's my stack?" seam notes and by the History card's chip so
    the two surfaces read the same thresholds and can never disagree — the chip
    must not re-type these numbers in TypeScript.
    """
    if seam_residual is None:
        return None
    try:
        seam = float(seam_residual)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seam):
        return None
    if seam >= _SEAM_VISIBLE_RATIO:
        return "check"
    if seam < _SEAM_FLAT_RATIO:
        return "flat"
    return None


# κ-σ rejection is *mathematically* blind to a lone outlier below a frame count
# that depends on κ (11 at the default κ=3): a single bright sample's z-score
# against statistics that still include it peaks at (n−1)/√n, so at n=5 a
# satellite trail scores z ≈ 1.79 against a κ of 3 and survives untouched. When a
# run's stored κ can't be read (a garbled/absent options_json), assume the app
# default rather than staying silent — every shipped default has used 3.0.
_DEFAULT_SIGMA_KAPPA = 3.0


def _run_sigma_kappa(options_json: str | None) -> float:
    """The κ a run's κ-σ pass used, from its stored options. Falls back to the
    app default for an unparseable/absent value — the threshold this feeds is an
    advisory note, so a sensible default beats saying nothing."""
    import json

    try:
        opts = json.loads(options_json) if options_json else {}
    except (ValueError, TypeError):
        return _DEFAULT_SIGMA_KAPPA
    if not isinstance(opts, dict):
        return _DEFAULT_SIGMA_KAPPA
    kappa = opts.get("sigma_kappa")
    if isinstance(kappa, (int, float)) and math.isfinite(kappa) and kappa > 0:
        return float(kappa)
    return _DEFAULT_SIGMA_KAPPA


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
    (``"trim_border"`` | ``"calibration"`` | ``"solve_help"`` | ``"restack"``
    | ``"background"`` | ``None``)."""

    kind: str
    severity: str
    message: str
    action: str | None = None


@dataclass(frozen=True)
class DarkSpec:
    """The exposure/gain a beginner should shoot their *dark* frames at so they
    match the lights — the numbers behind the "How to add darks" guide. Either
    field may be ``None`` when the frames didn't record it (older/odd FITS); the
    guide then falls back to generic wording rather than a wrong number."""

    exposure_s: float | None
    gain: float | None


def recommended_dark_spec(frames: Iterable[FrameRow]) -> DarkSpec:
    """The exposure and gain to shoot darks at, read from the target's own subs.

    Darks must match the lights' exposure and gain to subtract correctly, so we
    report the *typical* value across the accepted subs (median exposure, median
    gain) — the numbers a beginner should dial in. Pure/offline; returns a
    ``DarkSpec`` whose fields are ``None`` when no accepted frame recorded them,
    so the caller can degrade to generic wording instead of inventing a value.
    """
    accepted = [f for f in frames if f.accept]
    exps = [f.exposure_s for f in accepted
            if f.exposure_s is not None and f.exposure_s > 0]
    gains = [f.gain for f in accepted if f.gain is not None]
    return DarkSpec(
        exposure_s=statistics.median(exps) if exps else None,
        gain=statistics.median(gains) if gains else None,
    )


def _median_eccentricity(accepted: list[FrameRow]) -> float | None:
    vals = [f.eccentricity_median for f in accepted
            if f.eccentricity_median is not None]
    return statistics.median(vals) if vals else None


def _median_sub_fwhm(accepted: list[FrameRow]) -> float | None:
    """Median measured star size (FWHM, native-frame px) across the accepted
    subs, or ``None`` when too few recorded one. The per-target anchor the
    stack's own ``stack_fwhm_px`` is compared against for the soft-stars note."""
    vals = [f.fwhm_px for f in accepted
            if f.fwhm_px is not None and math.isfinite(f.fwhm_px) and f.fwhm_px > 0]
    if len(vals) < _SOFT_STARS_MIN_SUB_FWHM:
        return None
    return statistics.median(vals)


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
    # Judged on *how much* of the picture is thin, not on how thin its thinnest
    # pixel is — see ``_COVERAGE_THIN_SHARE``. A run recorded before that share
    # was measured (schema < 20) reports None, and we say nothing rather than fall
    # back to the old test: it fired on every stack the app has ever made, so
    # keeping it for old runs would mean knowingly repeating a false alarm. Those
    # runs get the note back the next time they are stacked.
    thin_share = run.coverage_thin_frac
    if (thin_share is not None and run.coverage_max >= _COVERAGE_MIN_PEAK
            and thin_share >= _COVERAGE_THIN_SHARE):
        scored.append((20, HealthNote(
            kind="coverage",
            severity="info",
            message=(f"About {thin_share * 100:.0f}% of this picture has "
                     "far fewer frames than the best-covered part, so it's "
                     "noisier and uneven there. Trim border gives a clean, even "
                     "rectangle."),
            action="trim_border",
        )))

    # --- κ-σ couldn't bite at this frame count --------------------------------
    # The stack ran the two-pass κ-σ clip, but with too few subs for κ-σ to reject
    # *anything*: a lone satellite/plane trail or cosmic-ray hit needs about 11
    # frames (at the default κ=3) before it stands out far enough from statistics
    # that still include it. So the trail is in the final picture, and nothing else
    # says so — the clean-up note below self-hides because the pass genuinely
    # clipped ~nothing, which reads as "your data was clean". The cure already
    # exists and is one switch away ("Auto outlier removal" resolves to the
    # order-statistic min/max drop, which works from 3 subs up); both default
    # paths turn it on for you, so this only fires for a run whose options said
    # otherwise — a saved default from before that existed, or an explicit choice.
    # Keyed off the *recorded* rejection mode, the authoritative account of what
    # actually ran: an auto-picked small stack records "min-max-reject" and a
    # drizzle run "drizzle-reject", so neither can trip this.
    n_combined = run.n_frames_used
    if (run.rejection_mode or "").strip() == "sigma-clip" and n_combined >= 1:
        from seestack.stack.stacker import kappa_min_frames

        need = kappa_min_frames(_run_sigma_kappa(run.options_json))
        if n_combined < need:
            scored.append((25, HealthNote(
                kind="rejection_blind",
                severity="info",
                message=(f"With only {n_combined} sub"
                         f"{'s' if n_combined != 1 else ''}, "
                         "sigma-clip outlier removal couldn't drop anything — it "
                         f"needs about {need} frames before a passing satellite or "
                         "cosmic-ray hit stands out enough to clip. Re-stack with "
                         "\"Auto outlier removal\" switched on and AstroStack will "
                         "use the min/max method instead, which works from 3 subs "
                         "up."),
                action="restack",
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

    # --- Sub-pixel refine left many subs only roughly aligned ------------------
    # A large share of contributing subs that refine couldn't lock within its
    # shift cap → those frames stacked unshifted, so stars can look soft/doubled
    # with nothing else pointing at the cause. Read the persisted count (schema
    # ≥ 13; older runs / refine-off runs are NULL → silent). Denominator is the
    # contributing count, the only population a roughly-aligned frame comes from.
    n_rough = run.n_roughly_aligned
    n_used = run.n_frames_used
    if (n_rough is not None and n_rough > 0
            and n_used >= _ROUGHLY_ALIGNED_MIN_USED
            and n_rough >= _ROUGHLY_ALIGNED_NOTE_FRACTION * n_used):
        n_rough = min(n_rough, n_used)
        scored.append((35, HealthNote(
            kind="roughly_aligned",
            severity="info",
            message=(f"{n_rough} of {n_used} stacked subs were only roughly "
                     "aligned, so your stars may look a little soft or doubled. "
                     "A steadier mount, or re-solving those subs, tightens them up."),
            action=None,
        )))

    # --- Stacked stars are bloated relative to the subs (registration smear) ---
    # If the finished stack's own star size is materially larger than the median
    # of its contributing subs, the combine — not the sky — is what softened the
    # stars: accumulated sub-pixel/field-rotation registration error over the
    # night. Purely relative (stack vs its own subs, both native px), so no
    # absolute FWHM bar. Silent when either measurement is missing (old runs, or
    # too few subs recorded a FWHM) or the stack is as sharp as its subs.
    stack_fwhm = run.stack_fwhm_px
    sub_fwhm = _median_sub_fwhm(accepted)
    if (stack_fwhm is not None and math.isfinite(stack_fwhm) and stack_fwhm > 0
            and sub_fwhm is not None
            and stack_fwhm >= _SOFT_STARS_BLOAT_RATIO * sub_fwhm):
        scored.append((37, HealthNote(
            kind="soft_stars",
            severity="info",
            message=("Your stacked stars came out fatter than the subs that made "
                     "them, so the combine — not the sky — softened them. This is "
                     "usually small alignment drift building up over the night; a "
                     "steadier mount, or re-solving the roughly-aligned subs, keeps "
                     "them tight."),
            action=None,
        )))

    # --- Mosaic panel seams: did the joins actually come out flat? -------------
    # The stacker measures the sky step still left between coverage levels on a
    # mosaic, in units of the picture's own grain. It is the one mosaic failure
    # mode a beginner can *see* but can't name — and until this was measured, the
    # only way it ever got noticed was the owner eyeballing an export. NULL on a
    # single-field stack (no joins to compare) and on runs from before it was
    # recorded, so both notes self-hide by construction.
    # Both the wording here and the History card's chip read the verdict from the
    # one shared :func:`seam_verdict`, so they can't drift apart.
    seam = run.seam_residual
    verdict = seam_verdict(seam)
    if verdict is not None:
        if verdict == "check":
            scored.append((40, HealthNote(
                kind="seams",
                severity="info",
                message=("The panels of this mosaic didn't fully even out — where "
                         "they join, the sky still steps by about "
                         f"{seam:.1f}× the picture's own grain, so faint seams may "
                         "show once it's stretched. It usually means those panels "
                         "were shot under different sky; the editor's background "
                         "tools can even it out further."),
                # The advice names a tool, so hand the user the tool: "background"
                # opens the editor on *this* run, where the background ops live.
                action="background",
            )))
        else:
            scored.append((62, HealthNote(
                kind="seams_flat",
                severity="good",
                message=("The panels of this mosaic evened out — the sky matches "
                         "across the joins, so you shouldn't see seams between "
                         "them."),
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
    # The exact complement of the ragged-border note above, so the panel can never
    # both praise and warn. On the old ``coverage_min`` test this praise was
    # *unreachable*: a dithered stack always has a one-frame fringe pixel, so no
    # real stack could earn it. None (an older run) stays silent either way.
    if (run.coverage_max > 0 and run.coverage_thin_frac is not None
            and run.coverage_thin_frac < _COVERAGE_THIN_SHARE):
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
