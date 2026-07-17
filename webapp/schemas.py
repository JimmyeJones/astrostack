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


class TargetPatch(BaseModel):
    notes: str | None = None
    tags: list[str] | None = None


class FramingHintOut(BaseModel):
    """A "will it fit in one Seestar frame?" verdict for a matched target."""

    level: str  # "fits" | "tight" | "mosaic"
    text: str


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
    # A plain-language, beginner-friendly one-liner about the object ("what am I
    # looking at?"), for the popular targets; ``""`` when the catalog has none.
    # Old backends omit it, so the UI treats absent/empty as "no blurb".
    blurb: str = ""


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
    reject_buckets: dict[str, int] = {}
    quality_drift: SessionQualityDriftOut | None = None


class HealthNoteOut(BaseModel):
    """One plain-language "How's my stack?" note (see seestack.stackhealth)."""

    kind: str
    severity: str          # "good" | "info" — colour only, never alarming
    message: str
    action: str | None = None  # UI action key ("trim_border" | "calibration") or null


class StackHealthOut(BaseModel):
    """Ranked health notes for a target's current stack, or ``null`` when the
    target has no genuine stack yet. The card shows the top one or two."""

    run_id: int | None = None
    notes: list[HealthNoteOut] = []


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
             "transparency; leaves un-measured frames untouched."},
    {"key": "lucky_fraction", "label": "Lucky imaging (keep best %)", "type": "float",
     "group": "simple", "min": 0.05, "max": 1.0, "step": 0.05,
     "help": "Keep only the best fraction of frames by FWHM. 1.0 = keep all."},
    {"key": "drizzle", "label": "Drizzle (super-resolution)", "type": "bool", "group": "simple",
     "help": "Use the drizzle algorithm. Best with 200+ dithered frames."},
    {"key": "drizzle_reject", "label": "Drizzle outlier rejection", "type": "bool",
     "group": "simple", "depends_on": "drizzle",
     "help": "Second drizzle pass that rejects satellites, plane trails and cosmic "
             "rays (single-pass drizzle keeps them). Uses Sigma κ; needs 4+ frames. "
             "Takes roughly 2–3× as long."},
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


# StackOptions fields that are intentionally NOT user-facing form controls:
# the webapp resolves them server-side (calibration master paths) and they must
# never be set from raw client input, so they have no descriptor.
NON_FORM_KEYS = {"dark_path", "flat_path", "flat_dark_path", "bias_path"}


def describable_keys() -> set[str]:
    return {d["key"] for d in _DESCRIPTORS}


def strip_non_form_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Return *data* without any ``NON_FORM_KEYS`` (calibration master paths).

    Those paths are resolved server-side from master *ids* and must never
    originate from raw client input (a settings PUT body, a persisted global
    ``default_stack_options``). Callers that seed a StackOptions dict from a
    source that could carry client-supplied paths strip them with this first;
    legitimate server-resolved paths (from ``trigger_stack`` / auto-bind) are
    applied downstream, after the stripped base.
    """
    return {k: v for k, v in data.items() if k not in NON_FORM_KEYS}


def coerce_stack_options(data: dict[str, Any]) -> StackOptions:
    """Build a StackOptions from a (possibly partial) dict, ignoring unknowns."""
    valid = {f.name for f in dataclasses.fields(StackOptions)}
    clean = {k: v for k, v in data.items() if k in valid}
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
