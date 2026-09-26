"""\"Did it get better?\" as a *picture*: one patch of sky from two of a target's
stacks, side by side, under one shared stretch.

The Target page already asks the question in words — *"put your newest picture
beside the one before it"* — and ``/compare`` answers it with a full A/B route
and a plain-language noise verdict. What a beginner never gets from either is the
thing that actually convinces: **seeing** the grain shrink. A whole-canvas
comparison at card size is exactly the wrong picture for that, because the two
previews are each shrunk by 5–10× and decimation averages the noise away — the
difference the sentence is about is thrown out before it reaches the screen.

So this composes a small, **native-resolution** crop of the same patch of sky
from each of the two masters. Three things make it honest rather than merely
pretty:

* **One stretch, solved once.** The tone curve comes from the *newer* crop and is
  replayed verbatim on the older one, exactly as the deepening reel replays one
  curve across a series (:mod:`seestack.render.deepening`). Autostretching each
  side to its own data — which is what the stored ``_preview.png``s are — moves
  the black point between the halves, and a brightness step reads as a difference
  in quality when it is nothing of the kind.
* **No resampling where it can be avoided.** The crop is read at native
  resolution straight out of the master's memory map, so the grain on screen is
  the grain in the data. When the two canvases are the same shape (the ordinary
  case — same target, same framing) the *same pixel rectangle* is taken from
  both, so neither side is touched. When they differ (a mosaic that grew, or a
  drizzled restack) the rectangle is taken at the same *relative* position and
  both sides are resized to a common size; the result is still a fair picture,
  but the σ comparison is withheld — see below.
* **The number is only offered when its sampling rule holds.**
  :func:`seestack.qc.noise_ratio.noise_ratio` is explicit that both sides must be
  sampled identically, and a resize breaks that in the direction that flatters
  the resampled side. So ``noise_ratio`` here is ``None`` unless the two crops
  came out of identically-shaped canvases at native resolution.

Pure and read-only, like :mod:`seestack.beforeafter`: no webapp import, no
network, nothing written anywhere. The webapp layer resolves the two runs and
serves the bytes.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

#: Native pixels along each side of the crop, and the size each half is drawn at.
#: 320 is the largest square that still reads as a *detail* beside a paragraph of
#: text on a phone (two of them plus a divider is 641 px, which the card scales
#: down by CSS without touching the bytes), and it gives the σ estimator ~80k
#: second-difference triples at its longest lag — comfortably past its own
#: ``_MIN_PAIRS`` floor.
PATCH_PX = 320

#: Below this there is not enough sky in the crop for the estimator or for the
#: eye, so no picture is offered at all rather than a 64-pixel smudge.
MIN_PATCH_PX = 96

#: The crop may not eat the whole canvas: a patch is a *detail*, and one that
#: spans the frame is just the picture again. Also keeps the fractional rect
#: inside both canvases after clamping.
_MAX_PATCH_FRACTION = 0.5

#: Width of the low-resolution view the patch is *chosen* on. Deliberately small:
#: choosing is a cheap search over a decimated copy, and only the winning
#: rectangle is then read at full resolution.
_SCOUT_PX = 384

#: Candidate centres per axis on the scout view. 5×5 is 25 candidates, enough to
#: find faint structure without turning the chooser into a cost.
_SCOUT_GRID = 5

#: The faint band the chooser looks for, in σ above the sky level. Noise *and*
#: emerging faint detail are both visible here; a blown core is not (it is
#: saturated in both halves and shows nothing), and bare sky shows the grain but
#: none of the detail.
_FAINT_LO_SIGMA = 1.0
_FAINT_HI_SIGMA = 8.0

_DIVIDER = (58, 60, 68)     # the hairline :mod:`seestack.beforeafter` draws
_DIVIDER_PX = 2


@dataclass
class NoiseDeltaPatch:
    """The composed picture plus what may honestly be said about it."""

    #: PNG bytes: the older crop, a hairline, then the newer crop.
    png: bytes
    #: Side of each half in the composed image.
    patch_px: int
    #: True when both crops were taken as the *same* pixel rectangle out of
    #: identically-shaped canvases, i.e. neither side was resampled.
    pixel_exact: bool
    #: ``σ_older / σ_newer`` over the crop, or ``None`` when the sampling rule
    #: above does not hold or the estimator declined.
    noise_ratio: float | None


def _luminance(rgb: np.ndarray) -> np.ndarray:
    """Channel-mean luminance, NaN-preserving and quiet about all-NaN pixels."""
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 2:
        return arr
    with warnings.catch_warnings():
        # A fully-uncovered pixel is an "empty slice"; NaN out is the answer we
        # want, so the warning is noise.
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(arr, axis=-1)


def _native_shape(fits_path: str | Path) -> tuple[int, int] | None:
    """``(H, W)`` of a stack FITS's image HDU, read from the header alone."""
    from astropy.io import fits as _fits

    try:
        with _fits.open(fits_path, memmap=True) as hdul:
            for hdu in hdul:
                shape = getattr(hdu, "shape", None)
                if not shape:
                    continue
                if len(shape) == 3:
                    return int(shape[1]), int(shape[2])
                if len(shape) == 2:
                    return int(shape[0]), int(shape[1])
    except Exception as exc:  # noqa: BLE001 — an unreadable master just opts out
        log.warning("noise-delta: could not read %s: %s", fits_path, exc)
    return None


