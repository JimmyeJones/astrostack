"""Pydantic models for the API + the StackOptions form schema.

``STACK_OPTION_FIELDS`` is the single source of truth the frontend uses to
render the stacking form generically (so adding a knob to the engine's
``StackOptions`` only requires adding a descriptor here). A unit test asserts
the descriptors stay in lockstep with the dataclass fields.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from pydantic import BaseModel

from seestack.stack.stacker import StackOptions

# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class TargetOut(BaseModel):
    safe_name: str
    name: str
    ra_deg: float | None = None
    dec_deg: float | None = None
    n_frames: int = 0
    n_frames_accepted: int = 0
    total_exposure_s: float = 0.0
    last_activity_utc: str | None = None
    has_preview: bool = False
    notes: str | None = None
    tags: list[str] = []
    # Run id (in this target's project) the user pinned as the showcase "cover"
    # image, or None to show the newest stack (the default). Lets the UI mark
    # which History run is the current cover.
    cover_stack_run_id: int | None = None


class TargetPatch(BaseModel):
    notes: str | None = None
    tags: list[str] | None = None


class SetCoverRequest(BaseModel):
    # The run id to pin as the target's cover. Null clears the pin (use newest).
    run_id: int | None = None


class FramingHintOut(BaseModel):
    """A "will it fit in one Seestar frame?" verdict for a matched target."""

    level: str  # "fits" | "tight" | "mosaic"
    text: str


class LightTravelOut(BaseModel):
    """"How far did you see?" — the light-travel line for a matched target."""

    distance_ly: float
    years: str   # the friendly duration alone, e.g. "2.5 million years"
    text: str    # the ready-to-render sentence


class AngularSizeOut(BaseModel):
    """"How big is it, really?" — a matched target's span in full Moons."""

    size_arcmin: float   # the catalog major axis this was built from
    moons: float         # that size in full-Moon widths, unrounded
    text: str            # the ready-to-render sentence


class MosaicPlanOut(BaseModel):
    """"How big a mosaic?" — the panel grid a too-big target's span needs."""

    cols: int   # panels along the frame's long edge
    rows: int   # panels along its short edge
    panels: int
    text: str   # a complete sentence, e.g. "About a 3×2 mosaic (6 panels) covers all of it."


class DifficultyHintOut(BaseModel):
    """A "how hard is this for a Seestar?" verdict for a matched target."""

    level: str  # "easy" | "moderate" | "challenging"
    label: str  # one-word badge text, e.g. "Easy"
    text: str


class BackgroundModeHintOut(BaseModel):
    """A suggested per-frame background-flatten mode for a matched target.

    ``mode`` is a ``StackOptions.background_mode`` value, so the Stack form can
    wire its one-click fix straight to it rather than re-deriving the choice.
    """

    mode: str   # "luminance" today
    text: str


class BestFrameOut(BaseModel):
    """The target's sharpest accepted sub, for the pre-stack "First look" card.

    ``frame_id`` is ``null`` when nothing is QC'd yet (no accepted frame carries
    a usable FWHM), so the UI shows no card. The metrics are echoed so the card
    can caption the pick ("your sharpest sub — FWHM 2.1 px, 480 stars")."""

    frame_id: int | None = None
    captured_utc: str | None = None
    fwhm_px: float | None = None
    star_count: int | None = None
    n_accepted: int = 0


class ObjectInfoOut(BaseModel):
    """Friendly identity for a target matched against the bundled catalog."""

    id: str
    name: str
    type: str
    constellation: str
    constellation_abbr: str
    ra_deg: float
    dec_deg: float
    matched_by: str
    # Major-axis angular size (arcmin) and the framing verdict derived from it,
    # when the catalog records a size for this object; ``null`` otherwise. Old
    # backends omit both, so the UI treats absent as "no framing hint".
    size_arcmin: float | None = None
    framing: FramingHintOut | None = None
    # "How big a mosaic?" — the panel grid for a target bigger than one frame;
    # ``null`` when it fits or has no vetted size. Old backends omit it, so the
    # UI treats absent as "nothing to say".
    mosaic: MosaicPlanOut | None = None
    # A plain-language, beginner-friendly one-liner about the object ("what am I
    # looking at?"), for the popular targets; ``""`` when the catalog has none.
    # Old backends omit it, so the UI treats absent/empty as "no blurb".
    blurb: str = ""
    # "How hard is this target for a Seestar?" — easy/moderate/challenging plus one
    # honest sentence, for the vetted popular objects; ``null`` when the object
    # isn't vetted (old backends omit it — the UI treats absent as "no verdict").
    difficulty: DifficultyHintOut | None = None
    # "Which per-frame background-flatten mode suits this target?" — set only for
    # a catalog target that is *extended emission* and big enough for the default
    # per-channel fit to bend into it; ``null`` for everything else, which is the
    # overwhelming majority (old backends omit it — the UI treats absent as "no
    # advice" and shows nothing).
    background_mode_hint: BackgroundModeHintOut | None = None
    # "How far did you see?" — the light in this picture left N years ago, from
    # the catalog's vetted distance. ``null`` for an object with no vetted
    # distance (old backends omit it — the UI shows nothing either way).
    light_travel: LightTravelOut | None = None
    # "How big is it, really?" — the object's span in full Moons, the one
    # angular yardstick a beginner already owns. ``null`` when the catalog has
    # no vetted size, or the object is too small for the comparison to say
    # anything (old backends omit it — the UI shows nothing either way).
    angular_size: AngularSizeOut | None = None


