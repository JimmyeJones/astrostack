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


def render_sub_preview(
    fits_path: str | Path,
    *,
    bayer_pattern: str | None = None,
    max_width: int = 1024,
) -> bytes:
    """Render a single raw Seestar sub to PNG bytes, stretched to *match* the
    stored stack preview.

    Reads one raw Bayer light, debayers it, decimates to ``max_width`` and applies
    the **same** conservative export STF stretch (:func:`~seestack.stack.output.
    _autostretch_for_export`, sky → ~6 % grey) that produced the run's stored
    ``*_preview.png``. Rendering both sides of a "one frame vs your stack"
    comparison through the identical stretch is what makes the reveal *honest* — the
    only visible difference is the noise/detail stacking bought, not a brightness
    offset from a different tone curve.

    Pure inputs/outputs (no shared state), so it can run in a worker thread.
    """
    import io

    from PIL import Image

    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw
    from seestack.stack.output import _autostretch_for_export

    rgb, info = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    pattern = bayer_pattern or info.bayer_pattern or "RGGB"
    rgb = bilinear_debayer(rgb, pattern=pattern)

    h, w = rgb.shape[:2]
    if w > max_width:
        target_w = max_width
        target_h = max(1, int(round(h * (max_width / w))))
        rgb = _downsample_rgb(rgb, target_h, target_w)

    stretched = _autostretch_for_export(rgb)
    out = (np.clip(np.nan_to_num(stretched), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def load_stack_rgb(
    fits_path: str | Path, *, max_width: int = 1024,
) -> tuple[np.ndarray, bool]:
    """Load a stacked-image FITS as an ``(H, W, 3)`` float32 array plus whether it
    is a tone-mapped display-space export.

    Reads an already-processed stack FITS — a 3-channel ``(C, H, W)`` float cube
    (or 2-D mono, expanded to grey RGB) — and decimates it to ``max_width`` by
    NaN-preserving striding. Shared by :func:`render_stack_png` (which stretches
    the result) and the History render's stretch suggestion (which measures it),
    so both operate on the *identical* pixels and the suggested asinh sliders
    reproduce what the render actually shows.
    """
    from astropy.io import fits as _fits

    from seestack.stack.output import fits_is_display_space

    display_space = fits_is_display_space(fits_path)
    arr = np.asarray(_fits.getdata(fits_path), dtype=np.float32)
    if arr.ndim == 3:                       # (channels, H, W) → (H, W, channels)
        rgb = np.transpose(arr, (1, 2, 0))
        if rgb.shape[2] == 1:
            rgb = np.repeat(rgb, 3, axis=2)
        elif rgb.shape[2] > 3:
            rgb = rgb[..., :3]
    else:                                   # 2-D mono → grey RGB
        rgb = np.stack([arr, arr, arr], axis=-1)

    w = rgb.shape[1]
    if w > max_width:
        # Decimate by striding (nearest) rather than box-averaging. Stack FITS
        # carry NaN in uncovered/mosaic-gap regions; box averaging (and a plain
        # min/max normalize) would smear NaN across the whole frame and blank
        # it out. Striding preserves NaN so the NaN-aware stretch below can
        # exclude those pixels — and it's faster, which suits live previews.
        step = int(np.ceil(w / max_width))
        rgb = rgb[::step, ::step]
    return rgb, display_space


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


def stack_north_up_deg(fits_path: str | Path) -> float | None:
    """The rotation (deg) that orients a stack's stored master so celestial North
    is up, read from its own WCS — or ``None`` when the run carries no usable WCS
    (older/edited runs). Lets the UI decide whether to offer a "North up" option
    (only when a real, more-than-trivial correction exists)."""
    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.render.orient import north_up_rotation_deg

    wcs, w, h = celestial_wcs_from_fits(fits_path)
    return north_up_rotation_deg(wcs, w, h)


def _apply_north_up(disp: np.ndarray, fits_path: str | Path) -> np.ndarray:
    """Rotate a display image so North is up, using the FITS's own WCS. A missing
    WCS or a sub-threshold correction leaves the pixels unchanged, so the render
    never breaks or needlessly resamples."""
    from seestack.render.orient import NORTH_UP_MIN_DEG, rotate_image_north_up

    angle = stack_north_up_deg(fits_path)
    if angle is None or abs(angle) < NORTH_UP_MIN_DEG:
        return disp
    return np.clip(rotate_image_north_up(disp, angle), 0.0, 1.0)


def orient_preview_north_up(preview_png: bytes, fits_path: str | Path) -> bytes:
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
    png_bytes_to_jpeg`."""
    import io

    from PIL import Image

    from seestack.render.orient import NORTH_UP_MIN_DEG, rotate_image_north_up

    angle = stack_north_up_deg(fits_path)
    if angle is None or abs(angle) < NORTH_UP_MIN_DEG:
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

    arr = np.asarray(_fits.getdata(fits_path), dtype=np.float32)
    if arr.ndim == 3:                       # (channels, H, W) → covered = any channel finite
        return np.isfinite(arr).any(axis=0)
    return np.isfinite(arr)                 # 2-D mono


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

    mask = np.asarray(coverage_mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("coverage_mask must be 2-D")
    im = Image.open(io.BytesIO(preview_png)).convert("RGB")
    w, h = im.size
    alpha_img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
        (w, h), Image.NEAREST)
    rgba = np.dstack([np.asarray(im, dtype=np.uint8),
                      np.asarray(alpha_img, dtype=np.uint8)])
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def asinh_stretch(
    rgb: np.ndarray,
    *,
    stretch: float = 0.5,
    black: float = 0.35,
    protect_highlights: bool = True,
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
    """
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
        x = _highlight_rolloff(xr) if protect_highlights else np.clip(xr, 0.0, 1.0)
        out[..., c][finite] = np.clip(np.arcsinh(x / a) / denom, 0.0, 1.0)

    return out


def autostretch(
    rgb: np.ndarray,
    *,
    target_bg: float = 0.20,
    sigma_factor: float = -2.0,
    protect_highlights: bool = True,
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
    """
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
        x = _highlight_rolloff(xr) if protect_highlights else np.clip(xr, 0.0, 1.0)
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
