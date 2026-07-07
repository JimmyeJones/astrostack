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


# The noisy↔clean crossfade band (in the normalized sky-σ units analyze_proxy
# reports, centred on its 0.02 "noisy" verdict). Below _NOISE_LO the stack is
# treated as clean (sharpen only); above _NOISE_HI as noisy (denoise only); in
# between it gets *both*, crossfading, so two near-identical stacks either side
# of the old hard threshold no longer produce visibly different one-click results.
_NOISE_LO = 0.012
_NOISE_HI = 0.028


def _noise_fraction(sky_sigma: float) -> float:
    """Map the measured background σ to a 0..1 crossfade weight: 0 at/below the
    clean end (``_NOISE_LO``), 1 at/above the noisy end (``_NOISE_HI``), linear in
    between. Denoise fades *in* and sharpen fades *out* as this rises."""
    if _NOISE_HI <= _NOISE_LO:
        return 1.0 if sky_sigma > _NOISE_LO else 0.0
    return float(np.clip((sky_sigma - _NOISE_LO) / (_NOISE_HI - _NOISE_LO), 0.0, 1.0))


def auto_recipe(rgb: np.ndarray | None = None,
                median_fwhm: float | None = None,
                is_mosaic: bool = False,
                trim_crop: tuple[float, float, float, float] | None = None) -> Recipe:
    """One-click auto-process built from the image, not hardcoded.

    Always: background/gradient removal → photometric colour balance → a proper
    per-channel STF stretch (``tone.stretch`` mode ``stf``, the same algorithm as
    the proven ``autostretch``) → a gentle green-cast removal (SCNR) — the single
    most common OSC defect, which every built-in nebula preset also fixes. Then,
    only when warranted by the analysis: denoise (on linear data, before the
    stretch) at a *data-driven* strength scaled to the measured background noise,
    and a gentle sharpen sized to the target's *own* stars (median FWHM → radius,
    the same conversion the editor's sharpen-from-stars button uses). Rather than a
    hard noisy/clean switch (which made two near-identical stacks either side of the
    threshold produce visibly different results), the two *crossfade* across a band
    around the old threshold: a clean stack gets sharpen only, a very noisy one
    denoise only, and a mildly-noisy one a light touch of *both* — the denoise
    fading in and the sharpen fading out as the measured σ rises (see
    ``_noise_fraction``). Saturation lifts colour a touch at the end (after the
    green cast is gone, so it doesn't amplify it) — *scaled to the measured noise*
    so a noisy stack gets a gentler boost (less amplified chroma speckle) and a
    clean one the full lift. Finally a gentle **contrast curve** (``tone.curves``
    with ``auto=True``) is appended: like the built-in galaxy/nebula presets — but
    unlike the previously-flat general Auto recipe — it shapes the midtones, deriving
    a *data-driven* lift from its own stretched input at apply time (sky floor and
    highlight shoulder pinned on the identity, so it only gently lifts faint midtone
    structure without brightening the sky or blowing star cores).

    When ``is_mosaic`` is set (the stacker's authoritative union-canvas verdict,
    resolved by the caller), a ``background.level_coverage`` pass is prepended (on
    linear data, before the gradient fit) so uneven-overlap panel steps are
    equalised before anything else — the Seestar mosaic case, fixed without the
    user discovering the op. On a single-field stack it's skipped entirely, where
    it would be a no-op anyway.

    When ``trim_crop`` (fractional ``(x0, y0, x1, y1)`` bounds) is supplied — the
    largest well-covered rectangle of a mosaic's coverage map, from the same
    ``largest_covered_rect`` machinery the "Trim border" button uses — a
    ``geometry.crop`` to that rectangle is appended at the *end*, so the one-click
    result is cleanly framed instead of leaving the ragged, noisy low-coverage
    fringe of the union canvas. The caller passes it only for a mosaic where the
    trim is meaningful (``largest_covered_rect`` returns ``None`` on a full-frame
    result), so a single-field stack is never cropped. The crop runs last (after
    all tone/detail ops), which is safe and keeps the coverage-leveling op — which
    needs the native-geometry coverage map — operating on the uncropped frame.
    """
    target_bg = 0.20
    saturation = 1.2          # neutral fallback when the image can't be measured
    # Crossfade weights: an unmeasurable image is treated as clean (sharpen full,
    # no denoise) — matching the old boolean fallback.
    denoise_strength = 0.0
    sharpen_amount = 0.5
    if rgb is not None:
        a = analyze_proxy(rgb)
        sky_sigma = float(a["sky_sigma"])
        noise_frac = _noise_fraction(sky_sigma)
        # Darker sky → lift a little more (higher target grey), brighter → less.
        target_bg = float(np.clip(0.24 - a["sky"] * 0.4, 0.14, 0.24))
        # Chroma noise scales with the saturation boost, so ease off on a noisy
        # stack (where a strong boost just amplifies colour speckle) and give a
        # clean one the full lift — rather than the same fixed 1.2 for both.
        saturation = float(np.clip(1.25 - sky_sigma * 6.0, 1.05, 1.25))
        # Sharpen fades out as noise rises; denoise fades in. So a clean stack
        # (noise_frac 0) gets full sharpen and no denoise, a very noisy one
        # (noise_frac 1) full denoise and no sharpen — matching the old ends — and
        # a mildly-noisy one a light touch of both instead of an abrupt switch.
        sharpen_amount = round(0.5 * (1.0 - noise_frac), 3)
        if noise_frac > 0.0:
            # Match the denoise strength to the actual measured noise (the same
            # estimator behind the editor's "From your image" one-click), scaled by
            # the crossfade weight so it eases in across the band.
            from seestack.edit.noise import suggest_denoise_strength

            _, suggested = suggest_denoise_strength(rgb)
            base = suggested if suggested is not None else 0.5
            denoise_strength = round(base * noise_frac, 3)

    ops: list[tuple[str, dict]] = []
    if is_mosaic:
        # Equalise per-panel sky steps before the gradient fit — the coverage map
        # is loaded into the render context downstream, so on a single-field
        # export (no coverage) this op is a harmless no-op even if it slips in.
        ops.append(("background.level_coverage", {}))
    ops += [
        ("background.final_gradient", {"mode": "luminance"}),
        ("tone.color_calibrate", {"mode": "gray_star"}),
    ]
    # Denoise (linear, before the stretch) once the crossfade calls for a
    # meaningful amount; skip a sub-step sliver so a near-clean stack carries no
    # no-op op.
    if denoise_strength >= 0.05:
        ops.append(("detail.denoise", {"method": "wavelet", "strength": denoise_strength}))
    ops.append(("tone.stretch", {"mode": "stf", "target_bg": target_bg}))
    # SCNR before the saturation boost: cap the green channel to the R/B neutral
    # so the boost lifts real colour, not the residual OSC green cast. Gentle
    # (0.7) and monotone — it can only *reduce* excess green, never invent colour.
    ops.append(("tone.scnr", {"amount": 0.7}))
    ops.append(("tone.saturation", {"amount": round(saturation, 3)}))
    # A gentle contrast curve — the built-in galaxy/nebula presets ship an S-curve,
    # but the general Auto recipe was the flat exception (denoise → stretch → SCNR →
    # saturation → sharpen, no contrast shaping). `auto=True` + the identity default
    # points make tone.curves derive a *data-driven* midtone lift from its own
    # (stretched) input at apply time — so it adapts to the actual stack rather than
    # a fixed shape — and fall back to a fixed gentle S-curve when the data offers no
    # useful suggestion. It keeps the sky floor and highlight shoulder on the identity
    # (no sky brightening, no blown star cores), so it only ever *gently* lifts faint
    # midtone structure. Scout-vetted on realistic dim OSC stacks (2026-07-04).
    ops.append(("tone.curves", {"auto": True}))
    if sharpen_amount >= 0.05:  # sharpening clean data helps; noisy data hurts
        radius = _sharpen_radius_from_fwhm(median_fwhm)
        ops.append(("detail.sharpen", {"amount": sharpen_amount, "radius": radius}))
    # Trim the ragged, low-coverage mosaic border last (after tone/detail ops), so
    # the auto result is cleanly framed. Only supplied when the trim is meaningful.
    if trim_crop is not None:
        x0, y0, x1, y1 = trim_crop
        ops.append(("geometry.crop", {"x0": x0, "y0": y0, "x1": x1, "y1": y1}))
    return Recipe(ops=_ops(*ops))