def _read_crop(fits_path: str | Path, y0: int, y1: int,
               x0: int, x1: int) -> np.ndarray | None:
    """The ``(y0:y1, x0:x1)`` rectangle of a stack FITS as ``(h, w, 3)`` float32.

    Slices the memory map per channel so a 150 MP mosaic costs the crop and not
    the canvas — the same reason :func:`seestack.render.thumbnail.load_stack_rgb`
    reads a plane at a time.
    """
    from astropy.io import fits as _fits

    try:
        with _fits.open(fits_path, memmap=True) as hdul:
            data = next((h.data for h in hdul if h.data is not None), None)
            if data is None:
                return None
            if data.ndim == 3 and data.shape[0] > 1:
                planes = [np.asarray(data[c][y0:y1, x0:x1], dtype=np.float32)
                          for c in range(min(data.shape[0], 3))]
                while len(planes) < 3:            # mono-ish cube → grey RGB
                    planes.append(planes[0])
            elif data.ndim == 3:
                plane = np.asarray(data[0][y0:y1, x0:x1], dtype=np.float32)
                planes = [plane, plane, plane]
            elif data.ndim == 2:
                plane = np.asarray(data[y0:y1, x0:x1], dtype=np.float32)
                planes = [plane, plane, plane]
            else:
                return None
    except Exception as exc:  # noqa: BLE001
        log.warning("noise-delta: could not crop %s: %s", fits_path, exc)
        return None
    crop = np.stack(planes, axis=-1)
    if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
        return None
    return crop