class IntegrationGoalOut(BaseModel):
    """A user-set per-target integration goal (total accepted exposure), in
    seconds, or ``null`` when the user hasn't set one (the readiness card then
    falls back to its sane per-object-type default)."""

    goal_s: float | None = None


class IntegrationGoalPatch(BaseModel):
    """Set (positive value) or clear (``null``) a target's integration goal."""

    goal_s: float | None = None


class SessionQualityDriftOut(BaseModel):
    """A cross-session softness nudge: the newest session is materially softer
    than the target's best previous one (higher FWHM = softer stars)."""

    kind: str
    latest_fwhm_px: float
    baseline_fwhm_px: float
    n_latest: int
    n_baseline: int


class AutoStackHoldOut(BaseModel):
    """Why the last hands-off scan held *this* target's stack back.

    The walk-away readability preflight (v0.270.1) refuses to publish a picture
    made thin by subs it couldn't read, and says so on the Jobs page — but a
    beginner whose picture stops updating looks at the **Target** page, where
    their picture lives. Same numbers, same wording, at the surface they
    actually stare at. Read-only, and derived from the most recent finished scan
    only, so it disappears by itself the moment a scan stacks the target.
    """

    offered: int
    readable: int
    unreadable: int
    reason: str | None = None
    when_utc: str | None = None


class CleanestShotOut(BaseModel):
    """The newest stack is materially cleaner than the target's pinned cover.

    A pinned cover never changes on its own — deliberately, because the choice
    is the user's — so a beginner who keeps adding subs can end up showing an
    older, noisier picture on every showcase surface than the one their own
    library already holds. This is the one-tap offer to close that gap; it never
    swaps anything by itself. ``null`` whenever there's nothing to say (see
    :func:`seestack.covernudge.cleanest_shot`).
    """

    run_id: int
    cover_run_id: int
    noise_sigma: float
    cover_noise_sigma: float
    percent_cleaner: int
    n_frames_used: int
    cover_n_frames_used: int
    timestamp_utc: str


class GrainierNewestOut(BaseModel):
    """The newest stack — which, with nothing pinned, *is* the cover — came out
    materially grainier than an earlier one the target already has.

    The mirror of :class:`CleanestShotOut`, for the state a beginner is actually
    in: nothing pinned, so the cover follows the newest stack and a hazy night's
    restack silently demotes a better picture everywhere. Same one-tap
    ``set-cover``, offering the earlier run instead; it never pins anything by
    itself. ``null`` whenever there's nothing to say (see
    :func:`seestack.covernudge.grainier_newest`).
    """

    run_id: int
    newest_run_id: int
    noise_sigma: float
    newest_noise_sigma: float
    percent_grainier: int
    n_frames_used: int
    newest_n_frames_used: int
    timestamp_utc: str


class SessionRecapOut(BaseModel):
    """Plain-language recap of a target's most recent capture session."""

    n_frames: int
    n_kept: int
    n_set_aside: int
    session_exposure_s: float
    kept_exposure_s: float
    total_kept_exposure_s: float
    start_utc: str | None = None
    end_utc: str | None = None
    # The *observing night* this session belongs to, as ISO ``YYYY-MM-DD`` — the
    # same noon-to-noon local bucket the Nights card and the imaging calendar use,
    # so the surfaces can't disagree about which night a session was. Additive and
    # optional: ``None`` when the start time can't be parsed, and an older frontend
    # simply shows no date at all, exactly as it did before.
    night_date: str | None = None
    reject_buckets: dict[str, int] = {}
    quality_drift: SessionQualityDriftOut | None = None
    # "Was the Moon washing this out?" — one plain-language sentence, present
    # **only** when a bright Moon was genuinely up and close to this target while
    # the session was being shot. Deliberately quiet: ``None`` on a good or merely
    # passable night (the common case), when the site is unknown, or when the
    # target has no solved position — so the card hides it rather than nagging.
    # Additive and optional; an older frontend simply ignores it.
    moon_note: str | None = None


class LiveConditionsOut(BaseModel):
    """How the last handful of subs have been going — the rolling "is it working
    right now?" read behind the live session view."""

    # "good" / "mixed" / "poor" / "unknown" — the last means "too few recent subs
    # to say", never "bad".
    verdict: str
    n_recent: int
    n_recent_kept: int
    median_fwhm_px: float | None = None
    recent_buckets: dict[str, int] = {}


class LiveSessionOut(BaseModel):
    """The capture session in progress (or the trailing one, if it has gone
    quiet) — "Tonight, live"."""

    active: bool
    n_frames: int
    n_kept: int
    n_set_aside: int
    kept_exposure_s: float
    session_exposure_s: float
    total_kept_exposure_s: float
    start_utc: str | None = None
    latest_utc: str | None = None
    minutes_since_latest: float | None = None
    conditions: LiveConditionsOut
    reject_buckets: dict[str, int] = {}
    newest_kept_frame_id: int | None = None
    # The target's readiness goal, when one is set — the other half of "have I got
    # enough to go inside?". ``None`` when no goal exists, so the page simply says
    # nothing rather than inventing a target to hit.
    goal_exposure_s: float | None = None