def analyze_auto_inputs(
    rgb: np.ndarray | None = None,
    median_fwhm: float | None = None,
    is_mosaic: bool = False,
    trim_crop: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """The *measured cues* that drove the Auto recipe — the causal inputs behind
    each op, surfaced so the user sees Auto tuned itself to *their* data (not a
    fixed op list). Pure; reuses the exact same analysis ``auto_recipe`` consumes
    (``analyze_proxy`` + ``_noise_fraction`` + the FWHM→radius map + the trim
    rect), so the numbers reported here match the recipe it actually built.

    Every field is optional/nullable so it degrades gracefully: ``sky``/noise are
    ``None`` when the proxy can't be measured, ``median_fwhm`` is ``None`` when no
    solved stars gave a FWHM, and ``trim_fraction`` is ``None`` on a single-field
    (non-trimmed) stack. Values are rounded to the precision a UI would show.
    """
    out: dict[str, Any] = {
        "sky": None,
        "sky_sigma": None,
        "noisy": None,
        "noise_fraction": None,
        "median_fwhm": (round(float(median_fwhm), 2)
                        if median_fwhm is not None and median_fwhm > 0 else None),
        "sharpen_radius": None,
        "is_mosaic": bool(is_mosaic),
        "trim_fraction": None,
    }
    if rgb is not None:
        a = analyze_proxy(rgb)
        sky_sigma = float(a["sky_sigma"])
        out["sky"] = round(float(a["sky"]), 3)
        out["sky_sigma"] = round(sky_sigma, 4)
        out["noisy"] = bool(a["noisy"])
        out["noise_fraction"] = round(_noise_fraction(sky_sigma), 3)
    if median_fwhm is not None and median_fwhm > 0:
        # Only meaningful when a sharpen actually runs (clean/mildly-noisy data);
        # reported unconditionally here since it's the star size Auto *would* use.
        out["sharpen_radius"] = _sharpen_radius_from_fwhm(median_fwhm)
    if trim_crop is not None:
        x0, y0, x1, y1 = trim_crop
        kept = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        out["trim_fraction"] = round(max(0.0, 1.0 - kept), 3)
    return out
