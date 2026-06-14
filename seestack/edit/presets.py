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
            ("tone.stretch", {"mode": "asinh", "stretch": 0.55, "black": 0.4}),
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
            ("tone.stretch", {"mode": "asinh", "stretch": 0.7, "black": 0.42}),
            ("tone.scnr", {"amount": 0.8}),
            ("tone.saturation", {"amount": 1.35}),
        ),
    },
    "nebula_narrowband": {
        "label": "Nebula (narrowband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "luminance"}),
            ("tone.stretch", {"mode": "asinh", "stretch": 0.78, "black": 0.45}),
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


def auto_recipe(rgb: np.ndarray | None = None) -> Recipe:
    """A sensible one-click recipe. If a proxy is supplied, lightly adapt the
    stretch black point to the image's sky level; otherwise use safe defaults."""
    black = 0.4
    strength = 0.6
    if rgb is not None:
        arr = np.asarray(rgb, dtype=np.float32)
        lum = arr[..., :3].mean(axis=2) if arr.ndim == 3 else arr
        finite = lum[np.isfinite(lum)]
        if finite.size:
            lo, hi = float(np.nanmin(finite)), float(np.nanmax(finite))
            if hi > lo:
                norm = (finite - lo) / (hi - lo)
                med = float(np.median(norm))
                # Brighter sky → push black up a touch; fainter target → stronger lift.
                black = float(np.clip(0.3 + med * 1.5, 0.3, 0.55))
                strength = float(np.clip(0.5 + (0.05 / max(med, 1e-3)) * 0.0 + 0.2, 0.5, 0.75))
    return Recipe(ops=_ops(
        ("background.final_gradient", {"mode": "luminance"}),
        ("tone.color_calibrate", {"mode": "gray_star"}),
        ("tone.stretch", {"mode": "asinh", "stretch": strength, "black": black}),
        ("detail.denoise", {"method": "wavelet", "strength": 0.35}),
        ("tone.saturation", {"amount": 1.2}),
        ("detail.sharpen", {"amount": 0.5, "radius": 2.0}),
    ))