class NightSummaryOut(BaseModel):
    """One capture night in the per-target "Nights" breakdown."""

    start_utc: str | None = None
    end_utc: str | None = None
    # The *observing night* this session belongs to, as ISO ``YYYY-MM-DD`` — the
    # noon-to-noon local date the imaging calendar buckets on, so the two surfaces
    # can never name the same session's night differently. Additive and optional:
    # ``None`` when the start time can't be parsed, and an older frontend simply
    # keeps labelling from ``start_utc``.
    night_date: str | None = None
    n_frames: int
    n_kept: int
    n_set_aside: int
    exposure_s: float
    kept_exposure_s: float
    median_fwhm_px: float | None = None
    verdict: str                         # "sharp" | "soft" | "hazy" | "" (too few measured)
    is_best: bool = False
    reject_buckets: dict[str, int] = {}


class FocusTrendPointOut(BaseModel):
    """One accepted, measured sub on the focus-trend sparkline."""

    t_utc: str
    fwhm_px: float


class FocusTrendOut(BaseModel):
    """Star-sharpness (FWHM) over capture time for the target's latest session,
    plus a plain-language verdict ("steady" | "softened" | "improved")."""

    verdict: str
    points: list[FocusTrendPointOut]
    n_points: int
    median_fwhm_px: float
    early_fwhm_px: float
    late_fwhm_px: float
    start_utc: str | None = None
    end_utc: str | None = None
    soft_after_utc: str | None = None


class TransparencyTrendPointOut(BaseModel):
    """One accepted, measured sub on the transparency-trend sparkline."""

    t_utc: str
    transparency: float


class TransparencyTrendOut(BaseModel):
    """Sky-clarity (transparency) over capture time for the target's latest
    session, plus a plain-language verdict ("clear" | "degraded" | "cleared")."""

    verdict: str
    points: list[TransparencyTrendPointOut]
    n_points: int
    median_transparency: float
    early_transparency: float
    late_transparency: float
    start_utc: str | None = None
    end_utc: str | None = None
    degraded_after_utc: str | None = None
    # How many mosaic panels this night's subs split into — 0 (and absent from an
    # older backend) for the ordinary single-pointing target. Non-zero means the
    # scores above were levelled panel by panel, because a mosaic's panels are
    # different patches of sky and their star flux legitimately differs; the card
    # says so rather than letting the reader assume one continuous sky.
    n_pointings: int = 0


class HealthNoteOut(BaseModel):
    """One plain-language "How's my stack?" note (see seestack.stackhealth)."""

    kind: str
    severity: str          # "good" | "info" — colour only, never alarming
    message: str
    # UI action key ("trim_border" | "calibration" | "solve_help" | "restack" |
    # "background") or null. Free-form on purpose: an older frontend simply
    # renders no link for a key it doesn't know, so adding one is upgrade-safe.
    action: str | None = None


class DarkSpecOut(BaseModel):
    """The exposure/gain a beginner should shoot dark frames at (read from the
    target's own subs), powering the "How to add darks" guide's pre-filled
    numbers. Either field is ``null`` when the subs didn't record it."""

    exposure_s: float | None = None
    gain: float | None = None


class StackHealthOut(BaseModel):
    """Ranked health notes for a target's current stack, or ``null`` when the
    target has no genuine stack yet. The card shows the top one or two."""

    run_id: int | None = None
    notes: list[HealthNoteOut] = []
    # The exposure/gain to shoot darks at, for the "How to add darks" guide shown
    # beside an uncalibrated note. Additive/nullable — older clients ignore it.
    dark_spec: DarkSpecOut | None = None


class FrameOut(BaseModel):
    id: int
    name: str
    timestamp_utc: str | None = None
    exposure_s: float | None = None
    gain: float | None = None
    width_px: int | None = None
    height_px: int | None = None
    bayer_pattern: str | None = None
    solved: bool = False
    ra_center_deg: float | None = None
    dec_center_deg: float | None = None
    ra_hint_deg: float | None = None
    dec_hint_deg: float | None = None
    fwhm_px: float | None = None
    star_count: int | None = None
    sky_adu_median: float | None = None
    eccentricity_median: float | None = None
    transparency_score: float | None = None
    streak_detected: bool = False
    accept: bool = True
    reject_reason: str | None = None
    user_override: bool = False


class FramePatch(BaseModel):
    accept: bool | None = None
    reject_reason: str | None = None
    bayer_pattern: str | None = None


class BulkFrameAction(BaseModel):
    # Reject the worst `fraction` of accepted frames by `metric`,
    # reject every accepted frame flagged with a satellite/plane trail
    # (`reject_streaked`), reject accepted frames whose stars are strong
    # eccentricity outliers (`reject_trailed`), or accept/reject an
    # explicit list of ids.
    action: Literal[
        "accept", "reject", "reject_worst", "reject_streaked", "reject_trailed",
    ]
    ids: list[int] | None = None
    metric: Literal[
        "fwhm_px", "star_count", "eccentricity_median", "sky_adu_median",
        "transparency_score",
    ] = "fwhm_px"
    fraction: float = 0.1


class NightSetAside(BaseModel):
    """Bounds of one capture night to set aside (reject its accepted subs), as
    carried by a ``NightSummary`` from the Nights card. Sessions are
    gap-separated, so the inclusive ``[start_utc, end_utc]`` window names exactly
    that night's frames."""

    start_utc: str
    end_utc: str


class GradeReasonOut(BaseModel):
    """One plain-language reason a frame was flagged by auto-grade."""

    metric: str
    label: str      # human-readable explanation with numbers
    value: float
    typical: float  # population median for this metric
    z: float        # robust (modified) z-score in the bad direction


class GradeRecommendationOut(BaseModel):
    frame_id: int
    name: str
    reasons: list[GradeReasonOut]


