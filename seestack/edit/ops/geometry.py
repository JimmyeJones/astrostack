"""Geometry operations: crop, rotate, resize.

Crop uses fractional coordinates (0..1) so the same recipe applies identically to
the preview proxy and the full-resolution export. Uncovered areas introduced by
rotation are filled with NaN (rendered black, consistent with mosaic gaps).
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, EditParam, OpSpec, as_rgb, register


def _crop(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    img = as_rgb(rgb)
    h, w = img.shape[:2]
    x0 = int(round(min(max(float(params.get("x0", 0.0)), 0.0), 1.0) * w))
    y0 = int(round(min(max(float(params.get("y0", 0.0)), 0.0), 1.0) * h))
    x1 = int(round(min(max(float(params.get("x1", 1.0)), 0.0), 1.0) * w))
    y1 = int(round(min(max(float(params.get("y1", 1.0)), 0.0), 1.0) * h))
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return img  # degenerate crop — ignore
    return img[y0:y1, x0:x1].copy()


def _rotate(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import rotate

    angle = float(params.get("angle", 0.0))
    if abs(angle) < 1e-3:
        return rgb
    img = as_rgb(rgb)
    return rotate(img, angle, axes=(0, 1), reshape=bool(params.get("expand", True)),
                  order=1, mode="constant", cval=np.nan).astype(np.float32)


def _resize(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import zoom

    scale = float(params.get("scale", 1.0))
    if abs(scale - 1.0) < 1e-3 or scale <= 0:
        return rgb
    img = as_rgb(rgb)
    return zoom(img, (scale, scale, 1.0), order=1).astype(np.float32)


# The reshape-the-canvas ops. A recipe's *enabled* members of this set are the
# only ops that move the coverage map (crop/rotate/resize); tone ops leave the
# geometry alone. Kept as a module constant so overlays can filter for them.
GEOMETRY_OP_IDS = ("geometry.crop", "geometry.rotate", "geometry.resize")


def apply_geometry_to_map(m: np.ndarray, recipe, ctx: EditContext) -> np.ndarray:
    """Apply a recipe's *enabled geometry ops* (crop/rotate/resize, in recipe
    order) to a 2-D single-channel map — e.g. the frame-coverage map — so an
    overlay of that map tracks the same crop/rotate/resize the edited image got.

    NaN = "uncovered" is preserved through the transform (crop copies, rotate fills
    exposed corners with NaN, resize interpolates), so gaps stay gaps. Non-geometry
    ops are ignored — only these three reshape the canvas. Returns a 2-D array whose
    shape matches the geometry-edited image's; the input is never mutated.
    """
    from seestack.edit.registry import get_op

    out = np.asarray(m, dtype=np.float32)
    for op in recipe.ops:
        if not op.enabled or op.id not in GEOMETRY_OP_IDS:
            continue
        spec = get_op(op.id)
        if spec is None:
            continue
        # The geometry ops operate on RGB; feed the map as three identical
        # channels, run the op, then take one channel back.
        rgb = np.stack([out, out, out], axis=-1)
        rgb = spec.apply(rgb, op.params, ctx)
        out = np.asarray(rgb, dtype=np.float32)[..., 0]
    return out


register(OpSpec(
    id="geometry.crop", label="Crop", group="stars_geometry", stage="nonlinear",
    apply=_crop, proxy_safe=True, help="Crop to a fractional rectangle (0..1).",
    params=[
        EditParam("x0", "Left", "float", default=0.0, min=0.0, max=1.0, step=0.01,
                  help="Left edge as a fraction of width. 0 = far left, 0.5 = centre."),
        EditParam("y0", "Top", "float", default=0.0, min=0.0, max=1.0, step=0.01,
                  help="Top edge as a fraction of height. 0 = very top."),
        EditParam("x1", "Right", "float", default=1.0, min=0.0, max=1.0, step=0.01,
                  help="Right edge as a fraction of width. 1 = far right."),
        EditParam("y1", "Bottom", "float", default=1.0, min=0.0, max=1.0, step=0.01,
                  help="Bottom edge as a fraction of height. 1 = very bottom."),
    ],
))

register(OpSpec(
    id="geometry.rotate", label="Rotate", group="stars_geometry", stage="nonlinear",
    apply=_rotate, proxy_safe=True, help="Rotate by an arbitrary angle.",
    params=[
        EditParam("angle", "Angle (°)", "float", default=0.0, min=-180.0, max=180.0,
                  step=0.5, help="Degrees to rotate, clockwise. Corners exposed by the "
                                 "rotation are left transparent (rendered black)."),
        EditParam("expand", "Expand canvas", "bool", default=True, group="advanced",
                  help="Grow the image to fit the whole rotated frame (nothing is lost; "
                       "exposed corners are transparent). Turn off to keep the original "
                       "size and let the rotated corners fall outside the frame."),
    ],
))

register(OpSpec(
    id="geometry.resize", label="Resize", group="stars_geometry", stage="nonlinear",
    apply=_resize, proxy_safe=True, help="Scale the image (1.0 = unchanged).",
    params=[EditParam("scale", "Scale", "float", default=1.0, min=0.1, max=2.0, step=0.05,
                      help="Resize factor. 1.0 = unchanged, 0.5 = half size, 2.0 = double. "
                           "Enlarging can't add real detail.")],
))
