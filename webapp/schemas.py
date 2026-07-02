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
    help: str | None = None
    # When set, the field is only relevant if another bool field is true.
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
    {"key": "background_flatten", "label": "Background flatten", "type": "bool", "group": "simple",
     "help": "Subtract a per-frame sky model to remove gradients."},
    {"key": "quality_weighted", "label": "Quality weighting", "type": "bool", "group": "simple",
     "help": "Weight sharper / clearer frames more heavily."},
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
     "options": ["per_channel", "luminance"], "depends_on": "background_flatten"},
    {"key": "background_box_size", "label": "Background box size", "type": "int",
     "group": "advanced", "min": 32, "max": 512, "step": 16, "depends_on": "background_flatten"},
    {"key": "suppress_hot_pixels", "label": "Hot-pixel suppression", "type": "bool",
     "group": "advanced"},
    {"key": "hot_pixel_sigma", "label": "Hot-pixel σ", "type": "float", "group": "advanced",
     "min": 2.0, "max": 10.0, "step": 0.5, "depends_on": "suppress_hot_pixels"},
    {"key": "subpixel_refine", "label": "Sub-pixel alignment refine", "type": "bool",
     "group": "advanced"},
    {"key": "final_gradient_removal", "label": "Final gradient removal", "type": "bool",
     "group": "advanced", "help": "Post-stack gradient removal with object masking."},
    {"key": "final_gradient_mode", "label": "Final gradient mode", "type": "enum",
     "group": "advanced", "options": ["per_channel", "luminance"],
     "depends_on": "final_gradient_removal"},
    {"key": "final_gradient_box_size", "label": "Final gradient box size", "type": "int",
     "group": "advanced", "min": 64, "max": 1024, "step": 32,
     "depends_on": "final_gradient_removal"},
    {"key": "color_calibration", "label": "Color calibration", "type": "bool", "group": "advanced"},
    {"key": "color_calibration_mode", "label": "Color cal. mode", "type": "enum",
     "group": "advanced", "options": ["gray_star", "gaia"], "depends_on": "color_calibration"},
    {"key": "mosaic_canvas", "label": "Canvas mode", "type": "enum", "group": "advanced",
     "options": ["auto", "union", "reference"]},
    {"key": "tiff_mode", "label": "TIFF mode", "type": "enum", "group": "advanced",
     "options": ["linear", "autostretch"]},
    {"key": "drizzle_pixfrac", "label": "Drizzle pixfrac", "type": "float", "group": "advanced",
     "min": 0.1, "max": 1.0, "step": 0.05, "depends_on": "drizzle"},
    {"key": "drizzle_scale", "label": "Drizzle scale", "type": "float", "group": "advanced",
     "min": 1.0, "max": 4.0, "step": 0.1, "depends_on": "drizzle"},
    {"key": "drizzle_kernel", "label": "Drizzle kernel", "type": "enum", "group": "advanced",
     "options": ["square", "gaussian", "turbo", "lanczos2", "lanczos3"], "depends_on": "drizzle"},
    {"key": "quick_look_interval", "label": "Quick-look every N frames", "type": "int",
     "group": "advanced", "min": 0, "max": 1000, "step": 10,
     "help": "Save a preview every N frames during pass 1. 0 = off."},
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
NON_FORM_KEYS = {"dark_path", "flat_path", "flat_dark_path"}


def describable_keys() -> set[str]:
    return {d["key"] for d in _DESCRIPTORS}


def coerce_stack_options(data: dict[str, Any]) -> StackOptions:
    """Build a StackOptions from a (possibly partial) dict, ignoring unknowns."""
    valid = {f.name for f in dataclasses.fields(StackOptions)}
    clean = {k: v for k, v in data.items() if k in valid}
    return StackOptions(**clean)


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
                options=p.options, help=p.help, depends_on=p.depends_on,
            )
            for p in spec.params
        ]
        out.append(EditOpOut(
            id=spec.id, label=spec.label, group=spec.group, stage=spec.stage,
            proxy_safe=spec.proxy_safe, is_stretch=spec.is_stretch,
            help=spec.help, params=params,
        ))
    return out