class GradeReportOut(BaseModel):
    """Preview of what auto-grade would reject (GET) / did reject (POST)."""

    sensitivity: str
    n_accepted: int
    n_considered: int
    recommendations: list[GradeRecommendationOut]
    metrics_used: list[str]
    metrics_skipped: dict[str, str]
    capped: bool
    # How many mosaic panels the star-count / sky / transparency metrics were
    # graded against separately (each panel judged against itself, since panels
    # are different patches of sky). 0 for an ordinary single-pointing target,
    # where grading is target-wide as it always has been. Additive: an older
    # frontend simply ignores it.
    pointing_groups: int = 0
    # POST …/apply only: the frame ids actually rejected (for one-click undo).
    changed_ids: list[int] | None = None


class StackRunOut(BaseModel):
    id: int
    timestamp_utc: str
    output_basename: str
    n_frames_used: int
    canvas_w: int
    canvas_h: int
    coverage_min: int
    coverage_max: int
    has_fits: bool = False
    has_tiff: bool = False
    has_preview: bool = False
    # True when this run recorded *where* outlier rejection dropped samples (the
    # ``{base}_rejected.fits`` sibling — ``StackOptions.record_rejection_map``,
    # off by default), so the card can offer "show me what was removed". Defaults
    # False, which is every run that didn't ask and every run recorded before the
    # option existed — an older client simply ignores the field.
    has_rejection_map: bool = False
    # True when this run is the target's pinned showcase "cover" (the image the
    # Library/Dashboard tile shows). False when unpinned (the default) — the tile
    # then shows the newest stack. Only ever one run per target is the cover.
    is_cover: bool = False
    notes: str | None = None
    # Effective integration time in seconds (None for pre-schema-4 runs), so the
    # UI can show "2.3 h · 840 subs" on a card without reading the FITS header.
    total_exposure_s: float | None = None
    # True when this run's options can pre-fill the Stack form ("reuse settings").
    # False for editor-recipe / channel-combine runs, which carry no stack knobs.
    reusable: bool = False
    # Median transparency of the stacked frames ÷ the target's clear-sky
    # baseline (< ~0.6 ⇒ hazy). None for pre-schema-5 runs or when not
    # computable; lets the card show a "hazy night" badge at a glance.
    transparency_ratio: float | None = None
    # Background-noise σ of the stacked image, normalized to its own signal range
    # so it's comparable across gain/exposure (lower = cleaner). None for
    # pre-schema-6 runs or when not computable; lets the UI show a noise readout
    # and flag the cleanest of several stacks of one target.
    noise_sigma: float | None = None
    # This stack's own median star size (FWHM) in native-frame pixels — the per-run
    # sharpness counterpart of noise_sigma (lower = tighter stars). None for
    # pre-schema-14 runs or when too few stars to fit; lets the UI show a per-run
    # sharpness readout and compare a target's stacks.
    stack_fwhm_px: float | None = None
    # The North-up rotation (degrees) baked into this run's *stored preview PNG*
    # by History's "Adjust" save — 0.0/None when the picture was saved
    # un-rotated. Anything that draws on top of those stored bytes (the object
    # pins and the scale bar, whose coordinates are measured on the un-rotated
    # FITS grid) needs to know, or it plots on a picture that has since turned.
    preview_north_up_deg: float | None = None
    # What the *stored preview PNG* shows of the stack canvas when the "Process
    # target" auto-edit trimmed its ragged border: fractional ``x0/y0/x1/y1``
    # bounds, or None (the common case) for a plain full-canvas downscale. The
    # object pins and scale bar are measured on the un-cropped FITS grid, so they
    # have to be shifted into this rectangle before they're drawn on those bytes.
    preview_crop: dict[str, float] | None = None
    # True when the stored preview came out of a recipe whose geometry can't be
    # reduced to a crop of the canvas at all, so nothing measured on the FITS grid
    # can honestly be placed on it — the UI hides the pins/bar rather than
    # mis-plotting them, exactly as it does for a North-up-saved picture.
    preview_geometry_unknown: bool = False
    # How flat this *mosaic's* panel joins came out: the sky step still left
    # between coverage levels, in units of the picture's own grain (~0 = the
    # panels matched; around 1 is where a seam starts to show once stretched).
    # None for a single-field stack (no joins to compare), pre-schema-15 runs, or
    # when it couldn't be measured — the UI self-hides rather than guessing.
    seam_residual: float | None = None
    # The plain-language reading of ``seam_residual``: "flat" (the joins matched),
    # "check" (a step big enough to show once stretched), or None when there is
    # nothing honest to say — no measurement, or the deliberately silent middle
    # band where large-scale structure makes the figure ambiguous. Computed
    # server-side by the same `seestack.stackhealth.seam_verdict` the "How's my
    # stack?" notes use, so a card chip and the health note can never disagree.
    seam_verdict: str | None = None
    # Which calibration masters were applied to the lights ("dark+flat",
    # "bias+flat", "flat", …), or None when the stack was uncalibrated / for
    # pre-schema-7 runs; lets a card show a "dark+flat" chip at a glance.
    calstat: str | None = None
    # The stacking options this run was made with (parsed from options_json), so
    # the History card can show *how* the result was combined (σ-clip / min-max /
    # drizzle) — the same badge the Gallery derives. Empty dict when unrecorded.
    options: dict[str, object] = {}
    # The AstroStack version that produced this run, for provenance ("made with
    # v0.75.0"). None for runs recorded before this was tracked (schema < 9).
    engine_version: str | None = None
    # True when the user saved an edit for this run in the editor but never
    # exported it, so the preview every surface shows is still the plain
    # auto-stretch of the linear stack rather than the picture they made. Lets
    # those surfaces say so — and offer to finish the export — instead of
    # silently presenting the wrong image. False for every ordinary run.
    unexported_edit: bool = False