def choose_patch_centre(rgb: np.ndarray, patch_frac: float, *,
                        also_covered: np.ndarray | None = None) -> tuple[float, float]:
    """Where to take the crop, as a ``(cx, cy)`` centre in **canvas fractions**.

    Searches a coarse grid over ``rgb`` (a decimated view of the deeper master)
    and keeps the fully-covered candidate carrying the most *faint* signal — the
    band between :data:`_FAINT_LO_SIGMA` and :data:`_FAINT_HI_SIGMA` above the
    sky. That band is where the two things the picture is about both live: the
    grain, and the faint structure a deeper stack pulls out of it. A blown core
    is saturated in both halves and shows neither; bare sky shows only the first.

    ``also_covered`` is the *other* master's view (any size — the rectangle is
    compared fractionally). A candidate ragged in **either** canvas is skipped,
    because a crop that is half an uncovered mosaic corner on one side is not a
    comparison of anything. Checking it here rather than after the fact is what
    lets a target whose older stack has a big NaN corner still get its picture,
    from a patch the two masters share.

    Falls back to the canvas centre when nothing scores — an all-NaN frame, or a
    featureless field — so the caller always gets a rectangle to try.
    """
    h, w = rgb.shape[:2]
    lum = _luminance(rgb)
    finite = np.isfinite(lum)
    if not finite.any():
        return 0.5, 0.5
    from seestack.render.thumbnail import _robust_median_sigma

    med, sigma = _robust_median_sigma(lum[finite])
    lo = med + _FAINT_LO_SIGMA * sigma
    hi = med + _FAINT_HI_SIGMA * sigma
    faint = finite & (lum > lo) & (lum < hi)
    # The box is square in *pixels* on this view, sized as the fraction of the
    # shorter side the caller will use natively, so the search sees the same
    # shape of patch the crop will be.
    box = max(2, int(round(patch_frac * min(h, w))))
    half = box // 2
    best: tuple[float, float, float] | None = None       # (score, cx, cy)
    for gy in range(_SCOUT_GRID):
        for gx in range(_SCOUT_GRID):
            cx_px = int(round((gx + 0.5) * w / _SCOUT_GRID))
            cy_px = int(round((gy + 0.5) * h / _SCOUT_GRID))
            x0 = min(max(0, cx_px - half), max(0, w - box))
            y0 = min(max(0, cy_px - half), max(0, h - box))
            x1, y1 = min(w, x0 + box), min(h, y0 + box)
            window = finite[y0:y1, x0:x1]
            if window.size == 0 or not window.all():
                continue                    # any uncovered pixel disqualifies it
            centre = ((x0 + x1) / 2.0 / w, (y0 + y1) / 2.0 / h)
            if also_covered is not None and not _fully_covered(
                    also_covered, centre[0], centre[1], patch_frac):
                continue
            score = float(faint[y0:y1, x0:x1].mean())
            if best is None or score > best[0]:
                best = (score, centre[0], centre[1])
    if best is None:
        return 0.5, 0.5
    return best[1], best[2]


def _rect_for(shape: tuple[int, int], cx: float, cy: float,
              patch_frac: float) -> tuple[int, int, int, int]:
    """The ``(y0, y1, x0, x1)`` native rectangle for a fractional centre."""
    h, w = shape
    box = max(2, int(round(patch_frac * min(h, w))))
    box = min(box, h, w)
    x0 = int(round(cx * w)) - box // 2
    y0 = int(round(cy * h)) - box // 2
    x0 = min(max(0, x0), w - box)
    y0 = min(max(0, y0), h - box)
    return y0, y0 + box, x0, x0 + box


def _fully_covered(rgb: np.ndarray, cx: float, cy: float,
                   patch_frac: float) -> bool:
    """Whether the same fractional rectangle is covered in this (scout) view too.

    NaN is "no coverage" everywhere in this engine, and a crop that is half a
    ragged mosaic corner on one side is not a comparison — it is two different
    patches of sky.
    """
    lum = _luminance(rgb)
    y0, y1, x0, x1 = _rect_for(lum.shape[:2], cx, cy, patch_frac)
    window = lum[y0:y1, x0:x1]
    return bool(window.size) and bool(np.isfinite(window).all())


