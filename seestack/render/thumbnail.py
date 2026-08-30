"""
Thumbnail cache.

A thumbnail is a 256x256 PNG preview of a frame, debayered and gently stretched
so the user can actually see what's in it. Without a stretch the linear data
looks black except for the brightest stars.

We keep thumbs in ``<project>/cache/thumbs/`` and key them on frame id. The
side cache is invalidated by clearing it from the GUI; nothing in the rest of
the pipeline reads from it.

Generation is a pure function so it can run in worker processes via JobRunner.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

THUMB_SIZE = 256
THUMBS_DIRNAME = "thumbs"
# Bumped whenever the thumbnail pipeline (debayer / stretch / size) changes
# enough that previously cached thumbnails should be discarded. The preview
# pane checks this before reusing a cached PNG.
THUMB_VERSION = 3


def thumbs_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "cache" / THUMBS_DIRNAME


def thumb_path_for(project_dir: Path, frame_id: int) -> Path:
    return thumbs_dir(project_dir) / f"frame_{frame_id:06d}.png"


def invalidate_frame_thumbs(project_dir: Path, frame_id: int) -> int:
    """Delete every cached preview PNG for one frame — the Qt gallery
    ``frame_NNNNNN.png`` and all web ``web_NNNNNN_*`` size/pattern variants — so
    the next request regenerates them from the frame's *current* pixels.

    Both preview caches key purely on ``frame_id`` (plus size/pattern/version),
    never on source content, and only regenerate when the file is missing. So
    when a frame's content changes after ingest — its source path is overwritten
    in place with a different capture, or a truncated mid-copy sub finishes
    copying — the caches keep serving the previous image indefinitely. The
    ingest/re-scan path calls this for each refreshed frame to close that gap.

    Returns the number of files removed; missing files (and any that can't be
    unlinked) are ignored."""
    d = thumbs_dir(project_dir)
    if not d.exists():
        return 0
    removed = 0
    # frame_NNNNNN.png is an exact name; web_NNNNNN_* fans out over size+pattern.
    for pattern in (f"frame_{frame_id:06d}.png", f"web_{frame_id:06d}_*.png"):
        for f in d.glob(pattern):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _version_sentinel(project_dir: Path) -> Path:
    return thumbs_dir(project_dir) / ".version"


def ensure_thumb_cache_current(project_dir: Path) -> bool:
    """
    Make sure the thumbnail cache matches the current pipeline version. If
    the on-disk version doesn't match, the cache is wiped. Returns True if
    a wipe happened.

    Call this once after opening a project — old thumbs from a previous
    Seestack version (different stretch, different size) will be regenerated
    on demand instead of showing weird stale previews.
    """
    d = thumbs_dir(project_dir)
    sentinel = _version_sentinel(project_dir)
    current = str(THUMB_VERSION)
    if sentinel.exists():
        try:
            if sentinel.read_text().strip() == current:
                return False
        except OSError:
            pass
    # Mismatch (or missing). Wipe + write new sentinel.
    wiped = False
    if d.exists():
        for f in d.iterdir():
            try:
                f.unlink()
                wiped = True
            except OSError:
                pass
    d.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(current)
    return wiped


def generate_thumbnail(
    fits_path: str | Path,
    out_path: str | Path,
    *,
    bayer_pattern: str | None = None,
    size: int = THUMB_SIZE,
) -> Path:
    """
    Read a FITS file, debayer, downsample, autostretch, and write as PNG.

    Designed to be called from a worker process — pure inputs/outputs, no shared
    state.
    """
    from PIL import Image

    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw

    rgb, info = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    # rgb is the raw 2D mosaic at this point; debayer with the requested pattern.
    pattern = bayer_pattern or info.bayer_pattern or "RGGB"
    rgb = bilinear_debayer(rgb, pattern=pattern)

    h, w = rgb.shape[:2]
    target_w = size
    target_h = max(1, int(round(h * (size / w))))
    rgb_small = _downsample_rgb(rgb, target_h, target_w)

    stretched = autostretch(rgb_small)
    out = (np.clip(stretched, 0.0, 1.0) * 255).astype(np.uint8)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(out_path, format="PNG")
    return out_path


def load_sub_linear_rgb(
    fits_path: str | Path,
    *,
    bayer_pattern: str | None = None,
    max_width: int = 1024,
) -> tuple[np.ndarray, float]:
    """Debayer one raw Seestar sub to **linear** RGB, decimated to ``max_width``.

    Returns ``(rgb, proxy_scale)`` where ``proxy_scale`` is ``full_width /
    rendered_width`` (``>= 1.0``) — the same meaning
    :class:`seestack.edit.registry.EditContext` gives it, so a caller can render
    an editor recipe over the result at the right spatial scale.

    Factored out of :func:`render_sub_preview` (which stretches the same array to
    PNG) so the "one frame vs your stack" reveal can put the sub through the
    run's *own* editor recipe instead of a stretch, without re-implementing the
    load/debayer/decimate half. Pure inputs/outputs, so it can run in a worker
    thread.
    """
    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw

    rgb, info = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    pattern = bayer_pattern or info.bayer_pattern or "RGGB"
    rgb = bilinear_debayer(rgb, pattern=pattern)

    h, w = rgb.shape[:2]
    scale = 1.0
    if w > max_width:
        target_w = max_width
        target_h = max(1, int(round(h * (max_width / w))))
        rgb = _downsample_rgb(rgb, target_h, target_w)
        scale = float(w) / float(target_w)
    return rgb, scale


def render_sub_preview(
    fits_path: str | Path,
    *,
    bayer_pattern: str | None = None,
    max_width: int = 1024,
    stretch: float | None = None,
    black: float | None = None,
) -> bytes:
    """Render a single raw Seestar sub to PNG bytes, stretched to *match* the
    stored stack preview.

    Reads one raw Bayer light, debayers it, decimates to ``max_width`` and applies
    the same tone curve that produced the run's stored ``*_preview.png``:

      * By default (``stretch``/``black`` both ``None``) the conservative export
        STF stretch (:func:`~seestack.stack.output._autostretch_for_export`,
        sky → ~6 % grey) — which is what a fresh linear stack's preview uses.
      * When the run has a **custom saved stretch** (the History "Adjust" panel
        overwrote its preview via :func:`asinh_stretch`), pass that run's saved
        ``stretch``/``black`` so the sub is rendered through the *same* asinh
        curve. Both stretches are anchored to each image's own robust sky level,
        so applying the same params to a single linear sub yields a comparable
        tone to the linear master's preview.

    Rendering both sides of a "one frame vs your stack" comparison through the
    identical stretch is what makes the reveal *honest* — the only visible
    difference is the noise/detail stacking bought, not a brightness offset from a
    different tone curve.

    Pure inputs/outputs (no shared state), so it can run in a worker thread.
    """
    import io

    from PIL import Image

    from seestack.stack.output import _autostretch_for_export

    rgb, _scale = load_sub_linear_rgb(
        fits_path, bayer_pattern=bayer_pattern, max_width=max_width)

    if stretch is not None and black is not None:
        stretched = asinh_stretch(rgb, stretch=float(stretch), black=float(black))
    else:
        stretched = _autostretch_for_export(rgb)
    out = (np.clip(np.nan_to_num(stretched), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


#: The width :func:`render_stack_png` caps a preview at — and therefore the grid
#: every *stored* preview PNG written by "Save as preview" sits on, before any
#: North-up rotation. Named so a caller that has to reason about that un-rotated
#: grid (the share/wallpaper paths, which must undo a baked rotation) shares one
#: definition with the renderer rather than hard-coding 1024 again.
PREVIEW_MAX_WIDTH = 1024


def preview_grid_size(
    full_w: int, full_h: int, *, max_width: int = PREVIEW_MAX_WIDTH,
) -> tuple[int, int]:
    """The ``(width, height)`` grid :func:`load_stack_rgb` decimates a
    ``full_w``×``full_h`` canvas onto — a stored preview PNG's own pixel grid,
    before any North-up rotation.

    A canvas narrower than ``max_width`` is kept at native size; anything wider is
    scaled to exactly ``max_width`` with the height following the aspect ratio.
    """
    if full_w > max_width:
        return max_width, max(1, int(round(full_h * max_width / full_w)))
    return int(full_w), int(full_h)


def load_stack_rgb(
    fits_path: str | Path, *, max_width: int = 1024,
) -> tuple[np.ndarray, bool]:
    """Load a stacked-image FITS as an ``(H, W, 3)`` float32 array plus whether it
    is a tone-mapped display-space export.

    Reads an already-processed stack FITS — a 3-channel ``(C, H, W)`` float cube
    (or 2-D mono, expanded to grey RGB) — and decimates it to ``max_width`` by a
    NaN-aware area average. Shared by :func:`render_stack_png` (which stretches
    the result) and the History render's stretch suggestion (which measures it),
    so both operate on the *identical* pixels and the suggested asinh sliders
    reproduce what the render actually shows.
    """
    from astropy.io import fits as _fits

    from seestack.stack.output import fits_is_display_space

    display_space = fits_is_display_space(fits_path)
    # Read the master **one channel at a time off the memory map**, and decimate
    # each plane as it is read. The old shape — ``asarray(getdata(...),
    # float32)`` on the whole cube, then a per-channel downscale — allocated the
    # entire canvas twice over before a single output pixel existed: FITS is
    # big-endian, so the dtype cast is a full copy *and* byte-swap of every
    # channel, and the per-channel NaN mask/fill then added their own full-plane
    # temporaries on top of it. Measured on a 144 MB master (4000×3000 × 3 ch,
    # decimated to 1024 px), peak **anonymous** RSS — the kind that actually OOMs,
    # as opposed to the evictable file-backed pages a memmap touches: **+342 MB
    # before, +148 MB after**. It scales with the canvas, so a 150 MP mosaic
    # preview costs ~1.9 GB of transient allocation instead of ~4.3 GB on the
    # RAM-capped NAS whose stack path is memory-bounded on purpose. The
    # arithmetic is untouched — each channel sees exactly the pixels it saw
    # before — so the result is bit-for-bit identical (pinned by a parity test).
    with _fits.open(fits_path, memmap=True) as hdul:
        # First HDU carrying pixels — what ``getdata`` used to pick for us.
        # Touching ``.data`` on a memmapped HDU doesn't read it, so the scan is
        # as cheap as it looks.
        data = next((h.data for h in hdul if h.data is not None), None)
        if data is None:
            raise ValueError(f"{fits_path}: FITS carries no image data")
        if data.ndim == 3 and data.shape[0] > 1:   # (channels, H, W)
            planes = [data[c] for c in range(min(data.shape[0], 3))]
            n_out, grey = len(planes), False
        else:
            # A 1-channel cube or a 2-D mono image is greyscale — decimate the
            # single plane once and repeat it, as the old ``np.repeat`` /
            # ``np.stack([arr, arr, arr])`` did.
            planes = [data[0] if data.ndim == 3 else data]
            n_out, grey = 3, True

        h, w = planes[0].shape
        # Downscale to the full ``max_width`` with a NaN-aware area (box)
        # average, not nearest-neighbour striding. Striding (a) only reached
        # ``ceil(w/max_width)`` integer steps — a 1080-wide Seestar stack
        # strode to 540 px, not 1024, visibly coarser than the box-averaged
        # baked preview beside it — and (b) *dropped* samples: a FWHM≈2 px
        # star could lose up to half its flux depending on subpixel phase, so
        # stars aliased/twinkled. The area average spreads each star's flux
        # instead. NaN (uncovered / mosaic-gap) is treated as no-coverage, so
        # an output pixel is the mean of the finite samples under it and
        # stays NaN only where every contributing input pixel was NaN — the
        # property striding was originally chosen to preserve.
        new_w, new_h = preview_grid_size(w, h, max_width=max_width)

        rgb = np.empty((new_h, new_w, n_out), dtype=np.float32)
        for i, plane in enumerate(planes):
            rgb[..., i] = _nan_aware_area_downscale_plane(plane, new_w, new_h)
        if grey:                            # the same plane in all three channels
            rgb[..., 1] = rgb[..., 0]
            rgb[..., 2] = rgb[..., 0]
    return rgb, display_space


def _nan_aware_area_downscale_plane(
    plane: np.ndarray, new_w: int, new_h: int,
) -> np.ndarray:
    """Area-average one ``(H, W)`` float plane down to ``(new_h, new_w)``,
    treating NaN as *no coverage*.

    Each output pixel is the mean of the **finite** input samples under it (via
    PIL's BOX/area filter on the NaN→0 plane divided by the same filter on a
    finite-sample mask), and is NaN only where every contributing input pixel was
    NaN. This spreads a star's flux across the downscale rather than dropping it
    (what nearest striding did, causing aliasing/twinkle) while keeping genuine
    coverage gaps as NaN for the NaN-aware stretch downstream.

    Accepts a memory-mapped, big-endian plane straight off the FITS HDU: nothing
    here needs the whole cube resident, which is what keeps a giant mosaic's
    preview inside the RAM budget. A no-op size (``new_w``/``new_h`` equal to the
    input) still returns a plain float32 copy, so the caller never hands a memmap
    view back to a caller that outlives the open file.
    """
    from PIL import Image

    h, w = plane.shape
    finite = np.isfinite(plane)
    # ``np.where`` on a big-endian plane against a float32 zero yields a native
    # float32 array — one conversion, no separate byte-swap pass.
    filled = np.where(finite, plane, np.float32(0.0)).astype(np.float32, copy=False)
    if (new_w, new_h) == (w, h):
        return np.where(finite, filled, np.float32(np.nan))
    # The two full-plane buffers are built and released one at a time: PIL copies
    # the array it is handed, so holding the filled plane, its mask, and both PIL
    # images at once would keep four full planes alive to produce two small ones.
    num = np.asarray(
        Image.fromarray(np.ascontiguousarray(filled), mode="F")
        .resize((new_w, new_h), Image.BOX),
        dtype=np.float32)
    del filled
    mask = finite.astype(np.float32)
    del finite
    den = np.asarray(
        Image.fromarray(mask, mode="F").resize((new_w, new_h), Image.BOX),
        dtype=np.float32)
    del mask
    with np.errstate(invalid="ignore", divide="ignore"):
        res = num / den
    res[den <= 0.0] = np.nan              # a fully-uncovered block stays a gap
    return res


def render_stack_png(
    fits_path: str | Path,
    *,
    stretch: float = 0.5,
    black: float = 0.35,
    max_width: int = 1024,
    north_up: bool = False,
) -> bytes:
    """Render a stacked-image FITS to PNG bytes with an adjustable asinh stretch.

    Unlike :func:`generate_thumbnail` (which debayers a raw Seestar mosaic),
    this reads an already-processed stack FITS — a 3-channel ``(C, H, W)`` float
    cube (or 2-D mono) — and applies :func:`asinh_stretch` with caller-supplied
    ``stretch`` (how hard to lift faint detail) and ``black`` (black point),
    both in ``[0, 1]``. Because it works from the full-dynamic-range FITS, faint
    detail that the baked 8-bit preview clipped comes back.

    An editor-export FITS is already a tone-mapped display-space ``[0, 1]`` image
    (marked with :data:`~seestack.stack.output.DISPLAY_SPACE_CARD`), so it is
    rendered *verbatim* — a second asinh stretch would double-process it, and the
    ``stretch``/``black`` sliders simply don't apply to such a run.
    """
    import io

    from PIL import Image

    rgb, display_space = load_stack_rgb(fits_path, max_width=max_width)

    # A display-space export is shown as written (matches its stored preview PNG);
    # a linear stack gets the adjustable asinh stretch. A second stretch on an
    # already tone-mapped image would double-process it.
    stretched = rgb if display_space else asinh_stretch(rgb, stretch=stretch, black=black)
    disp = np.clip(np.nan_to_num(stretched), 0.0, 1.0)
    if north_up:
        disp = _apply_north_up(disp, fits_path)
    u8 = (disp * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def render_preview_png_full_res(
    fits_path: str | Path, *, max_long_edge: int = 8000,
    north_up: bool = False,
    stretch: float | None = None, black: float | None = None,
) -> bytes:
    """Render a stacked-image FITS to a PNG at (near) native output resolution
    using the **same stretch as the baked gallery/History preview** — the STF
    autostretch for a linear stack, verbatim for a display-space editor export —
    i.e. the very picture the user already sees, at full output resolution instead
    of the 1024 px preview cap.

    ``stretch``/``black`` are the escape hatch for the one case where the baked
    preview is *not* the STF: History's "Adjust" save re-renders the stored preview
    through :func:`render_stack_png`'s **asinh** curve and records the two values on
    the run. Pass them here and the full-res render follows the same curve, so the
    download keeps matching the thumbnail. Omit them (the default) and the STF is
    used exactly as before — an unadjusted run is byte-for-byte unchanged.

    This is the beginner-friendly answer to "why is my downloaded picture
    low-res?": the FITS/TIFF already hold full-resolution pixels but aren't easily
    viewable, and the quick PNG button serves the 1024 px preview. This serves the
    same look at full size. It matches :func:`~seestack.stack.output._write_preview_png`
    exactly (STF for linear, ``nan_to_num`` for display-space) rather than the
    adjustable asinh of :func:`render_stack_png`, so the download is the thumbnail
    the user clicked, just bigger.

    Decimated only if the long edge exceeds ``max_long_edge`` — a practical PNG
    ceiling that bounds memory / response size on a RAM-capped host; the FITS/TIFF
    stay available for the true native pixels of an enormous mosaic. Returns PNG
    bytes.
    """
    import io

    from PIL import Image

    from seestack.stack.output import _autostretch_for_export

    # ``load_stack_rgb`` area-averages the width down to ``max_long_edge`` during
    # load (cheap for a wide image); a tall image's height is capped after stretch.
    rgb, display_space = load_stack_rgb(fits_path, max_width=max_long_edge)
    if display_space:
        # Already tone-mapped: written verbatim, and the sliders don't apply.
        stretched = np.nan_to_num(rgb, nan=0.0)
    elif stretch is not None and black is not None:
        stretched = asinh_stretch(rgb, stretch=float(stretch), black=float(black))
    else:
        stretched = _autostretch_for_export(rgb)
    disp = np.clip(np.nan_to_num(stretched), 0.0, 1.0)
    if north_up:
        disp = _apply_north_up(disp, fits_path)
    u8 = (disp * 255).astype(np.uint8)
    img = Image.fromarray(u8, mode="RGB")
    h, w = u8.shape[:2]
    long_edge = max(h, w)
    if long_edge > max_long_edge:
        scale = max_long_edge / long_edge
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                         Image.BOX)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def stack_north_up_deg(fits_path: str | Path) -> float | None:
    """The rotation (deg) that orients a stack's stored master so celestial North
    is up, read from its own WCS — or ``None`` when the run carries no usable WCS
    (older/edited runs). Lets the UI decide whether to offer a "North up" option
    (only when a real, more-than-trivial correction exists)."""
    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.render.orient import north_up_rotation_deg

    wcs, w, h = celestial_wcs_from_fits(fits_path)
    return north_up_rotation_deg(wcs, w, h)


def applied_north_up_deg(fits_path: str | Path) -> float:
    """The rotation a ``north_up=True`` render of this stack **actually applies**
    — ``0.0`` when the run has no usable WCS or the correction is below
    :data:`~seestack.render.orient.NORTH_UP_MIN_DEG` (both leave the pixels
    untouched), and the snapped angle otherwise.

    Anything that has to *record* or *follow* the rotation — the Sky map, which
    places a saved preview's tile and its coverage footprint on the sky — needs
    this one answer rather than re-deriving the threshold-and-snap rules, so it
    can never drift from what the renderer did.
    """
    from seestack.render.orient import NORTH_UP_MIN_DEG, applied_rotation_deg

    angle = stack_north_up_deg(fits_path)
    if angle is None or abs(angle) < NORTH_UP_MIN_DEG:
        return 0.0
    return applied_rotation_deg(angle)


def _apply_north_up(disp: np.ndarray, fits_path: str | Path) -> np.ndarray:
    """Rotate a display image so North is up, using the FITS's own WCS. A missing
    WCS or a sub-threshold correction leaves the pixels unchanged, so the render
    never breaks or needlessly resamples."""
    from seestack.render.orient import NORTH_UP_MIN_DEG, rotate_image_north_up

    angle = stack_north_up_deg(fits_path)
    if angle is None or abs(angle) < NORTH_UP_MIN_DEG:
        return disp
    return np.clip(rotate_image_north_up(disp, angle), 0.0, 1.0)


def preview_north_up_remainder_deg(
    fits_path: str | Path, *, already_deg: float = 0.0,
) -> float:
    """The rotation :func:`orient_preview_north_up` will **actually apply** to a
    stored preview — ``0.0`` when it would return the bytes untouched.

    Anything that has to lay something *over* that turned picture — the "see what
    stacking removed" tint, which is a separate PNG sized to the preview — needs
    the same answer the picture got, and it must come from here rather than each
    caller re-deriving the "no WCS → don't turn", "sub-threshold total → treat as
    zero", "sub-threshold remainder → don't turn" rules. The returned angle is
    deliberately **un-snapped**: both :func:`~seestack.render.orient.
    rotate_image_north_up` and its plane/mask siblings apply the 90°-snap
    themselves, so passing the raw remainder to any of them keeps them in step.
    """
    from seestack.render.orient import NORTH_UP_MIN_DEG

    total = stack_north_up_deg(fits_path)
    if total is None:
        return 0.0
    if abs(total) < NORTH_UP_MIN_DEG:
        total = 0.0
    angle = total - float(already_deg)
    return 0.0 if abs(angle) < NORTH_UP_MIN_DEG else angle


def orient_preview_north_up(
    preview_png: bytes, fits_path: str | Path, *, already_deg: float = 0.0,
) -> bytes:
    """Rotate an already-rendered stack *preview* PNG so celestial North is up,
    using the run's own master-FITS WCS, and return it re-encoded as PNG.

    Lets the share/download path offer a North-up picture without re-rendering
    from the linear FITS: the stored preview is already the finished display
    image (exact colour parity with what the user saw), and the North rotation is
    invariant under the uniform downscale between the FITS and its preview, so the
    FITS-derived angle applies to the preview unchanged. When the run has no usable
    WCS or the correction is sub-threshold (:data:`~seestack.render.orient.
    NORTH_UP_MIN_DEG`), the **original bytes are returned untouched** — so a
    no-correction request is byte-for-byte the un-oriented preview and never
    needlessly resamples. Exposed corners fill with black (the app's uncovered/NaN
    convention), matching the JPEG flatten in :func:`~seestack.stack.output.
    png_bytes_to_jpeg`.

    ``already_deg`` is the rotation **these bytes already carry** — History's
    "Adjust → North up → Save" overwrites the stored preview with a rotated
    render and records the angle on the run (``preview_north_up_deg``). Pass it
    and only the *remainder* is applied, so a preview already saved North-up is a
    clean no-op instead of being turned a second time (which shared it 180° from
    the picture on screen). The default of ``0.0`` is exactly the old behaviour,
    so every un-rotated run is byte-for-byte unchanged. When the run carries no
    usable WCS the bytes are returned untouched even if ``already_deg`` is set:
    we can't recompute the correction, and leaving a recorded North-up preview
    alone is right, while "un-rotating" it on a guess would not be."""
    import io

    from PIL import Image

    from seestack.render.orient import rotate_image_north_up

    angle = preview_north_up_remainder_deg(fits_path, already_deg=already_deg)
    if not angle:
        return preview_png
    with Image.open(io.BytesIO(preview_png)) as src:
        rgb = np.asarray(src.convert("RGB"), dtype=np.float32) / 255.0
    rotated = np.clip(rotate_image_north_up(rgb, angle), 0.0, 1.0)
    u8 = (rotated * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def stack_coverage_mask(fits_path: str | Path) -> np.ndarray:
    """Boolean ``(H, W)`` coverage mask for a stacked-image FITS.

    ``True`` where the pixel has real data (any channel finite), ``False`` on
    uncovered / mosaic-gap pixels (NaN) — the "NaN = no coverage" footprint. Used
    to make the Sky-map overlay transparent where an irregular union-mosaic doesn't
    reach, instead of an opaque black rectangle.
    """
    from astropy.io import fits as _fits

    # Reduced straight off the memory map, one channel at a time. The float32
    # cast the old shape did was pure waste here — ``isfinite`` needs no
    # conversion, and on a big-endian FITS that cast copied and byte-swapped the
    # *whole* cube to answer a boolean question. Measured on the same 144 MB
    # master, peak anonymous RSS **+201 MB before, +41 MB after**. Same mask,
    # same "any channel finite" rule.
    with _fits.open(fits_path, memmap=True) as hdul:
        data = next((h.data for h in hdul if h.data is not None), None)
        if data is None:
            raise ValueError(f"{fits_path}: FITS carries no image data")
        if data.ndim == 3:                  # (channels, H, W) → any channel finite
            mask = np.isfinite(data[0])
            for c in range(1, data.shape[0]):
                mask |= np.isfinite(data[c])
            return mask
        return np.isfinite(data)            # 2-D mono (a fresh array, not a view)


#: Longest axis the frame-count map is loaded at when deriving the detail mask.
#: The mask only ever drives a ≤1024 px preview's alpha, so reading a big
#: mosaic's full-canvas float32 count map would be hundreds of megabytes for a
#: decision that survives a nearest-neighbour resize unchanged.
_DETAIL_MAX_DIM = 2048


def stack_detail_mask(fits_path: str | Path, *, min_frac: float = 0.5
                      ) -> np.ndarray:
    """Boolean ``(H, W)`` mask of a stack's **well-covered** pixels.

    Stricter than :func:`stack_coverage_mask`, which only asks "is there data
    here?". This asks "did enough frames land here to trust it?", using the
    per-pixel frame-count sibling every run writes (``{stem}_framecov.fits``) and
    the same "at least ``min_frac`` of the peak" rule the editor's one-click
    border trim already uses (:func:`seestack.edit.coverage_trim.well_covered_mask`)
    — so the number isn't picked blind, it is the app's existing definition of
    "enough coverage".

    Falls back to the plain has-data footprint when there is no frame-count
    sibling (older runs) or it carries no usable coverage, so a legacy run still
    maps its real shape rather than vanishing. On the canvas grid, like
    :func:`stack_coverage_mask`.
    """
    from seestack.edit.coverage_trim import well_covered_mask
    from seestack.edit.proxy import load_frame_coverage

    covered = stack_coverage_mask(fits_path)
    # Stride the frame-count sibling the way the editor's trim already does: a
    # big mosaic's map is a full-canvas float32 array (hundreds of MB), and the
    # answer is only ever resized down onto a ≤1024 px preview anyway.
    step = max(1, -(-max(covered.shape) // _DETAIL_MAX_DIM))  # ceil division
    try:
        counts = load_frame_coverage(fits_path, step=step)
    except Exception:  # noqa: BLE001 — an unreadable sibling just means "no opinion"
        counts = None
    if counts is None:
        return covered
    mask = well_covered_mask(counts, min_frac)
    if mask is None or not mask.any():
        return covered
    if mask.shape != covered.shape:
        from PIL import Image

        mask = np.asarray(
            Image.fromarray(mask.astype(np.uint8) * 255, mode="L").resize(
                (covered.shape[1], covered.shape[0]), Image.NEAREST)) > 127
    return covered & mask


def overlay_rgba_array(preview_png: bytes, coverage_mask: np.ndarray) -> np.ndarray:
    """The RGBA ``(H, W, 4)`` uint8 array behind :func:`overlay_rgba_png` — the
    preview's pixels with the mask resized onto its grid as the alpha channel.

    Split out so a caller that wants to *draw* the transparent picture (the
    all-sky "My map" composite) doesn't have to encode a PNG and decode it again.
    """
    import io

    from PIL import Image

    mask = np.asarray(coverage_mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("coverage_mask must be 2-D")
    im = Image.open(io.BytesIO(preview_png)).convert("RGB")
    w, h = im.size
    alpha_img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
        (w, h), Image.NEAREST)
    return np.dstack([np.asarray(im, dtype=np.uint8),
                      np.asarray(alpha_img, dtype=np.uint8)])


def overlay_rgba_png(preview_png: bytes, coverage_mask: np.ndarray) -> bytes:
    """Compose an RGBA overlay PNG from an opaque preview PNG and a coverage mask.

    The preview's RGB pixels are kept verbatim, so the overlay looks exactly like
    the finished picture; the coverage mask (``True`` = covered) is resized —
    nearest-neighbour, so it stays a hard 1-bit footprint — to the preview's grid
    and drives the alpha channel, turning uncovered pixels fully transparent. So an
    irregular mosaic shows its true footprint on the sky instead of a black box,
    while a fully-covered stack is unchanged (every pixel opaque). Keeps the
    preview's exact dimensions, so a WCS built for the preview grid still places it.
    """
    import io

    from PIL import Image

    rgba = overlay_rgba_array(preview_png, coverage_mask)
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


#: Tint for the "what stacking removed" overlay. Cyan, because an OSC deep-sky
#: picture is overwhelmingly red/gold/black and a warm highlight would vanish
#: into the very nebulosity the user is trying to look past.
REJECTION_TINT_RGB = (53, 224, 255)

#: The drop density (samples per pixel, after the resize below) that reads as
#: fully opaque. Taken as a high percentile of the *non-empty* pixels rather than
#: the maximum: a handful of hot pixels rejected in every single sub would
#: otherwise set the scale and render the satellite trail — the thing the user
#: actually wants to see — as good as invisible.
_REJECTION_SCALE_PERCENTILE = 90.0
#: Gamma applied to the normalised density, <1 so a trail that only appears in
#: one sub of many is still plainly visible rather than a ghost.
_REJECTION_ALPHA_GAMMA = 0.7
#: Above this share of the density map being non-empty, the map is dominated by
#: the *uniform* noise-tail clipping every pixel is subject to, not by marks —
#: so the level at this percentile is subtracted as the map's own floor. Chosen
#: as a percentile rather than a hit-fraction test so it is exactly zero, and
#: therefore a strict no-op, on any map where three quarters of the canvas lost
#: nothing (which is every map a modest stack produces). Real marks — trails,
#: cosmic rays, hot columns — cover a small part of a canvas; nothing that
#: covers three quarters of one is a mark.
_REJECTION_FLOOR_PERCENTILE = 75.0
#: The opaque level for a floor-subtracted map. Measured over the *whole* canvas
#: rather than the non-empty pixels: after the subtraction almost everything is
#: still faintly non-empty (the noise floor has spread, not a single value), so
#: the hit-set percentile above would be set by that residue and re-open the
#: wash the subtraction just closed.
_REJECTION_DENSE_SCALE_PERCENTILE = 95.0


def rejection_overlay_png(rejection_map: np.ndarray,
                          size: tuple[int, int]) -> bytes:
    """A transparent RGBA PNG tinting where outlier rejection dropped samples.

    ``rejection_map`` is the run's per-pixel drop count (the ``_rejected.fits``
    sibling); ``size`` is the ``(width, height)`` of the preview it will be laid
    over, so the result drops straight onto the picture at any box size. Pixels
    that lost nothing are fully transparent, so this is an *overlay* — the
    picture underneath is untouched.

    **Why the resize averages rather than samples.** Rejection legitimately
    clips a scattering of lone pixels all over the frame (the tails of the noise
    distribution), and those are not what the user is being shown — the
    satellites, plane trails and cosmic rays are. Down-sampling the counts with
    an area average turns the map into a local *density*: a trail, which is
    dense along a line, keeps its strength, while isolated speckle dilutes
    toward nothing. Scaling up (a small canvas, a big preview) degrades to
    nearest-neighbour, which is the right answer there too.

    **Why the floor is subtracted.** That dilution alone stops working once the
    map is *dense*, and the map gets denser with every sub: a pixel is marked if
    it lost a sample in **any** frame, so at a fixed per-sample clip rate the
    share of the canvas that is non-empty climbs with the sub count (measured on
    real engine output: 1.9 % of the canvas at 16 subs, 11.5 % at 32, 31.2 % at
    64 — and the Seestar owner this app is for stacks hundreds). Past that point
    the *hit set* is mostly noise floor, so a percentile of it normalises the
    floor itself to opaque and the tint becomes a cyan wash over the whole
    picture — measured at 94 % of the frame above half opacity on a 64-sub stack
    at a 4× downsample, with the satellite trail no more prominent than the sky
    beside it. Since that floor is *uniform* — every pixel runs the same risk of
    losing a sample to the noise tail — and real marks are local excesses over
    it, subtracting the level at :data:`_REJECTION_FLOOR_PERCENTILE` removes it
    and leaves the marks. The subtraction is exactly zero, hence byte-for-byte
    inert, whenever three quarters of the canvas lost nothing.
    """
    import io

    from PIL import Image

    m = np.asarray(rejection_map, dtype=np.float32)
    if m.ndim != 2:
        raise ValueError("rejection_map must be 2-D")
    w, h = int(size[0]), int(size[1])
    if w <= 0 or h <= 0:
        raise ValueError("size must be positive")

    dens = np.asarray(
        Image.fromarray(m, mode="F").resize((w, h), Image.BOX),
        dtype=np.float32)
    # Subtract the map's own uniform noise floor before normalising. Only where
    # the resize actually *averaged*, because only then is `dens` a local
    # density: at 1:1 (or scaling up) a trail pixel and a noise-tail pixel are
    # both "one sample lost here" and nothing pointwise can separate them, so a
    # floor there would take the trail with the speckle. Every real preview is a
    # downsample of the canvas — the stored preview is capped at 1024 px on its
    # long edge — so the 1:1 case needs a canvas no bigger than the preview,
    # which for a Seestar stack means a tiny crop.
    floor = 0.0
    if w < m.shape[1] or h < m.shape[0]:
        floor = float(np.percentile(dens, _REJECTION_FLOOR_PERCENTILE))
    if floor > 0.0:
        dens = np.clip(dens - floor, 0.0, None)
        scale_pct, scale_over = _REJECTION_DENSE_SCALE_PERCENTILE, dens
    else:
        scale_pct, scale_over = _REJECTION_SCALE_PERCENTILE, dens[dens > 0]
    if scale_over.size:
        scale = float(np.percentile(scale_over, scale_pct))
        if scale <= 0:
            scale = float(dens.max())
        alpha = (np.clip(dens / scale, 0.0, 1.0) ** _REJECTION_ALPHA_GAMMA
                 if scale > 0 else np.zeros_like(dens))
    else:
        alpha = np.zeros_like(dens)

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = REJECTION_TINT_RGB
    rgba[..., 3] = np.rint(alpha * 255.0).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def asinh_stretch(
    rgb: np.ndarray,
    *,
    stretch: float = 0.5,
    black: float = 0.35,
    protect_highlights: bool = True,
    highlight_protect: float = 0.0,
) -> np.ndarray:
    """Asinh (inverse-hyperbolic-sine) stretch — the astrophotographer's stretch.

    Asinh is near-linear for bright pixels (so stars and bright cores keep their
    shape and colour) but strongly amplifies faint values, which is exactly what
    nebulae and galaxy halos need. Compared with the MTF/STF curve in
    :func:`autostretch` it gives a far more natural, less "crunchy" reveal of
    faint signal.

    Two intuitive controls, both in ``[0, 1]``:

      * ``stretch`` — how hard to lift faint detail. ``0`` ≈ linear, ``1`` ≈
        extreme. The mapping is geometric so equal slider steps feel evenly
        spaced.
      * ``black`` — the black point. Raising it darkens / cleans the sky
        background. It is anchored to each channel's robust sky level so the
        background stays a neutral grey (no colour cast), and the response is
        monotonic: more ``black`` always means a darker background.

    NaN pixels (uncovered mosaic canvas) are excluded from every statistic and
    rendered black, exactly as in :func:`autostretch`.

    ``highlight_protect`` (0..1, default 0) walks the highlight shoulder's knee
    down (:func:`highlight_knee_for`) so a bright core is compressed harder and
    keeps its detail. 0 is byte-for-byte the historical behaviour.
    """
    knee = highlight_knee_for(highlight_protect)
    img = rgb.astype(np.float32, copy=True)
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)

    finite_any = np.isfinite(img).any(axis=2)
    if not finite_any.any():
        return np.zeros_like(np.nan_to_num(img))

    # Normalize over covered pixels only; keeps per-channel scales intact.
    # Use a robust high percentile rather than the raw max for the top of the
    # range: a single surviving hot/warm pixel, bloom, or bright column that
    # sigma-clip didn't reject would otherwise inflate `hi`, divide the whole
    # image down, and — with the asinh gain fixed by the slider, not adaptive —
    # crush faint nebulosity to near-black. The bright stars still saturate to
    # white via the final `np.clip(..., 0, 1)`. This mirrors the 0.5–99.5th
    # percentile scaling in edit/ops/detail.py, added for the same reason
    # ("a single hot star sets max(), crushing the sky noise").
    lo = float(np.nanmin(img))
    hi = float(np.nanpercentile(img, 99.5))
    if not np.isfinite(hi) or hi <= lo:
        hi = float(np.nanmax(img))          # degenerate/near-flat image
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(np.nan_to_num(img))
    img = (img - lo) / (hi - lo)

    # asinh softening `a`: geometric sweep from 1.0 (≈linear) at stretch=0 down
    # to 0.004 (very aggressive) at stretch=1.
    s = float(np.clip(stretch, 0.0, 1.0))
    a = float(0.004 ** s)
    denom = math.asinh(1.0 / a)
    b = float(np.clip(black, 0.0, 1.0))

    out = np.zeros_like(img)
    for c in range(3):
        chan = img[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            continue
        med, sigma = _robust_median_sigma(chan[finite])
        # Black point anchored to the sky median: black=0 keeps almost
        # everything (median − 2σ), black≈0.33 sits at the sky median, black=1
        # cuts well into the signal (median + 4σ).
        shadows = float(np.clip(med + (b * 6.0 - 2.0) * sigma, 0.0, 0.999))
        rng = max(1.0 - shadows, 1e-6)
        # Soft-shoulder the highlights rather than hard-clipping them: a bright
        # HDR core sits above the 99.5th-pct ceiling (xr > 1) and would otherwise
        # clip to a flat white blob, exactly the STF blow-out fixed in v0.119.1.
        # The rolloff leaves the sky/mid-tones untouched, so it only recovers
        # core detail; `protect_highlights=False` restores the old hard clip.
        xr = (chan[finite] - shadows) / rng
        x = _highlight_rolloff(xr, knee) if protect_highlights else np.clip(xr, 0.0, 1.0)
        out[..., c][finite] = np.clip(np.arcsinh(x / a) / denom, 0.0, 1.0)

    return out


def autostretch(
    rgb: np.ndarray,
    *,
    target_bg: float = 0.20,
    sigma_factor: float = -2.0,
    protect_highlights: bool = True,
    highlight_protect: float = 0.0,
) -> np.ndarray:
    """
    PixInsight-style "Screen Transfer Function" (STF) autostretch.

    Each channel is stretched independently so that **its own** robust sky
    median lands at ``target_bg`` (default 20% grey). This is what every
    professional astro tool does, and it's the right answer because:

      - Sky goes to clean neutral grey: each R/G/B channel's median maps to
        the same target value, so the sky has no colour cast.
      - Per-channel SNR is preserved: we don't multiply weak channels by
        large factors, so red noise doesn't get amplified relative to green.
      - Star colours come through naturally because the *shape* of the
        stretch curve is the same for all channels.

    The maths: PixInsight's "midtones transfer function":

        mtf(x, m) = (m - 1) · x / ((2·m - 1)·x - m)

    where ``m`` is chosen per channel so that ``mtf(median, m) = target_bg``
    after shadow clipping at ``median + sigma_factor·σ``.

    ``highlight_protect`` (0..1, default 0) walks the highlight shoulder's knee
    down (:func:`highlight_knee_for`), compressing more of the bright range so a
    high-dynamic-range core keeps its structure instead of washing out. It moves
    only values *above* the knee, so the sky still lands on ``target_bg``
    unchanged; 0 reproduces the historical output byte-for-byte.
    """
    knee = highlight_knee_for(highlight_protect)
    img = rgb.astype(np.float32, copy=True)
    if img.ndim == 2:
        # A 2-D (mono) array is treated as a grey image — expand to 3 channels
        # so the per-channel stretch below has an ``axis=2`` to work on, exactly
        # as :func:`asinh_stretch` does. Without this a mono input would raise an
        # ``AxisError`` at the ``any(axis=2)`` below.
        img = np.stack([img, img, img], axis=-1)

    # NaN = uncovered canvas (mosaic gaps, corners). These MUST be excluded
    # from every statistic — otherwise a mosaic's large no-data regions drag
    # the per-channel median to ~0 and the stretch goes haywire (colour cast,
    # wrong black point). We compute all stats over the finite pixels only and
    # set uncovered pixels to 0 (black) in the output.
    finite_any = np.isfinite(img).any(axis=2)
    if not finite_any.any():
        return np.zeros_like(np.nan_to_num(img))

    # Normalize the *whole image* to 0..1 first — keeps per-channel scales
    # intact relative to each other. Use a robust high percentile rather than
    # the raw max for the top of the range: a single surviving hot/cosmic pixel
    # or bright column that sigma-clip didn't reject would otherwise inflate
    # `hi`, compress the real sky median toward 0, and — once the MTF's midtone
    # clamp (`m` clamped to [1e-3, 1-1e-3]) is hit — crush the whole picture to
    # near-black. The bright star cores still saturate to white via the final
    # `np.clip(..., 0, 1)`. This mirrors the 99.5th-percentile scaling already
    # in the sibling `asinh_stretch` (and edit/ops/detail.py), added there for
    # exactly the same reason ("a single hot star sets max(), crushing the sky").
    lo = float(np.nanmin(img))
    hi = float(np.nanpercentile(img, 99.5))
    if not np.isfinite(hi) or hi <= lo:
        hi = float(np.nanmax(img))          # degenerate/near-flat image
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(np.nan_to_num(img))
    img = (img - lo) / (hi - lo)

    out = np.zeros_like(img)
    for c in range(3):
        chan = img[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            continue
        med, sigma = _robust_median_sigma(chan[finite])
        # Black point = median - 2σ (clipped at 0).
        shadows = max(0.0, med + sigma_factor * sigma)
        rng = max(1.0 - shadows, 1e-6)
        # Apply the stretch only to covered pixels; uncovered stay 0.
        xr = (chan[finite] - shadows) / rng
        # Soft-shoulder the highlights instead of hard-clipping them to flat
        # white — otherwise a bright HDR core (which sits above the 99.5th-pct
        # ceiling, so xr > 1) clips to a featureless white blob. The rolloff
        # leaves the sky/mid-tones untouched (they're far below the knee), so it
        # only recovers core detail. `protect_highlights=False` restores the old
        # hard-clip behaviour for callers that want it.
        x = _highlight_rolloff(xr, knee) if protect_highlights else np.clip(xr, 0.0, 1.0)
        norm_med = max((med - shadows) / rng, 1e-6)
        m = _midtones_for(norm_med, target_bg)
        out_chan = out[..., c]
        out_chan[finite] = np.clip(_mtf(x, m), 0.0, 1.0)

    return out


def _robust_median_sigma(values: np.ndarray) -> tuple[float, float]:
    """
    Median and MAD-based sigma — resistant to bright stars.

    ``values`` should already be the finite (covered) pixels; callers strip
    NaN before passing it in.
    """
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    sigma = 1.4826 * mad if mad > 0 else float(values.std() or 1e-3)
    return med, sigma


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    """PixInsight midtones transfer function. ``m`` in (0, 1)."""
    if abs(m - 0.5) < 1e-9:
        return x
    return (m - 1.0) * x / ((2.0 * m - 1.0) * x - m)


#: Where the STF highlight rolloff starts, in the per-channel shadow-normalized
#: space that feeds the midtones transfer. Values below the knee pass through
#: unchanged (so the sky, nebula, and ordinary stars are untouched); values above
#: it — a bright HDR core that sits above the robust 99.5th-percentile ceiling —
#: are soft-compressed into ``[knee, 1)`` instead of hard-clipping to flat white.
_HIGHLIGHT_KNEE = 0.7

#: Where the knee lands at full "hold the highlights back" strength. Below this
#: the shoulder would start eating ordinary bright nebulosity rather than just the
#: core, so it is the floor of the range :func:`highlight_knee_for` sweeps.
_HIGHLIGHT_KNEE_MIN = 0.25


def highlight_knee_for(protect: float = 0.0) -> float:
    """Rolloff knee for a 0..1 "hold the bright cores back" strength.

    ``protect=0`` — every caller's default — returns :data:`_HIGHLIGHT_KNEE`
    **exactly**, so an untouched stretch is byte-for-byte what it always was.
    Raising it walks the knee down toward :data:`_HIGHLIGHT_KNEE_MIN`, which
    starts the Reinhard shoulder earlier and so compresses more of the bright
    range: a blown-out galaxy/nebula core keeps a resolvable gradient instead of
    rendering as flat white. Non-finite / out-of-range input is treated as 0 (no
    extra protection) rather than raising — the value can reach here from a
    stored recipe or a taste profile.
    """
    p = float(protect)
    if not math.isfinite(p) or p <= 0.0:
        return _HIGHLIGHT_KNEE
    p = min(p, 1.0)
    return float(_HIGHLIGHT_KNEE + (_HIGHLIGHT_KNEE_MIN - _HIGHLIGHT_KNEE) * p)


def _highlight_rolloff(x: np.ndarray, knee: float = _HIGHLIGHT_KNEE) -> np.ndarray:
    """Soft-shoulder the highlights of a shadow-normalized channel.

    Without this the STF stretch hard-clips every value above the 99.5th-
    percentile normalization ceiling to ``1.0``, so a bright high-dynamic-range
    core (an M31/M42-style compact core on a faint disk) loses *all* internal
    structure and renders as a flat white blob. Here everything at or below
    ``knee`` is returned unchanged, and the open-ended highlight range
    ``[knee, +inf)`` is mapped monotonically onto ``[knee, 1)`` with a Reinhard
    shoulder (``t / (1 + t)``) so the core keeps a smooth, resolvable gradient
    and only the very brightest pixel approaches (but never reaches) pure white.
    The sky/mid-tones — which sit far below the knee — are bit-for-bit unchanged,
    so this only ever *adds* highlight detail, never shifts the background.
    """
    out = np.clip(x, 0.0, knee)                     # below-knee unchanged; floor at 0
    over = x > knee
    if np.any(over):
        span = 1.0 - knee
        t = (x[over] - knee) / span                 # >= 0, open-ended
        out[over] = knee + span * (t / (1.0 + t))   # -> [knee, 1), asymptotic
    return out


def _midtones_for(median: float, target: float) -> float:
    """
    Closed-form inverse of ``_mtf``: choose m so ``mtf(median, m) = target``.

    Derived from the MTF formula by solving for m. Both arguments must be in
    (0, 1); we clamp to avoid division by zero or runaway curves.
    """
    median = float(np.clip(median, 1e-6, 1 - 1e-6))
    target = float(np.clip(target, 1e-3, 1 - 1e-3))
    denom = median * (1.0 - 2.0 * target) + target
    if abs(denom) < 1e-12:
        return 0.5
    m = median * (1.0 - target) / denom
    return float(np.clip(m, 1e-3, 1 - 1e-3))


def _downsample_rgb(rgb: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """
    Resize an RGB float image to (target_h, target_w) using Pillow's box filter.

    Each channel is box-averaged in Pillow's **float** (``"F"``) mode, keeping full
    float precision — there is *no* uint8 round-trip. A prior version first
    normalised the whole frame to ``[0, 1]`` against its global min/max and
    quantised to uint8 before resizing. On a real raw Seestar sub the max is a
    saturated star (or hot pixel) at ~65535, while the sky sits a few thousand
    ADU up with only ~80 ADU of noise — so the sky collapsed into 1–2 uint8
    levels and its texture was destroyed *before* the downstream autostretch
    could reveal it. That silently flattened the raw-sub side of the "one frame
    vs your stack" reveal (``render_sub_preview``), hiding the very single-sub
    noise the comparison exists to show, and posterised the faint sky in every
    raw-sub thumbnail. Box downsampling is a per-channel *linear* average, so
    resizing each channel independently in float preserves colour ratios exactly
    (the old shared-normalisation trick is unnecessary without the uint8 step).
    """
    from PIL import Image

    # An all-non-finite frame has no data to show → black placeholder (matches
    # the sibling autostretch/asinh_stretch degenerate handling).
    if not np.isfinite(rgb).any():
        return np.zeros((target_h, target_w, 3), dtype=np.float32)
    # NaN = no coverage (should a future caller point this at a stacked/
    # reprojected FITS). Floor NaN to the frame min (darkest) so a no-coverage
    # pixel doesn't poison the box average of its finite neighbours, mirroring
    # the sibling reductions. For an ordinary raw-sub input (no NaN) this is a
    # no-op.
    floor = float(np.nanmin(rgb))
    filled = np.nan_to_num(rgb.astype(np.float32, copy=False), nan=floor)
    chans = [
        np.asarray(
            Image.fromarray(np.ascontiguousarray(filled[..., c], dtype=np.float32),
                            mode="F").resize((target_w, target_h), Image.BOX),
            dtype=np.float32,
        )
        for c in range(filled.shape[2])
    ]
    return np.stack(chans, axis=-1)