class JobOut(BaseModel):
    id: str
    kind: str
    target: str | None = None
    state: str
    phase: str = ""
    done: int = 0
    total: int = 0
    detail: str = ""
    created_utc: str | None = None
    started_utc: str | None = None
    finished_utc: str | None = None
    error: str | None = None
    # Stable canonical classification of a fatal error (memory_budget,
    # no_solved_frames, …) stamped server-side by JobManager. Mirrors the SSE
    # payload and Job.to_dict(); the frontend prefers it over string-matching the
    # raw `error` text (webapp/jobs.py, Jobs.tsx). None when unclassified.
    error_kind: str | None = None
    result: dict[str, Any] | None = None


class TargetCreate(BaseModel):
    name: str


class MergeRequest(BaseModel):
    into: str
    sources: list[str]


class MergeSuggestionTarget(BaseModel):
    """One target inside a same-object merge suggestion."""

    safe: str
    name: str
    n_frames_accepted: int
    total_exposure_s: float


class MergeSuggestionOut(BaseModel):
    """A friendly "these look like the same object — combine them?" suggestion:
    a cluster of ≥2 targets whose plate-solved centres agree. ``targets`` are
    ordered deepest-integration first, so ``targets[0].safe`` is the natural
    ``into`` for the one-click merge (it keeps the most history). Read-only."""

    object_name: str | None  # catalog id/common name for the cluster, or null
    center_ra_deg: float
    center_dec_deg: float
    max_sep_arcmin: float    # widest pairwise separation in the group (arcmin)
    targets: list[MergeSuggestionTarget]


class CleanupSuggestionOut(BaseModel):
    """A leftover target an old (pre-v0.184.9) scan built before the scanner
    learned the Seestar folder convention. Read-only detection: the Library offers
    a one-click "remove these" and the user confirms; nothing is deleted until then
    (``DELETE /api/targets/{safe}``). ``reason`` is one of ``"video"`` /
    ``"on_device_output"`` (built from a Seestar output or ``_video`` folder rather
    than raw sub-frames — cannot be stacked) or ``"duplicate_sub"`` (a
    ``<T>_sub``-named duplicate holding the *same* raw subs the base target ``<T>``
    now owns — a harmless clutter/wasted-compute leftover, not corrupt data) or
    ``"legacy_mixed_drop"`` (a legacy giant target an old scan built from a
    whole-device / mixed-folder container drop, mixing several objects' subs with
    on-device outputs/videos — the correct per-target versions now exist, so it's a
    stale duplicate that keeps auto-stacking gibberish; flagged at scan time);
    ``detail`` is a plain-language explanation for the beginner."""

    safe: str
    name: str
    n_frames: int
    reason: str
    detail: str


class ScanRequest(BaseModel):
    root: str | None = None  # default: settings.incoming_dir


# ---------------------------------------------------------------------------
# StackOptions form schema
# ---------------------------------------------------------------------------


class StackOptionField(BaseModel):
    key: str
    label: str
    type: Literal["bool", "int", "float", "str", "enum", "curve"]
    group: Literal["simple", "advanced"]
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    # Optional friendly display names for enum ``options`` (value -> label); the
    # form falls back to the raw value for any option without a mapping.
    option_labels: dict[str, str] | None = None
    help: str | None = None
    # When set, the field is only relevant if another field is truthy, or — with
    # the ``"key=value"`` form — equals a specific value.
    depends_on: str | None = None


