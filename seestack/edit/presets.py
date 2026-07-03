"""Built-in object-type presets + the one-click Auto-process recipe.

A preset is a recipe fragment (ordered ops). Applying a preset replaces the working
recipe. User-saved presets live in library meta; these built-ins ship with the code.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from seestack.edit.recipe import OpInstance, Recipe, validate_ops

# Gaussian FWHM → σ, and the sharpen op's radius bounds/step (kept in step with
# the EditParam in seestack/edit/ops/detail.py). A good unsharp-mask radius is on
# the scale of the star's own blur (its Gaussian σ), so the median star FWHM is
# the natural data-driven default — the same conversion the editor's
# sharpen-from-stars button uses.
_FWHM_TO_SIGMA = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))  # ≈ 0.4247
_SHARPEN_RADIUS_MIN = 0.5
_SHARPEN_RADIUS_MAX = 10.0
_SHARPEN_RADIUS_STEP = 0.5


def _sharpen_radius_from_fwhm(median_fwhm: float | None) -> float:
    """Map a target's median star FWHM to an unsharp-mask radius (≈ the star's
    Gaussian σ), clamped to the op's slider range and rounded to its step.
    Falls back to the op's 2.0 default when no FWHM is available."""
    if median_fwhm is None or median_fwhm <= 0:
        return 2.0
    raw = median_fwhm * _FWHM_TO_SIGMA
    radius = max(_SHARPEN_RADIUS_MIN, min(_SHARPEN_RADIUS_MAX, raw))
    return round(round(radius / _SHARPEN_RADIUS_STEP) * _SHARPEN_RADIUS_STEP, 2)


def _ops(*pairs: tuple[str, dict]) -> list[OpInstance]:
    return validate_ops([OpInstance(id=i, params=p) for i, p in pairs])


# Each: id -> {label, group, ops}
BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "galaxy_broadband": {
        "label": "Galaxy (broadband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "per_channel"}),
            ("tone.color_calibrate", {"mode": "gray_star"}),
            ("tone.stretch", {"mode": "stf", "target_bg": 0.18}),
            ("tone.curves", {"points": [[0, 0], [0.25, 0.2], [0.75, 0.82], [1, 1]]}),
            ("tone.saturation", {"amount": 1.25}),
            ("detail.sharpen", {"amount": 0.6, "radius": 2.0}),
        ),
    },
    "nebula_broadband": {
        "label": "Nebula (broadband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "luminance"}),
            ("tone.color_calibrate", {"mode": "gray_star"}),
            ("tone.stretch", {"mode": "stf", "target_bg": 0.22}),
            ("tone.scnr", {"amount": 0.8}),
            ("tone.saturation", {"amount": 1.35}),
        ),
    },
    "nebula_narrowband": {
        "label": "Nebula (narrowband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "luminance"}),
            ("tone.stretch", {"mode": "stf", "target_bg": 0.25}),
            ("tone.scnr", {"amount": 0.6}),
            ("tone.curves", {"points": [[0, 0], [0.3, 0.28], [0.8, 0.86], [1, 1]]}),
            ("tone.saturation", {"amount": 1.15}),
        ),
    },
    "globular_cluster": {
        "label": "Star cluster", "group": "Built-in",
        "ops": _ops(
            ("background.subtract", {"mode": "per_channel"}),
            ("tone.color_calibrate", {"mode": "gray_star"}),
            ("tone.stretch", {"mode": "asinh", "stretch": 0.45, "black": 0.45}),
            ("stars.reduce", {"amount": 0.3, "size": 2}),
            ("tone.saturation", {"amount": 1.2}),
        ),
    },
}


def preset_recipe(preset_id: str) -> Recipe | None:
    p = BUILTIN_PRESETS.get(preset_id)
    if p is None:
        return None
    return Recipe(ops=[OpInstance(id=o.id, params=dict(o.params)) for o in p["ops"]])


def analyze_proxy(rgb: np.ndarray) -> dict[str, Any]:
    """Cheap content analysis of a proxy used to tailor the auto recipe:
    sky level, sky-noise fraction, and a coarse 'noisy' verdict.

    Stats are computed on the whole-image-normalized luminance over the *sky*
    side only (pixels at/below the robust median), so bright stars/targets don't
    masquerade as noise.
    """
    arr = np.asarray(rgb, dtype=np.float32)
    lum = arr[..., :3].mean(axis=2) if arr.ndim == 3 else arr
    finite = lum[np.isfinite(lum)]
    if finite.size < 16:
        return {"sky": 0.1, "sky_sigma": 0.0, "noisy": False}
    lo, hi = float(np.nanpercentile(finite, 0.5)), float(np.nanpercentile(finite, 99.5))
    if hi <= lo:
        return {"sky": 0.1, "sky_sigma": 0.0, "noisy": False}
    norm = np.clip((finite - lo) / (hi - lo), 0.0, 1.0)
    med = float(np.median(norm))
    sky = norm[norm <= med]                       # the sky population
    if sky.size:
        sky_sigma = float(1.4826 * np.median(np.abs(sky - np.median(sky))))
    else:
        sky_sigma = 0.0
    return {"sky": med, "sky_sigma": sky_sigma, "noisy": sky_sigma > 0.02}