def build_noise_delta(older_fits: str | Path, newer_fits: str | Path, *,
                      patch_px: int = PATCH_PX) -> NoiseDeltaPatch | None:
    """Compose the matched-crop picture for two of a target's masters.

    ``None`` — the caller self-hides — when either master is a display-space
    editor export (a bespoke tone curve nothing can be honestly matched to, the
    same gate the one-frame reveal uses), is unreadable, is too small to yield a
    patch, or has no patch of sky covered in both.
    """
    from PIL import Image

    from seestack.stack.output import fits_is_display_space, pack_unit

    for path in (older_fits, newer_fits):
        if not path or not Path(path).exists():
            return None
        try:
            if fits_is_display_space(path):
                return None
        except Exception as exc:  # noqa: BLE001
            log.warning("noise-delta: could not classify %s: %s", path, exc)
            return None

    shape_new = _native_shape(newer_fits)
    shape_old = _native_shape(older_fits)
    if shape_new is None or shape_old is None:
        return None
    want = max(MIN_PATCH_PX, int(patch_px))
    # The patch is sized on the *newer* canvas and then expressed as a fraction,
    # so the two halves cover the same share of the frame even when one canvas
    # grew. A small canvas gets a proportionally smaller patch rather than one
    # that swallows the picture.
    box_new = min(want, int(min(shape_new) * _MAX_PATCH_FRACTION))
    if box_new < MIN_PATCH_PX or min(shape_old) * _MAX_PATCH_FRACTION < MIN_PATCH_PX:
        return None
    patch_frac = box_new / float(min(shape_new))

    from seestack.render.thumbnail import load_stack_rgb

    try:
        scout_new, _ = load_stack_rgb(newer_fits, max_width=_SCOUT_PX)
        scout_old, _ = load_stack_rgb(older_fits, max_width=_SCOUT_PX)
    except Exception as exc:  # noqa: BLE001
        log.warning("noise-delta: could not scout %s: %s", newer_fits, exc)
        return None
    cx, cy = choose_patch_centre(scout_new, patch_frac, also_covered=scout_old)
    if not (_fully_covered(scout_old, cx, cy, patch_frac)
            and _fully_covered(scout_new, cx, cy, patch_frac)):
        # Only reachable via the chooser's own centre fallback (no candidate was
        # covered in both), and there is no "same patch of sky" to show.
        return None

    y0n, y1n, x0n, x1n = _rect_for(shape_new, cx, cy, patch_frac)
    y0o, y1o, x0o, x1o = _rect_for(shape_old, cx, cy, patch_frac)
    crop_new = _read_crop(newer_fits, y0n, y1n, x0n, x1n)
    crop_old = _read_crop(older_fits, y0o, y1o, x0o, x1o)
    if crop_new is None or crop_old is None:
        return None

    # Identical sampling is the precondition the σ ratio rests on: same canvas
    # shape means the *same* pixel rectangle out of both, with no resize on
    # either side. Anything else and the number is withheld rather than guessed.
    pixel_exact = (shape_new == shape_old and crop_new.shape == crop_old.shape)
    ratio: float | None = None
    if pixel_exact:
        from seestack.qc.noise_ratio import noise_ratio

        ratio = noise_ratio(crop_old, crop_new)

    from seestack.render.deepening import _apply_stf_params, _solve_stf_params

    # One curve, solved on the newer crop and replayed on the older one. Solved
    # on the *crop* rather than the whole master deliberately: a whole-frame STF
    # renders a sky patch almost flat, and the grain this picture exists to show
    # would be invisible.
    params = _solve_stf_params(crop_new)
    if params is None:
        return None
    disp_new = _apply_stf_params(crop_new, params)
    disp_old = _apply_stf_params(crop_old, params)

    left = Image.fromarray(pack_unit(disp_old), mode="RGB")
    right = Image.fromarray(pack_unit(disp_new), mode="RGB")
    side = min(want, left.size[0], right.size[0], left.size[1], right.size[1]) \
        if not pixel_exact else left.size[0]
    side = max(MIN_PATCH_PX, int(side))
    if left.size != (side, side):
        left = left.resize((side, side), Image.LANCZOS)
    if right.size != (side, side):
        right = right.resize((side, side), Image.LANCZOS)

    canvas = Image.new("RGB", (side * 2 + _DIVIDER_PX, side), _DIVIDER)
    canvas.paste(left, (0, 0))
    canvas.paste(right, (side + _DIVIDER_PX, 0))

    import io

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return NoiseDeltaPatch(png=buf.getvalue(), patch_px=side,
                           pixel_exact=pixel_exact, noise_ratio=ratio)