# Curated descriptors. `default` is filled from the dataclass at import time so
# there's exactly one source of truth for defaults.
_DESCRIPTORS: list[dict[str, Any]] = [
    # --- simple ---
    {"key": "output_name", "label": "Output name", "type": "str", "group": "simple",
     "help": "Base filename for the stacked outputs."},
    {"key": "auto_reject", "label": "Auto outlier removal", "type": "bool", "group": "simple",
     "help": "Picks the best outlier removal for your number of subs — min/max on "
             "small stacks (where sigma clipping can't catch a lone satellite/plane "
             "trail), sigma clipping on large ones — so you don't have to choose. "
             "When on, it overrides the two options below."},
    {"key": "sigma_clip", "label": "Sigma clipping", "type": "bool", "group": "simple",
     "help": "Reject per-pixel outliers (satellites, cosmic rays, planes)."},
    {"key": "sigma_kappa", "label": "Sigma κ", "type": "float", "group": "simple",
     "min": 1.0, "max": 5.0, "step": 0.1, "depends_on": "sigma_clip",
     "help": "Lower = more aggressive rejection."},
    {"key": "min_max_reject", "label": "Min/max rejection", "type": "bool", "group": "simple",
     "help": "Drop one per-pixel min and max before averaging. Removes a lone "
             "satellite/plane trail or hot/cold sample even in a small stack, "
             "where sigma clipping can't. Needs 3+ frames; takes precedence over "
             "sigma clipping and ignores quality weights."},
    {"key": "min_max_reject_count", "label": "Extremes to drop (per side)", "type": "int",
     "group": "advanced", "min": 1, "max": 5, "step": 1, "depends_on": "min_max_reject",
     "help": "How many of the lowest and highest values to drop at each pixel. 1 = "
             "the classic single min/max drop. Raise it to remove several trails "
             "crossing one pixel across a session (3 → up to 3 trails). Only applied "
             "where a pixel has at least 2×this+1 frames; costs a little more memory."},
    {"key": "background_flatten", "label": "Background flatten", "type": "bool", "group": "simple",
     "help": "Subtract a per-frame sky model to remove gradients."},
    {"key": "quality_weighted", "label": "Quality weighting", "type": "bool", "group": "simple",
     "help": "Weight sharper / clearer frames more heavily."},
    {"key": "photometric_normalize", "label": "Photometric normalization", "type": "bool",
     "group": "advanced",
     "help": "Gain-match every frame's brightness to the run's median before combining, "
             "so haze and airmass across a multi-night session don't weaken outlier "
             "rejection or let hazy nights dim the result. Uses each frame's measured "
             "transparency; leaves un-measured frames untouched. Mosaics do this "
             "automatically — a panel shot through haze would otherwise stay dimmer "
             "than the one next to it."},
    {"key": "lucky_fraction", "label": "Lucky imaging (keep sharpest fraction)", "type": "float",
     "group": "simple", "min": 0.05, "max": 1.0, "step": 0.05,
     "help": "Keep only the sharpest frames by FWHM and drop the rest. This is a "
             "fraction, not a percentage: 1.0 = keep all, 0.75 = keep the sharpest "
             "three-quarters, 0.5 = the sharpest half. Shown as a percentage "
             "(e.g. \"Lucky 50%\") on the finished picture."},
    {"key": "drizzle", "label": "Drizzle (super-resolution)", "type": "bool", "group": "simple",
     "help": "Use the drizzle algorithm. Best with 200+ dithered frames."},
    {"key": "drizzle_reject", "label": "Drizzle outlier rejection", "type": "bool",
     "group": "simple", "depends_on": "drizzle",
     "help": "Second drizzle pass that rejects satellites, plane trails and cosmic "
             "rays (single-pass drizzle keeps them). Uses Sigma κ; needs 4+ frames. "
             "Takes roughly 2–3× as long. Unattended stacks (auto-stack, Process "
             "target) turn this on for themselves when there's memory for it."},
    {"key": "mono", "label": "Mono / filtered subs", "type": "bool", "group": "simple",
     "help": "Stack as single-channel luminance (no debayer). For mono cameras and "
             "L/R/G/B/narrowband subs. Combine channels later in Channel combine."},
    # --- advanced ---
    {"key": "background_mode", "label": "Background mode", "type": "enum", "group": "advanced",
     "options": ["per_channel", "luminance"],
     "option_labels": {"per_channel": "Per channel", "luminance": "Luminance"},
     "depends_on": "background_flatten",
     "help": "How the per-frame sky model is fitted. Per channel flattens R, G and B "
             "separately — best for star fields and small targets. Luminance fits one "
             "shared model and keeps colour on extended emission (nebulae like M42 / "
             "Lagoon / North America), where per-channel can leave cyan cores and red "
             "halos. Switch to Luminance for a big diffuse nebula."},
    {"key": "background_box_size", "label": "Background box size", "type": "int",
     "group": "advanced", "min": 32, "max": 512, "step": 16, "depends_on": "background_flatten",
     "help": "Grid size (px) of the sky model. Smaller follows finer gradients but risks "
             "eating real nebulosity; larger is gentler. 128 suits most Seestar frames."},
    {"key": "suppress_hot_pixels", "label": "Hot-pixel suppression", "type": "bool",
     "group": "advanced",
     "help": "Replace stuck hot/cold pixels with a local median before stacking. "
             "Cheap (~10 ms/frame) and safe to leave on."},
    {"key": "hot_pixel_sigma", "label": "Hot-pixel σ", "type": "float", "group": "advanced",
     "min": 2.0, "max": 10.0, "step": 0.5, "depends_on": "suppress_hot_pixels",
     "help": "How far above the local median a pixel must sit to count as hot. Lower = "
             "catches more (but can nibble faint stars); higher = only the worst."},
    {"key": "subpixel_refine", "label": "Sub-pixel alignment refine", "type": "bool",
     "group": "advanced",
     "help": "Add a phase-correlation pass that nudges each frame by a fraction of a "
             "pixel after the plate-solve align, for slightly tighter stars. Costs a "
             "little more time per frame; off by default."},
    {"key": "final_gradient_removal", "label": "Final gradient removal", "type": "bool",
     "group": "advanced", "help": "Post-stack gradient removal with object masking."},
    {"key": "final_gradient_mode", "label": "Final gradient mode", "type": "enum",
     "group": "advanced", "options": ["per_channel", "luminance"],
     "option_labels": {"per_channel": "Per channel", "luminance": "Luminance"},
     "depends_on": "final_gradient_removal",
     "help": "Same choice as Background mode, applied to the one post-stack gradient "
             "pass. Use Luminance for extended nebulae to keep their colour; Per channel "
             "for star fields."},
    {"key": "final_gradient_box_size", "label": "Final gradient box size", "type": "int",
     "group": "advanced", "min": 64, "max": 1024, "step": 32,
     "depends_on": "final_gradient_removal",
     "help": "Grid size (px) of the post-stack gradient model. Larger than the per-frame "
             "box because it works on the full stacked image; 256 suits most stacks."},
    {"key": "scale_dark_to_light", "label": "Scale dark to sub exposure", "type": "bool",
     "group": "advanced",
     "help": "When your master dark was shot at a different exposure than these subs, "
             "scale its dark current to match: dark = bias + (dark − bias)×(sub ÷ dark "
             "exposure). Needs a master bias selected too (to hold the readout pedestal "
             "fixed); without one the dark is used unscaled."},
    {"key": "color_calibration", "label": "Color calibration", "type": "bool", "group": "advanced",
     "help": "Balance the stack's colour so a neutral background reads grey, at stack "
             "time. The editor also offers colour calibration, so you can leave this off "
             "and do it there with a live preview."},
    {"key": "color_calibration_mode", "label": "Color cal. mode", "type": "enum",
     "group": "advanced", "options": ["gray_star", "gaia"],
     "option_labels": {"gray_star": "Gray-star (offline)", "gaia": "Gaia catalogue"},
     "depends_on": "color_calibration",
     "help": "Gray-star balances so the average star is neutral — fully offline and a "
             "good default. Gaia matches your stars to catalogue colours for a more "
             "physical result, but needs a plate-solved field and the Gaia data."},
    {"key": "mosaic_canvas", "label": "Canvas mode", "type": "enum", "group": "advanced",
     "options": ["auto", "union", "reference"],
     "help": "Output framing when frames don't all cover the same field. Auto uses a "
             "union canvas only when the frames span more than one Seestar field (a "
             "mosaic), else the reference frame. Union always keeps every frame's area; "
             "Reference always crops to the first frame. Leave on Auto unless mosaicking."},
    {"key": "tiff_mode", "label": "TIFF mode", "type": "enum", "group": "advanced",
     "options": ["linear", "autostretch"],
     "help": "How the exported TIFF is scaled. Linear keeps the raw stacked data (looks "
             "dark on screen but is what you edit — like DeepSkyStacker). Autostretch "
             "bakes in a gentle stretch so the TIFF is viewable straight away."},
    {"key": "drizzle_pixfrac", "label": "Drizzle pixfrac", "type": "float", "group": "advanced",
     "min": 0.1, "max": 1.0, "step": 0.05, "depends_on": "drizzle",
     "help": "How much each input pixel is shrunk before it's dropped onto the finer "
             "grid. Smaller = sharper but needs more frames to fill gaps; 0.8 is a safe "
             "middle. Only used when Drizzle is on."},
    {"key": "drizzle_scale", "label": "Drizzle scale", "type": "float", "group": "advanced",
     "min": 1.0, "max": 4.0, "step": 0.1, "depends_on": "drizzle",
     "help": "Output resolution multiplier. 2.0 = twice the reference resolution (full "
             "super-res), 1.0 = same size. Higher needs many well-dithered frames to pay "
             "off. Only used when Drizzle is on."},
    {"key": "drizzle_kernel", "label": "Drizzle kernel", "type": "enum", "group": "advanced",
     "options": ["square", "gaussian", "turbo", "lanczos2", "lanczos3"], "depends_on": "drizzle",
     "help": "Shape used to spread each pixel onto the output grid. Square is the robust "
             "default; Gaussian is smoother; Lanczos is sharpest but can ring around "
             "bright stars. Only used when Drizzle is on."},
    {"key": "quick_look_interval", "label": "Quick-look every N frames", "type": "int",
     "group": "advanced", "min": 0, "max": 1000, "step": 10,
     "help": "Save a preview every N frames during pass 1. 0 = off."},
    {"key": "save_progress", "label": "Save a “watch it appear” clip", "type": "bool",
     "group": "advanced",
     "help": "Keep a short looping animation of your picture coming together as frames "
             "stack, shown on the result. A fun beginner extra; off by default."},
    {"key": "record_rejection_map", "label": "Record what rejection removed",
     "type": "bool", "group": "advanced",
     "help": "Keep a map of where outlier rejection dropped samples, so the finished "
             "picture can show you the satellite trails and cosmic rays it cleaned out "
             "for you. Doesn't change a single pixel of the result — it only watches. "
             "Costs a little extra memory while stacking; off by default."},
    {"key": "max_workers", "label": "Max workers", "type": "int", "group": "advanced",
     "min": 1, "max": 64, "step": 1, "help": "Blank = all CPU cores."},
    {"key": "use_gpu", "label": "Use GPU (if available)", "type": "bool", "group": "advanced",
     "help": "Blank = auto-detect."},
]


