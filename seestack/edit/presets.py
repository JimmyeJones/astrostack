"""Built-in object-type presets + the one-click Auto-process recipe.

A preset is a recipe fragment (ordered ops). Applying a preset replaces the working
recipe. User-saved presets live in library meta; these built-ins ship with the code.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from seestack.edit.recipe import OpInstance, Recipe, validate_ops


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


def auto_recipe(rgb: np.ndarray | None = None) -> Recipe:
    """One-click auto-process built from the image, not hardcoded.

    Always: background/gradient removal → photometric colour balance → a proper
    per-channel STF stretch (``tone.stretch`` mode ``stf``, the same algorithm as
    the proven ``autostretch``). Then, only when warranted by the analysis:
    denoise (on linear data, before the stretch) for noisy frames, and a gentle
    sharpen for clean ones. Saturation lifts colour a touch at the end.
    """
    noisy = False
    target_bg = 0.20
    if rgb is not None:
        a = analyze_proxy(rgb)
        noisy = bool(a["noisy"])
        # Darker sky → lift a little more (higher target grey), brighter → less.
        target_bg = float(np.clip(0.24 - a["sky"] * 0.4, 0.14, 0.24))

    ops: list[tuple[str, dict]] = [
        ("background.final_gradient", {"mode": "luminance"}),
        ("tone.color_calibrate", {"mode": "gray_star"}),
    ]
    if noisy:  # denoise belongs on LINEAR data, before the stretch
        ops.append(("detail.denoise", {"method": "wavelet", "strength": 0.5}))
    ops.append(("tone.stretch", {"mode": "stf", "target_bg": target_bg}))
    ops.append(("tone.saturation", {"amount": 1.2}))
    if not noisy:  # sharpening clean data helps; sharpening noisy data hurts
        ops.append(("detail.sharpen", {"amount": 0.5, "radius": 2.0}))
    return Recipe(ops=_ops(*ops))
