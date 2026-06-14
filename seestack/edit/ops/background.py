"""Background & gradient operations — thin wrappers over existing seestack.bg code."""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, EditParam, OpSpec, register


def _subtract(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.bg.per_frame import BackgroundOptions, subtract_background

    opts = BackgroundOptions(
        box_size=int(params.get("box_size", 128)),
        mode=str(params.get("mode", "per_channel")),
        enabled=True,
    )
    return subtract_background(rgb, opts, use_gpu=ctx.use_gpu)


def _final_gradient(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.bg.final_gradient import FinalGradientOptions, remove_final_gradient

    opts = FinalGradientOptions(
        enabled=True,
        mode=str(params.get("mode", "luminance")),
        box_size=int(params.get("box_size", 256)),
        detect_sigma=float(params.get("detect_sigma", 2.5)),
        dilate_px=int(params.get("dilate_px", 16)),
    )
    return remove_final_gradient(rgb, opts)


def _level_coverage(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    if ctx.coverage is None:
        return rgb  # nothing to level against (single-field image)
    from seestack.bg.coverage_leveling import level_by_coverage

    return level_by_coverage(rgb, ctx.coverage,
                             object_sigma=float(params.get("object_sigma", 2.0)))


_MODE = ["per_channel", "luminance"]

register(OpSpec(
    id="background.subtract", label="Background subtract", group="background",
    stage="linear", apply=_subtract, proxy_safe=True,
    help="Subtract a per-tile sky model to flatten gradients and vignetting.",
    params=[
        EditParam("mode", "Mode", "enum", default="per_channel", options=_MODE,
                  help="per_channel for star fields; luminance for emission nebulae."),
        EditParam("box_size", "Box size", "int", default=128, min=32, max=512, step=16,
                  group="advanced"),
    ],
))

register(OpSpec(
    id="background.final_gradient", label="Gradient removal", group="background",
    stage="linear", apply=_final_gradient, proxy_safe=True,
    help="Object-masked gradient removal — protects stars/nebulosity while flattening sky.",
    params=[
        EditParam("mode", "Mode", "enum", default="luminance", options=_MODE),
        EditParam("box_size", "Box size", "int", default=256, min=64, max=1024, step=32,
                  group="advanced"),
        EditParam("detect_sigma", "Object σ", "float", default=2.5, min=1.0, max=6.0,
                  step=0.1, group="advanced"),
        EditParam("dilate_px", "Mask dilate (px)", "int", default=16, min=0, max=64, step=2,
                  group="advanced"),
    ],
))

register(OpSpec(
    id="background.level_coverage", label="Coverage leveling", group="background",
    stage="linear", apply=_level_coverage, proxy_safe=True,
    help="Equalize sky across mosaic panels with different frame coverage.",
    params=[
        EditParam("object_sigma", "Object σ", "float", default=2.0, min=1.0, max=5.0,
                  step=0.1, group="advanced"),
    ],
))