def _is_mosaic(coverage_span: tuple[int, int] | None) -> bool:
    """A mosaic stack has uneven panel overlap, so its per-pixel frame coverage
    spans a range (``coverage_max > coverage_min``); a single-field stack has
    uniform coverage (max == min), where coverage-leveling is a deliberate no-op.
    ``None`` (unknown) is treated as single-field so the recipe is unchanged."""
    if coverage_span is None:
        return False
    lo, hi = coverage_span
    return hi > lo


def auto_recipe(rgb: np.ndarray | None = None,
                median_fwhm: float | None = None,
                coverage_span: tuple[int, int] | None = None) -> Recipe:
    """One-click auto-process built from the image, not hardcoded.

    Always: background/gradient removal → photometric colour balance → a proper
    per-channel STF stretch (``tone.stretch`` mode ``stf``, the same algorithm as
    the proven ``autostretch``) → a gentle green-cast removal (SCNR) — the single
    most common OSC defect, which every built-in nebula preset also fixes. Then,
    only when warranted by the analysis: denoise (on linear data, before the
    stretch) for noisy frames — at a *data-driven* strength scaled to the
    measured background noise, not a fixed guess — and a gentle sharpen for clean
    ones, sized to the target's *own* stars (median FWHM → radius, the same
    conversion the editor's sharpen-from-stars button uses) rather than a fixed
    guess. Saturation lifts colour a touch at the end (after the green cast is
    gone, so it doesn't amplify it) — *scaled to the measured background noise*
    so a noisy stack gets a gentler boost (less amplified chroma speckle) and a
    clean one the full lift.

    When ``coverage_span`` marks a mosaic (``coverage_max > coverage_min``), a
    ``background.level_coverage`` pass is prepended (on linear data, before the
    gradient fit) so uneven-overlap panel steps are equalised before anything
    else — the Seestar mosaic case, fixed without the user discovering the op.
    On a single-field stack (uniform coverage) it's skipped entirely, where it
    would be a no-op anyway.
    """
    noisy = False
    target_bg = 0.20
    denoise_strength = 0.5  # neutral fallback when the image can't be measured
    saturation = 1.2        # neutral fallback when the image can't be measured
    if rgb is not None:
        a = analyze_proxy(rgb)
        noisy = bool(a["noisy"])
        # Darker sky → lift a little more (higher target grey), brighter → less.
        target_bg = float(np.clip(0.24 - a["sky"] * 0.4, 0.14, 0.24))
        # Chroma noise scales with the saturation boost, so ease off on a noisy
        # stack (where a strong boost just amplifies colour speckle) and give a
        # clean one the full lift — rather than the same fixed 1.2 for both.
        saturation = float(np.clip(1.25 - a["sky_sigma"] * 6.0, 1.05, 1.25))
        if noisy:
            # Match the denoise strength to the actual measured noise (the same
            # estimator behind the editor's "From your image" one-click), so a
            # mildly-noisy stack gets a light touch and a very noisy one more —
            # rather than always the same 0.5.
            from seestack.edit.noise import suggest_denoise_strength

            _, suggested = suggest_denoise_strength(rgb)
            if suggested is not None:
                denoise_strength = suggested

    ops: list[tuple[str, dict]] = []
    if _is_mosaic(coverage_span):
        # Equalise per-panel sky steps before the gradient fit — the coverage map
        # is loaded into the render context downstream, so on a single-field
        # export (no coverage) this op is a harmless no-op even if it slips in.
        ops.append(("background.level_coverage", {}))
    ops += [
        ("background.final_gradient", {"mode": "luminance"}),
        ("tone.color_calibrate", {"mode": "gray_star"}),
    ]
    if noisy:  # denoise belongs on LINEAR data, before the stretch
        ops.append(("detail.denoise", {"method": "wavelet", "strength": denoise_strength}))
    ops.append(("tone.stretch", {"mode": "stf", "target_bg": target_bg}))
    # SCNR before the saturation boost: cap the green channel to the R/B neutral
    # so the boost lifts real colour, not the residual OSC green cast. Gentle
    # (0.7) and monotone — it can only *reduce* excess green, never invent colour.
    ops.append(("tone.scnr", {"amount": 0.7}))
    ops.append(("tone.saturation", {"amount": round(saturation, 3)}))
    if not noisy:  # sharpening clean data helps; sharpening noisy data hurts
        radius = _sharpen_radius_from_fwhm(median_fwhm)
        ops.append(("detail.sharpen", {"amount": 0.5, "radius": radius}))
    return Recipe(ops=_ops(*ops))