def _dataclass_defaults() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in dataclasses.fields(StackOptions):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            out[f.name] = f.default_factory()  # type: ignore[misc]
        else:
            out[f.name] = None
    return out


# Project meta key under which per-target stacking defaults are stored. Shared
# by the stack router (read/write) and the pipeline (auto-stack reads it).
STACK_DEFAULTS_META_KEY = "web_stack_defaults"


def stack_option_fields() -> list[StackOptionField]:
    """The form schema, with defaults sourced from the dataclass."""
    defaults = _dataclass_defaults()
    fields: list[StackOptionField] = []
    for d in _DESCRIPTORS:
        d = dict(d)
        d.setdefault("default", defaults.get(d["key"]))
        fields.append(StackOptionField(**d))
    return fields


# StackOptions fields that are intentionally NOT user-facing form controls, so
# they have no descriptor. Two kinds, both server-owned:
#   * the calibration master *paths*, resolved server-side from master ids;
#   * ``unattended`` — the "nobody is watching this run" posture, written by
#     ``pipeline._stack_target`` after every option merge.
# Neither may ever be set from raw client input.
NON_FORM_KEYS = {"dark_path", "flat_path", "flat_dark_path", "bias_path",
                 "unattended"}


def describable_keys() -> set[str]:
    return {d["key"] for d in _DESCRIPTORS}


