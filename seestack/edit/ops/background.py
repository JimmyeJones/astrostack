"""Background & gradient operations — thin wrappers over existing seestack.bg code."""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, EditParam, OpSpec, register


def _scaled_box(ctx: EditContext, px: int, minimum: int = 16) -> int:
    """A full-res box/mesh size expressed in *this render's* pixels.

    ``box_size`` (and ``dilate_px``) are full-resolution pixel measures. On the
    decimated live-preview proxy a box of ``px`` full-res pixels covers
    ``proxy_scale`` times more of the scene, so the gradient mesh would be
    estimated at a coarser physical scale in the preview than in the export.
    Shrinking it by ``proxy_scale`` keeps the mesh at the same physical scale
    (preview↔export parity), floored so ``Background2D`` still gets a sane box
    with a few cells across the (small) proxy. On the export (``proxy_scale ==
    1``) this is a no-op, so the exported result is unchanged.
    """
    return max(minimum, round(ctx.scaled_px(px)))


def _subtract(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.bg.per_frame import BackgroundOptions, subtract_background

    opts = BackgroundOptions(
        box_size=_scaled_box(ctx, int(params.get("box_size", 128))),
        mode=str(params.get("mode", "per_channel")),
        enabled=True,
    )
    # for_image_size (called inside subtract_background) floors box_size further
    # for tiny images, so the mesh always tiles the proxy.
    # Pass an errors collector so a failed fit *surfaces* in the editor instead of
    # silently returning the input (or partially subtracting and colour-shifting).
    errors: list[str] = []
    out = subtract_background(rgb, opts, use_gpu=ctx.use_gpu, errors=errors)
    if errors:
        raise RuntimeError("; ".join(errors))
    return out


def _final_gradient(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.bg.final_gradient import FinalGradientOptions, remove_final_gradient

    opts = FinalGradientOptions(
        enabled=True,
        mode=str(params.get("mode", "luminance")),
        box_size=_scaled_box(ctx, int(params.get("box_size", 256))),
        detect_sigma=float(params.get("detect_sigma", 2.5)),
        # dilate_px is a full-res pixel measure too — scale it (floor 0 so a
        # small full-res dilation can legitimately vanish on a heavy proxy).
        dilate_px=_scaled_box(ctx, int(params.get("dilate_px", 16)), minimum=0),
    )
    # Surface a failed gradient fit in the editor rather than silently returning
    # the input (Background2D failure is this op's most likely real failure).
    errors: list[str] = []
    out = remove_final_gradient(rgb, opts, errors=errors)
    if errors:
        raise RuntimeError("; ".join(errors))
    return out


def _level_coverage(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    if ctx.coverage is None:
        return rgb  # nothing to level against (single-field image)
    # The coverage map is captured at the image's native geometry; if an earlier
    # geometry op (crop/rotate/resize) already changed the frame shape, we can't
    # align them, so skip rather than crash the whole render.
    if ctx.coverage.shape[:2] != rgb.shape[:2]:
        return rgb
    from seestack.bg.coverage_leveling import level_by_coverage

    # Pass the proxy scale so the per-level pixel-count floor is measured in
    # full-res-equivalent pixels: the live-preview proxy is strided, so without
    # this a mosaic panel would be leveled in the full-res export yet skipped in
    # the preview (a visible preview↔export panel-step mismatch).
    return level_by_coverage(rgb, ctx.coverage,
                             object_sigma=float(params.get("object_sigma", 2.0)),
                             proxy_scale=ctx.proxy_scale)


_MODE = ["per_channel", "luminance"]

register(OpSpec(
    id="background.subtract", label="Background subtract", group="background",
    stage="linear", apply=_subtract, proxy_safe=True,
    help="Subtract a per-tile sky model to flatten gradients and vignetting.",
    params=[
        EditParam("mode", "Mode", "enum", default="per_channel", options=_MODE,
                  option_labels={"per_channel": "Per channel", "luminance": "Luminance"},
                  help="Per channel for star fields; luminance for emission nebulae."),
        EditParam("box_size", "Box size", "int", default=128, min=32, max=512, step=16,
                  group="advanced",
                  help="Tile size (px) for the sky model. Larger follows only broad "
                       "gradients; smaller can over-fit and eat real signal."),
    ],
))

register(OpSpec(
    id="background.final_gradient", label="Gradient removal", group="background",
    stage="linear", apply=_final_gradient, proxy_safe=True,
    help="Object-masked gradient removal — protects stars/nebulosity while flattening sky.",
    params=[
        EditParam("mode", "Mode", "enum", default="luminance", options=_MODE,
                  option_labels={"per_channel": "Per channel", "luminance": "Luminance"},
                  help="Per channel corrects a colour cast in the gradient; luminance "
                       "flattens brightness only (safest for emission nebulae)."),
        EditParam("box_size", "Box size", "int", default=256, min=64, max=1024, step=32,
                  group="advanced",
                  help="Tile size (px) for the gradient model. Larger follows only "
                       "broad gradients; smaller can over-fit and eat real signal."),
        EditParam("detect_sigma", "Object σ", "float", default=2.5, min=1.0, max=6.0,
                  step=0.1, group="advanced",
                  help="How aggressively to mask off stars/nebulosity before fitting "
                       "the sky. Lower masks more; higher lets more into the fit."),
        EditParam("dilate_px", "Mask dilate (px)", "int", default=16, min=0, max=64, step=2,
                  group="advanced",
                  help="Grow the object mask by this many pixels so faint halos around "
                       "bright stars aren't treated as sky."),
    ],
))

register(OpSpec(
    id="background.level_coverage", label="Coverage leveling", group="background",
    stage="linear", apply=_level_coverage, proxy_safe=True,
    help="Equalize sky across mosaic panels with different frame coverage.",
    params=[
        EditParam("object_sigma", "Object σ", "float", default=2.0, min=1.0, max=5.0,
                  step=0.1, group="advanced",
                  help="How aggressively to mask off real signal before measuring each "
                       "panel's sky. Lower masks more; higher lets more into the estimate."),
    ],
))
