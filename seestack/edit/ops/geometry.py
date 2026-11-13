"""Geometry operations: crop, rotate, resize.

Crop uses fractional coordinates (0..1) so the same recipe applies identically to
the preview proxy and the full-resolution export. Uncovered areas introduced by
rotation are filled with NaN (rendered black, consistent with mosaic gaps).
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, EditParam, OpSpec, as_rgb, register


def crop_bounds(h: int, w: int, params: dict,
                proxy_scale: float = 1.0) -> tuple[int, int, int, int] | None:
    """The pixel rectangle ``(x0, x1, y0, y1)`` a crop op takes out of an
    ``h × w`` image, or ``None`` when the crop is degenerate and the op is a no-op.

    Split out of :func:`_crop` so anything that has to *replay* the crop in pixel
    space — the WCS carried onto an editor export, say — derives the same numbers
    from the same code rather than from a second copy of this arithmetic that can
    drift away from it.
    """
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
    scale = max(1.0, float(proxy_scale))
    if (x1f - x0f) * w * scale < 2.0 or (y1f - y0f) * h * scale < 2.0:
        return None  # degenerate crop — ignore (consistently on proxy and export)
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
    return x0, x1, y0, y1


def _crop(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    img = as_rgb(rgb)
    h, w = img.shape[:2]
    box = crop_bounds(h, w, params, ctx.proxy_scale)
    if box is None:
        return img
    x0, x1, y0, y1 = box
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
    # ``rotate`` already returns float32 for float32 input; ``copy=False`` keeps
    # the cast from duplicating the whole rotated canvas on a mosaic export
    # (tests/test_edit_geometry_memory.py — peak was 2.0× the result).
    return rotate(img, angle, axes=(0, 1), reshape=bool(params.get("expand", True)),
                  order=1, mode="constant", cval=np.nan).astype(np.float32, copy=False)


def resize_shape(h: int, w: int, params: dict) -> tuple[int, int] | None:
    """The ``(out_h, out_w)`` a resize op produces from an ``h × w`` image, or
    ``None`` when the op is a no-op. Split out of :func:`_resize` for the same
    reason as :func:`crop_bounds` — one copy of the arithmetic, no drift.
    """
    scale = float(params.get("scale", 1.0))
    if abs(scale - 1.0) < 1e-3 or scale <= 0:
        return None
    # Keep each axis ≥ 1 px. A downscale of a thin frame (e.g. a sliver crop on
    # the proxy, or a small proxy) can drive round(dim·scale) to 0, which yields
    # an empty image that then crashes the PNG/export render ("cannot write empty
    # image"). Derive exact per-axis zoom factors from the guaranteed-nonzero
    # target shape so the output is always well-defined.
    out_h = max(1, int(round(h * scale)))
    out_w = max(1, int(round(w * scale)))
    if out_h == h and out_w == w:
        return None
    return out_h, out_w


def _resize(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from scipy.ndimage import zoom

    img = as_rgb(rgb)
    h, w = img.shape[:2]
    shape = resize_shape(h, w, params)
    if shape is None:
        return rgb
    out_h, out_w = shape
    zy, zx = out_h / h, out_w / w
    if zy < 1.0 or zx < 1.0:
        # Shrinking: low-pass each channel before it is resampled, one plane at
        # a time, so a mosaic-sized export holds a few planes extra, never a
        # second full RGB copy.
        out = np.empty((out_h, out_w, img.shape[2]), dtype=np.float32)
        for c in range(img.shape[2]):
            out[..., c] = zoom(_antialias_for_shrink(img[..., c], zy, zx),
                               (zy, zx), order=1)
        return out
    # As in _rotate: the enlarged result is already float32, so don't copy it.
    return zoom(img, (zy, zx, 1.0), order=1).astype(np.float32, copy=False)


def _antialias_for_shrink(plane: np.ndarray, zy: float, zx: float) -> np.ndarray:
    """Low-pass one channel before a downscale by ``(zy, zx)`` so the resample
    *averages* the pixels it drops instead of skipping them.

    A bare order-1 ``zoom`` lands each output pixel on (nearly) one input
    pixel, so shrinking a picture point-samples it: measured at 0.25× the sky
    noise came out 2.7× what a real downscale gives (no smoother than full
    size), and a star's brightness swung by ±41 % with its sub-pixel phase —
    some all but vanished. That is not what "0.5 = half size" promises.

    The blur is the standard anti-alias width ``σ = (1/zoom − 1) / 2`` per axis
    (scikit-image's ``rescale`` default), and **NaN-aware**: a normalised
    convolution weights only covered pixels, so a mosaic's uncovered border
    never darkens the sky next to it, and every pixel that was NaN is NaN again
    afterwards — the gap ``zoom`` then sees is exactly the gap it saw before,
    and "NaN = no coverage" holds. Sized from the zoom alone, so the decimated
    preview proxy and the full-resolution export are each smoothed relative to
    their own grid, the way every other pixel-scaled op keeps them in step.
    """
    from scipy.ndimage import gaussian_filter

    plane = np.asarray(plane, dtype=np.float32)
    sigma = (max(0.0, (1.0 / zy - 1.0) / 2.0), max(0.0, (1.0 / zx - 1.0) / 2.0))
    if max(sigma) <= 0.0:
        return plane
    covered = np.isfinite(plane)
    if covered.all():
        return gaussian_filter(plane, sigma=sigma, mode="nearest")
    smoothed = gaussian_filter(np.where(covered, plane, np.float32(0.0)),
                               sigma=sigma, mode="nearest")
    weight = gaussian_filter(covered.astype(np.float32), sigma=sigma, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        smoothed /= weight
    smoothed[~covered] = np.nan
    return smoothed


# The reshape-the-canvas ops. A recipe's *enabled* members of this set are the
# only ops that move the coverage map (crop/rotate/resize); tone ops leave the
# geometry alone. Kept as a module constant so overlays can filter for them.
GEOMETRY_OP_IDS = ("geometry.crop", "geometry.rotate", "geometry.resize")


def reshapes_frame(op_id: str, params: dict | None) -> bool:
    """Whether an *enabled* geometry op really moves pixels, from its params alone.

    Each of the three ops carries its own "this is a no-op" guard — :func:`_crop`
    ignores a degenerate or whole-frame rectangle, :func:`_rotate` returns the
    image below ~1e-3°, :func:`_resize` returns it at scale 1.0 — and every one of
    those guards fires on the op's **own defaults**: a Crop, Rotate or Resize
    fresh from the editor's Add menu reshapes nothing until the user aims it. So
    anything that reads "the recipe has an enabled geometry op" as "the frame has
    been reshaped" is wrong about exactly the op a beginner is most likely to be
    holding, and switches itself off naming a crop or resize the recipe does not
    have.

    **Conservative, and shape-free.** It answers from the params only, so it says
    "reshapes" for anything it cannot be certain of at *every* canvas size — a
    crop too thin to survive :func:`crop_bounds`' 2-px floor, a resize that rounds
    back to the same pixels, a rotate of a sliver, a value that will not parse.
    Each of those keeps today's answer; only the certain no-ops change. A caller
    can therefore only ever gain a correct offer, never lose a correct refusal.

    Mirrored in TypeScript by ``cropDrag.ts::geometryOpReshapesFrame`` for the
    editor's drag-to-crop refusal; change the two together.
    """
    if op_id not in GEOMETRY_OP_IDS:
        return False
    if not isinstance(params, dict):
        return True  # a hand-edited recipe: assume it reshapes
    if op_id == "geometry.rotate":
        try:
            angle = float(params.get("angle", 0.0))
        except (TypeError, ValueError):
            return True
        return not abs(angle) < 1e-3          # _rotate's own branch, verbatim
    if op_id == "geometry.resize":
        try:
            scale = float(params.get("scale", 1.0))
        except (TypeError, ValueError):
            return True
        return not (abs(scale - 1.0) < 1e-3 or scale <= 0)   # resize_shape's
    # geometry.crop. ``make_crop`` applies the same clamp/sort and the same
    # "ignore a degenerate rectangle" rule :func:`crop_bounds` does, and a
    # whole-frame rectangle crops nothing — the pair of tests
    # ``preview_crop_of_recipe`` already uses, reached through the one
    # implementation rather than a second copy of the arithmetic.
    from seestack.previewcrop import make_crop

    crop = make_crop(params.get("x0", 0.0), params.get("y0", 0.0),
                     params.get("x1", 1.0), params.get("y1", 1.0))
    return crop is not None and not crop.is_full


def geometry_pixel_steps(recipe, shape: tuple[int, int],
                         proxy_scale: float = 1.0) -> list[tuple] | None:
    """Replay a recipe's *enabled geometry ops* as pixel-space steps, so a caller
    holding the source image's WCS can move it onto the edited canvas.

    Returns a list of steps — ``("crop", x0, y0)`` and
    ``("resize", in_w, in_h, out_w, out_h)`` — in recipe order, using the very
    same :func:`crop_bounds` / :func:`resize_shape` the ops themselves use; an op
    that is a no-op on this image contributes no step. Returns ``None`` when a
    step **cannot** be expressed this way, which today means an active rotate:
    it resamples the picture onto a grid the source solution no longer describes,
    and a plausible-looking wrong WCS is worse than none (every consumer —
    North-up, the scale bar, the compass, object labels — would then be quietly
    off). ``shape`` is the ``(h, w)`` the recipe starts from.
    """
    h, w = int(shape[0]), int(shape[1])
    steps: list[tuple] = []
    for op in recipe.ops:
        if not op.enabled or op.id not in GEOMETRY_OP_IDS:
            continue
        if op.id == "geometry.rotate":
            # Mirror _rotate's own no-op guards: an angle below its threshold, or
            # a sliver too small to rotate, leaves the pixels (and so the WCS)
            # exactly as they were.
            if abs(float(op.params.get("angle", 0.0))) < 1e-3 or h < 3 or w < 3:
                continue
            return None
        if op.id == "geometry.crop":
            box = crop_bounds(h, w, op.params, proxy_scale)
            if box is None:
                continue
            x0, x1, y0, y1 = box
            steps.append(("crop", x0, y0))
            h, w = y1 - y0, x1 - x0
        else:  # geometry.resize
            out = resize_shape(h, w, op.params)
            if out is None:
                continue
            out_h, out_w = out
            steps.append(("resize", w, h, out_w, out_h))
            h, w = out_h, out_w
    return steps


def rotated_shape(h: int, w: int, params: dict) -> tuple[int, int] | None:
    """The ``(out_h, out_w)`` :func:`_rotate` produces from an ``h × w`` image, or
    ``None`` when the op leaves the image as it is.

    ``expand`` off keeps the frame; on, it grows to the rotated rectangle's
    bounding box by the very formula ``scipy.ndimage.rotate(reshape=True)`` uses
    (``ptp`` of the rotated corners, ``+ 0.5`` then truncated), so a caller that
    only needs the *size* of an edited picture never has to resample it.
    """
    angle = float(params.get("angle", 0.0))
    if abs(angle) < 1e-3 or h < 3 or w < 3:
        return None
    if not bool(params.get("expand", True)):
        return h, w
    rad = np.deg2rad(angle)
    c, s = np.cos(rad), np.sin(rad)
    rot = np.array([[c, s], [-s, c]])
    corners = rot @ np.array([[0, 0, h, h], [0, w, 0, w]], dtype=float)
    out_h, out_w = (np.ptp(corners, axis=1) + 0.5).astype(int)
    return int(out_h), int(out_w)


def edited_shape(recipe, shape: tuple[int, int]) -> tuple[int, int]:
    """The ``(h, w)`` a full-resolution render of ``recipe`` comes out at, from
    the source ``shape`` alone — no pixels touched.

    Replays the recipe's *enabled* geometry ops in order through the same
    :func:`crop_bounds` / :func:`resize_shape` / :func:`rotated_shape` the ops
    themselves use, so anything that has to promise something about the
    exported picture's pixels (the editor's print-size menu, which must offer
    only sizes the export will then accept) reads one answer with it. Every
    other op leaves the size alone.
    """
    h, w = int(shape[0]), int(shape[1])
    for op in recipe.ops:
        if not op.enabled or op.id not in GEOMETRY_OP_IDS:
            continue
        if op.id == "geometry.crop":
            box = crop_bounds(h, w, op.params)
            if box is not None:
                x0, x1, y0, y1 = box
                h, w = y1 - y0, x1 - x0
        elif op.id == "geometry.resize":
            out = resize_shape(h, w, op.params)
            if out is not None:
                h, w = out
        else:
            out = rotated_shape(h, w, op.params)
            if out is not None:
                h, w = out
    return h, w


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
                  step=0.5, help="Degrees to turn the picture. A positive angle turns it "
                                 "anticlockwise, a negative one clockwise. Corners exposed by "
                                 "the rotation are left transparent (rendered black)."),
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
