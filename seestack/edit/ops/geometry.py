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
    x0f, x1f = sorted((min(max(float(params.get("x0", 0.0)), 0.0), 1.0),
                       min(max(float(params.get("x1", 1.0)), 0.0), 1.0)))
    y0f, y1f = sorted((min(max(float(params.get("y0", 0.0)), 0.0), 1.0),
                       min(max(float(params.get("y1", 1.0)), 0.0), 1.0)))
    # Decide "degenerate crop" in **full-resolution** pixels (proxy_scale-corrected)
    # so the crop/no-crop decision is identical on the decimated live-preview proxy
    # and the full-res export — the fractional-coordinate parity contract this
    # module documents. Evaluating ``< 2 px`` in *this render's* pixels let a tiny
    # fractional crop no-op on the small proxy while it still applied on the export
    # (or vice-versa), so the preview didn't match what was exported.
    scale = max(1.0, float(ctx.proxy_scale))
    if (x1f - x0f) * w * scale < 2.0 or (y1f - y0f) * h * scale < 2.0:
        return img  # degenerate crop — ignore (consistently on proxy and export)
    x0, x1 = int(round(x0f * w)), int(round(x1f * w))
    y0, y1 = int(round(y0f * h)), int(round(y1f * h))
    # A non-degenerate full-res crop can still round to < 1 px on a heavily
    # decimated proxy; keep at least 1 px per axis so the proxy slice is never
    # empty (an empty image crashes the PNG/export render) while still applying the
    # same crop the export does. A no-op on the export and on any real crop.
    x0 = min(x0, w - 1)
    y0 = min(y0, h - 1)
    x1 = max(x1, x0 + 1)
    y1 = max(y1, y0 + 1)
    return img[y0:y1, x0:x1].copy()


def _rotate(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import rotate

    angle = float(params.get("angle", 0.0))
    if abs(angle) < 1e-3:
        return rgb
    img = as_rgb(rgb)
    h, w = img.shape[:2]
    if h < 3 or w < 3:
        # Degenerate size: rotation's order-1 NaN border fill reaches ~1 px in from
        # every edge, so a frame with fewer than 3 px on an axis has no interior to
        # survive and comes back *entirely* NaN — turning a fully-covered image into
        # "no coverage" and breaking the NaN=coverage invariant. A sliver has no
        # meaningful orientation to change, so leave it untouched (mirroring the
        # <2 px guards on crop/resize/denoise). A no-op on any real ≥3 px image.
        return img
    return rotate(img, angle, axes=(0, 1), reshape=bool(params.get("expand", True)),
                  order=1, mode="constant", cval=np.nan).astype(np.float32)


def _resize(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import zoom

    scale = float(params.get("scale", 1.0))
    if abs(scale - 1.0) < 1e-3 or scale <= 0:
        return rgb
    img = as_rgb(rgb)
    h, w = img.shape[:2]
    # Keep each axis ≥ 1 px. A downscale of a thin frame (e.g. a sliver crop on
    # the proxy, or a small proxy) can drive round(dim·scale) to 0, which yields
    # an empty image that then crashes the PNG/export render ("cannot write empty
    # image"). Derive exact per-axis zoom factors from the guaranteed-nonzero
    # target shape so the output is always well-defined.
    out_h = max(1, int(round(h * scale)))
    out_w = max(1, int(round(w * scale)))
    if out_h == h and out_w == w:
        return rgb
    return zoom(img, (out_h / h, out_w / w, 1.0), order=1).astype(np.float32)


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