def strip_non_form_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Return *data* without any ``NON_FORM_KEYS`` (the calibration master paths
    and the ``unattended`` posture flag).

    Those paths are resolved server-side from master *ids* and must never
    originate from raw client input (a settings PUT body, a persisted global
    ``default_stack_options``). Callers that seed a StackOptions dict from a
    source that could carry client-supplied paths strip them with this first;
    legitimate server-resolved paths (from ``trigger_stack`` / auto-bind) are
    applied downstream, after the stripped base. ``unattended`` rides along for
    the same reason — it says whether anybody is watching the run, which only the
    server that started the job knows.
    """
    return {k: v for k, v in data.items() if k not in NON_FORM_KEYS}


def coerce_stack_options(data: dict[str, Any]) -> StackOptions:
    """Build a StackOptions from a (possibly partial) dict, ignoring unknowns.

    ``None`` means "use the dataclass default" (that is how
    :func:`validate_stack_options` treats it too). A cleared numeric field in the
    React form posts ``null`` (``StackOptionControl`` emits ``v === "" ? null``),
    which for a non-optional field like ``sigma_kappa: float`` would otherwise be
    written straight into the dataclass and blow up in the engine with a raw
    ``TypeError`` (``NoneType * float``). Dropping ``None`` here is also safe for
    the genuinely-optional fields (``max_workers``, ``dark_path`` …) whose default
    is itself ``None`` — dropping the key yields the identical value. This is the
    single choke point every stack path funnels through (form POST, per-target
    stack-defaults, the global ``default_stack_options``), so guarding it here
    protects them all — including the walk-away auto-stack.
    """
    valid = {f.name for f in dataclasses.fields(StackOptions)}
    clean = {k: v for k, v in data.items() if k in valid and v is not None}
    return StackOptions(**clean)


def validate_stack_options(data: dict[str, Any]) -> None:
    """Validate client-supplied stack-option *values* against the form descriptors.

    ``coerce_stack_options`` only drops unknown keys — it does **no** enum/range
    checking (``StackOptions`` is a plain dataclass), so a client bypassing the
    React form could send e.g. ``tiff_mode="garbage"`` or an out-of-range
    ``sigma_kappa``/``drizzle_scale`` and get a ``200 {job_id}`` back, only for the
    job to fail cryptically deep in the engine. Endpoints call this first and turn
    a ``ValueError`` into a plain-language ``400``.

    Raises ``ValueError`` on the first bad enum choice or out-of-range number.
    Unknown keys are ignored (coerce drops them); server-resolved calibration
    paths (``NON_FORM_KEYS``) and ``None`` values ("use default") are skipped.
    """
    fields = {f.key: f for f in stack_option_fields()}
    for key, value in data.items():
        if key in NON_FORM_KEYS or value is None:
            continue
        fld = fields.get(key)
        if fld is None:
            continue  # unknown key — coerce_stack_options ignores it
        if fld.type == "enum" and fld.options is not None:
            if value not in fld.options:
                raise ValueError(
                    f"{fld.label}: {value!r} is not a valid choice "
                    f"(expected one of {', '.join(map(str, fld.options))})")
        elif fld.type in ("int", "float"):
            # bool is a subclass of int — a checkbox value in a numeric field is wrong.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{fld.label}: expected a number, got {value!r}")
            # An ``int``-typed option must be a whole number. ``coerce_stack_options``
            # does no coercion (StackOptions is a plain dataclass), so a fractional
            # float (e.g. ``max_workers=3.5``) would otherwise slip through and reach
            # the engine as a float. An *integral* float (``3.0``) is fine.
            if fld.type == "int" and isinstance(value, float) and not value.is_integer():
                raise ValueError(
                    f"{fld.label}: expected a whole number, got {value!r}")
            if fld.min is not None and value < fld.min:
                raise ValueError(
                    f"{fld.label}: {value} is below the minimum of {fld.min}")
            if fld.max is not None and value > fld.max:
                raise ValueError(
                    f"{fld.label}: {value} is above the maximum of {fld.max}")


# ---------------------------------------------------------------------------
# Editor operation schema (adapts the engine's EditParam to StackOptionField so
# the frontend renders editor controls with the same machinery as stack options).
# ---------------------------------------------------------------------------


class EditOpOut(BaseModel):
    id: str
    label: str
    group: str
    stage: str
    proxy_safe: bool
    is_stretch: bool
    heavy: bool = False
    help: str | None = None
    params: list[StackOptionField]


def editor_ops_schema() -> list[EditOpOut]:
    from seestack.edit.registry import all_specs

    out: list[EditOpOut] = []
    for spec in all_specs():
        params = [
            StackOptionField(
                key=p.key, label=p.label, type=p.type, group=p.group,
                default=p.default, min=p.min, max=p.max, step=p.step,
                options=p.options, option_labels=p.option_labels,
                help=p.help, depends_on=p.depends_on,
            )
            for p in spec.params
        ]
        out.append(EditOpOut(
            id=spec.id, label=spec.label, group=spec.group, stage=spec.stage,
            proxy_safe=spec.proxy_safe, is_stretch=spec.is_stretch,
            heavy=spec.heavy, help=spec.help, params=params,
        ))
    return out
