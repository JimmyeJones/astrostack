"""Measure a blown-out bright core and solve the stretch's "Hold back
highlights" strength that reopens it, so the knob gets the "from your image"
partner every sibling detail slider already has.

``tone.stretch``'s ``highlights`` slider (v0.237.0) starts at 0 and only moves
when the user notices their galaxy/nebula core has washed out to flat white —
but a beginner has to *know* to look. Sharpen has "size it from your stars",
denoise has "from your image"; this module is that partner's measurement.

Two things make it trustworthy rather than a guessed constant:

* **It only offers a rescue that can happen.** A core genuinely saturated in the
  *linear* data has no gradient left to bring back, and holding the highlights
  back would merely darken it. A core that is flat only *after* the stretch is
  exactly what the knob fixes. The two are told apart by looking at the same
  pixels in the linear image the stretch received: flat in display but
  structured in linear = recoverable; flat in both = lost at capture, so the
  answer is "no suggestion" rather than a promise.
* **The number is solved, not mapped.** Rather than converting a severity score
  into a strength by a made-up curve, it re-runs the caller's own stretch at
  increasing protection and returns the *smallest* strength that actually
  reopens the core. So the value is the least change that does the job, and the
  op it was solved against is the op that will render it.

Nothing here changes a picture on its own. It backs a button the user presses,
whose result is visible in the preview immediately and is undone by dragging the
slider back — which is why it can ship without the real-data threshold tuning
that gates an *automatic* highlight-clip cue.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from seestack.edit.noise import estimate_noise_sigma
from seestack.edit.registry import as_rgb, luminance, param_grid

#: Display luminance at or above which a pixel counts as "at the ceiling". The
#: stretch clips to 1.0, so a blown core is a plateau of exactly 1.0; the small
#: slack admits the dithered rim around it.
_CEILING = 0.98

#: A core must cover at least this fraction of the covered pixels before it is
#: worth a suggestion. Scale-invariant on purpose (the measurement runs on the
#: editor proxy, whose size varies): 0.01 % is ~65 px on a 1000×650 proxy, which
#: is far more than a saturated *star* (a few pixels) and far less than a
#: washed-out galaxy/nebula core. On a mosaic the share is of **one frame's**
#: footprint, not of the whole canvas — see :func:`_min_core_area`.
_MIN_CORE_AREA_FRAC = 1e-4
#: ...with an absolute floor so a tiny test/thumbnail image can't qualify a star.
#: Counted in **native** pixels (a star's size does not shrink with the proxy).
_MIN_CORE_PX = 32

#: Local gradient (in display units, 0..1) at or below which a pixel counts as
#: flat. A hard-clipped plateau is *exactly* flat; this is 0.1 % of the full
#: display range, comfortably below any real core gradient.
_FLAT_EPS = 1e-3

#: How much of the linear noise a local gradient must clear to count as real
#: structure. Below this the "detail" in the linear data is grain, not a core
#: gradient, so there is nothing for the knob to bring back.
_LINEAR_STRUCTURE_SIGMA = 0.25

#: Share of the core that must be flat-but-recoverable before it is worth
#: saying anything. Below this the core is barely clipped; a nudge would be
#: noise. Calibrated so a core already saturated in the data (whose recoverable
#: share is only the thin rim before the capture clip) stays silent.
_MIN_SEVERITY = 0.10

#: Target the solver drives the recoverable-flat share down to. Not 0: the rim
#: of any bright core is flat within a thousandth of a display unit no matter
#: how hard the shoulder is pulled in, so demanding zero would always return the
#: maximum strength.
_TARGET_FLAT = 0.10

#: How much of the core the strongest setting must actually reopen before the
#: button is worth offering. Offering a suggestion the slider cannot deliver
#: would be a button that does nothing, so say nothing instead. *(Until v0.424.0
#: this fired on exactly the frames the knob is most needed for: the knee walks
#: down **before** the midtones transfer, and on a very high-contrast frame — a
#: sky median at a ten-thousandth of the normalization ceiling — the transfer
#: squashed the whole shoulder back into the last thousandth of the display
#: range, so the slider did not visibly move the picture at any strength. The
#: stretch now reserves the shoulder display room of its own, so the guard is
#: back to catching only genuinely hopeless cores.)*
_MIN_IMPROVEMENT = 0.05


def _per_native_px(gradient: np.ndarray, proxy_scale: float) -> np.ndarray:
    """A proxy-pixel gradient expressed per *native* (export) pixel.

    The two flatness tests above are thresholds on a one-pixel difference, but
    on the strided editor proxy one pixel spans ``proxy_scale`` native pixels,
    so the same smooth core reads ``proxy_scale``× steeper there. Measured raw,
    fewer core pixels counted as flat, the severity fell with the step and the
    solver stopped lower: one blown core got 1.00 on a native render, 0.70 on a
    single S30 field's step-2 proxy, 0.40 on his 2×2 mosaic's step-3 one — and
    the step-3 answer left the exported core still blown. Dividing by the step
    puts every proxy on the export's scale. ``proxy_scale <= 1`` (the export,
    and any proxy that needed no decimation) is returned untouched.
    """
    scale = float(proxy_scale)
    if not np.isfinite(scale) or scale <= 1.0:
        return gradient
    return gradient / np.float32(scale)


def _min_core_area(n_covered: int, proxy_scale: float = 1.0,
                   frame_px: float | None = None) -> float:
    """The smallest core, **in proxy pixels**, worth a suggestion.

    The floor is there to keep a saturated *star* from being called a core, and
    a star is a fixed size on the sky — so the floor must not grow with the
    canvas, and must not stay fixed while the proxy's step shrinks the core.
    Until v0.505.22 it did both: ``_MIN_CORE_AREA_FRAC`` was a share of the
    *whole* covered canvas (a 2×2 mosaic's canvas catches ~3.5× a single field's
    sky, so the same galaxy core had to be ~3.5× bigger), and ``_MIN_CORE_PX``
    was counted in proxy pixels while a step-``s`` proxy shows the core at
    ``1/s²`` of its native area. Measured on the dogfood scale pair: one blown
    core read 91 px against a floor of 53 on the step-1 2×2 and got "Hold back
    highlights (0.05)"; on its full-size step-2 twin it read 24 proxy px
    (≈ 96 native) against 46 and got nothing.

    So: the share is taken of ``min(canvas, one frame)`` — ``frame_px`` is one
    sub's footprint in **canvas** pixels (drizzle included), ``None`` when the
    caller doesn't know it, which keeps the canvas share — and the absolute
    floor is ``_MIN_CORE_PX`` native pixels, i.e. ``_MIN_CORE_PX / s²`` proxy
    ones. ``proxy_scale <= 1`` with no ``frame_px`` is exactly the old floor.
    """
    scale = float(proxy_scale)
    if not np.isfinite(scale) or scale < 1.0:
        scale = 1.0
    area_px = float(n_covered)
    if frame_px is not None and np.isfinite(frame_px) and frame_px > 0:
        area_px = min(area_px, float(frame_px) / (scale * scale))
    return max(_MIN_CORE_PX / (scale * scale),
               float(int(_MIN_CORE_AREA_FRAC * area_px)))


@dataclass(frozen=True)
class BlownCore:
    """A measured, *recoverable* blown-out core and the strength that reopens it.

    ``strength`` is the suggested ``highlights`` value — the smallest one on the
    slider's own step grid that brings the core back. ``flat_fraction`` is the
    share of the core that was flat white in display but still carried structure
    in the linear data at strength 0 (the severity the button reports), and
    ``core_px`` is the size of the core it measured, so the UI can say what it
    looked at.
    """

    strength: float
    flat_fraction: float
    core_px: int


def _local_gradient(values: np.ndarray) -> np.ndarray:
    """Magnitude of the local gradient of a 2-D array, NaN-safe.

    ``np.gradient`` would propagate a NaN neighbour across the whole
    neighbourhood; uncovered pixels are common on a mosaic canvas, so use
    forward/backward differences that treat a non-finite neighbour as "no
    information" (contributing 0) instead of poisoning the pixel. Each pixel
    takes the larger of its two neighbouring differences on each axis, so a
    plateau's *interior* reads 0 while its edge does not.
    """
    filled = np.where(np.isfinite(values), values, np.nan)
    out = np.zeros(filled.shape, dtype=np.float32)
    for axis in (0, 1):
        d = np.abs(np.diff(filled, axis=axis))
        d = np.where(np.isfinite(d), d, 0.0).astype(np.float32, copy=False)
        pad_lo: list[tuple[int, int]] = [(0, 0), (0, 0)]
        pad_hi: list[tuple[int, int]] = [(0, 0), (0, 0)]
        pad_lo[axis] = (1, 0)
        pad_hi[axis] = (0, 1)
        out = np.maximum(out, np.pad(d, pad_lo))
        out = np.maximum(out, np.pad(d, pad_hi))
    return out


def _largest_bright_component(bright: np.ndarray) -> tuple[np.ndarray, int] | None:
    """``(mask, area)`` of the largest 8-connected component of ``bright``."""
    if not bright.any():
        return None
    from scipy.ndimage import label

    lab, n = label(bright, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return None
    counts = np.bincount(lab.ravel())
    counts[0] = 0                      # label 0 is the background
    top = int(counts.argmax())
    return lab == top, int(counts[top])


def _strength_grid() -> list[float]:
    """The op's own slider stops, ascending, minus the no-op at the bottom.

    Read off the ``highlights`` ``EditParam`` rather than from a copy of its
    bounds here, which is what this module used to keep: a strength off those
    stops cannot be reached by dragging the slider, and the editor's readout
    beside it would print a different number from the button that offered it. 0
    is dropped because a suggestion to change nothing is not a suggestion.
    """
    return [v for v in param_grid("tone.stretch", "highlights") if v > 0.0]


def _linear_reference(linear: np.ndarray) -> tuple[float, float, float | None] | None:
    """``(lo, hi, sigma)`` the linear-structure test is normalised by.

    The linear image's own robust range (0.5–99.5th percentile of luminance) and
    its grain in those units. Taken from the **whole picture**: a native window
    round the core is dominated by the core, so measuring there would change the
    yardstick along with the grid. ``None`` when the image has no range.
    """
    lin = as_rgb(np.asarray(linear, dtype=np.float32))
    lum_l = luminance(lin)
    lo = float(np.nanpercentile(lum_l, 0.5))
    hi = float(np.nanpercentile(lum_l, 99.5))
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    return lo, hi, estimate_noise_sigma(lin)


def measure_blown_core(display: np.ndarray, linear: np.ndarray,
                       proxy_scale: float = 1.0,
                       frame_px: float | None = None,
                       *, reference: tuple[float, float, float | None] | None = None,
                       min_area: float | None = None,
                       ) -> tuple[np.ndarray, np.ndarray, int] | None:
    """``(core_mask, linear_has_structure, core_px)`` for the largest blown core.

    ``display`` is the image as the user sees it (post-stretch, 0..1 with NaN for
    uncovered pixels); ``linear`` is the image the stretch received, at the same
    shape. ``proxy_scale`` is the native pixels one input pixel spans (the
    editor proxy's step), so gradients are judged per native pixel and the size
    floor is counted in native pixels. ``frame_px`` is one sub's footprint in
    canvas pixels, so a mosaic's floor is one frame's, not the whole canvas's
    (:func:`_min_core_area`). ``reference`` is :func:`_linear_reference` of the
    whole picture, for a caller measuring a *window* of it, and ``min_area``
    replaces the size floor there (the window was chosen round a core that has
    already passed it). ``None``
    means there is nothing to work with — no bright core at all, or one too
    small to be anything but a star.
    """
    disp = as_rgb(np.asarray(display, dtype=np.float32))
    lin = as_rgb(np.asarray(linear, dtype=np.float32))
    if disp.shape[:2] != lin.shape[:2]:
        return None
    lum_d = luminance(disp)
    covered = np.isfinite(lum_d)
    n_covered = int(covered.sum())
    if n_covered < 64:
        return None

    found = _largest_bright_component(covered & (lum_d >= _CEILING))
    if found is None:
        return None
    core, area = found
    floor = (_min_core_area(n_covered, proxy_scale, frame_px)
             if min_area is None else float(min_area))
    if area < floor:
        return None

    # Structure in linear: normalize to the linear image's own robust range so
    # the threshold is comparable across gains/exposures, then call a gradient
    # "real" only when it clears a quarter of the measured grain. A core flat
    # here too was saturated at capture — nothing for the knob to recover.
    ref = _linear_reference(lin) if reference is None else reference
    if ref is None:
        return None
    lo, hi, sigma = ref
    norm_l = (luminance(lin) - lo) / (hi - lo)
    tol = max(_FLAT_EPS, _LINEAR_STRUCTURE_SIGMA * sigma) if sigma else _FLAT_EPS
    return core, _per_native_px(_local_gradient(norm_l), proxy_scale) > tol, area


def _recoverable_flat_fraction(display: np.ndarray, core: np.ndarray,
                               linear_has_structure: np.ndarray, area: int,
                               proxy_scale: float = 1.0) -> float:
    """Share of ``core`` that is flat in ``display`` yet structured in linear."""
    lum_d = luminance(as_rgb(np.asarray(display, dtype=np.float32)))
    flat = _per_native_px(_local_gradient(lum_d), proxy_scale) <= _FLAT_EPS
    return float(np.count_nonzero(core & flat & linear_has_structure)) / float(area)


#: A native window round the core is read only when the proxy is decimated and
#: the core is small enough for its rim to matter; a window bigger than this per
#: side means a big core, whose proxy measurement already holds (r=12: 0.506 /
#: 0.494 / 0.503 at steps 1/2/3), and is the same bound the full-size check reads.
_NATIVE_WINDOW_MAX_PX = 1024

#: Sky kept round the core's bounding box in the native window, in proxy pixels
#: (at least; half the core's own extent when that is more), so the rim and the
#: shoulder outside it are measured with their real neighbours.
_NATIVE_WINDOW_PAD = 4

#: ``native_window(y0, x0, h, w)`` — that rectangle of the picture in **source**
#: (full-resolution) pixels, as ``(linear, restretch)``: the image the stretch
#: receives there, and a function rendering it through the caller's stretch at a
#: given ``highlights`` with the *whole picture's* fitted statistics. ``None`` when
#: the window can't be rendered faithfully, and the proxy measurement stands.
NativeWindow = Callable[[int, int, int, int],
                        "tuple[np.ndarray, Callable[[float], np.ndarray]] | None"]

_UNANSWERED = object()


def _native_window_bounds(core: np.ndarray, proxy_scale: float,
                          ) -> tuple[int, int, int, int] | None:
    """``(y0, x0, h, w)`` in source pixels round the proxy core's bounding box,
    or ``None`` when that window would be bigger than :data:`_NATIVE_WINDOW_MAX_PX`.

    Proxy pixel ``(r, c)`` is source pixel ``(r·s, c·s)`` (``build_proxy``
    strides from the origin), so the window holds every core pixel the proxy saw.
    It is not clamped to the canvas here: the caller knows the canvas.
    """
    rows = np.flatnonzero(core.any(axis=1))
    cols = np.flatnonzero(core.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    s = int(round(proxy_scale))
    ext = max(int(rows[-1] - rows[0]), int(cols[-1] - cols[0])) + 1
    pad = max(_NATIVE_WINDOW_PAD, ext // 2)
    y0 = max(0, int(rows[0]) - pad) * s
    x0 = max(0, int(cols[0]) - pad) * s
    y1 = (int(rows[-1]) + 1 + pad) * s
    x1 = (int(cols[-1]) + 1 + pad) * s
    if max(y1 - y0, x1 - x0) > _NATIVE_WINDOW_MAX_PX:
        return None
    return y0, x0, y1 - y0, x1 - x0


def _solve(base: np.ndarray, restretch: Callable[[float], np.ndarray],
           core: np.ndarray, linear_has_structure: np.ndarray, area: int,
           proxy_scale: float, core_px: int) -> BlownCore | None:
    """The severity gate and the strength search, on one grid."""
    def flat_at(p: float) -> float:
        return _recoverable_flat_fraction(
            restretch(p), core, linear_has_structure, area, proxy_scale)

    severity = _recoverable_flat_fraction(
        base, core, linear_has_structure, area, proxy_scale)
    if severity < _MIN_SEVERITY:
        return None

    grid = _strength_grid()
    # What the slider can do at all. If its strongest setting barely dents the
    # blown core, there is no honest suggestion to make.
    strongest = flat_at(grid[-1])
    if severity - strongest < _MIN_IMPROVEMENT:
        return None

    strength = grid[-1]
    if strongest <= _TARGET_FLAT:
        # It reopens fully — find the *smallest* step that already does, so the
        # button is the least change that does the job.
        lo, hi = 0, len(grid) - 2
        while lo <= hi:
            mid = (lo + hi) // 2
            if flat_at(grid[mid]) <= _TARGET_FLAT:
                strength = grid[mid]
                hi = mid - 1
            else:
                lo = mid + 1
    return BlownCore(strength=strength, flat_fraction=round(severity, 3), core_px=core_px)


def _solve_on_native_window(core: np.ndarray, linear: np.ndarray,
                            proxy_scale: float, native_window: NativeWindow,
                            grain_ratio: float | None, core_px: int):
    """The suggestion measured on a native window round the proxy's core, or
    :data:`_UNANSWERED` when no window can be had (the proxy answer stands).

    Why a window and not the proxy. Every per-pixel test here reads a pixel's
    largest neighbour difference, so the core's *rim* — one pixel wide on any
    grid — is scored on the grid's own terms, and on a step-``s`` proxy that rim
    is ``s`` native pixels wide while the core is ``1/s²`` of its area. Measured
    on exponential cores through the real stretch: a small recoverable core read
    0.092 / 0.093 / 0.023 / 0.000 at steps 1–4 (the button went silent on a
    bigger canvas), and a core clipped at capture read 0.060 / 0.120 / 0.164 /
    0.188 (a false button that grew with it). Both are the same effect, and
    cutting the rim off or upsampling the proxy each traded one for the other.
    On the source grid the rim is one native pixel at every step, so the answer
    is the export's own.

    The yardstick is carried from the whole picture: the linear range from
    ``linear`` (the proxy), its grain put back on the source grid by
    ``grain_ratio`` (``seestack.edit.proxy.source_grain_ratio``; ``None`` leaves
    the proxy's σ, which can only call *less* structure), and the stretch's
    statistics by the caller's ``native_window``.
    """
    bounds = _native_window_bounds(core, proxy_scale)
    if bounds is None:
        return _UNANSWERED
    try:
        got = native_window(*bounds)
    except (OSError, ValueError, MemoryError):
        return _UNANSWERED
    if got is None:
        return _UNANSWERED
    lin_w, restretch_w = got
    ref = _linear_reference(linear)
    if ref is None:
        return _UNANSWERED
    lo, hi, sigma = ref
    if (sigma is not None and grain_ratio is not None
            and np.isfinite(grain_ratio) and grain_ratio > 0):
        sigma = float(sigma * grain_ratio)
    base_w = restretch_w(0.0)
    measured = measure_blown_core(base_w, lin_w, 1.0, reference=(lo, hi, sigma),
                                  min_area=1)
    if measured is None:
        return _UNANSWERED
    core_w, structure_w, area_w = measured
    return _solve(base_w, restretch_w, core_w, structure_w, area_w, 1.0, core_px)


def suggest_highlight_protect(
    linear: np.ndarray,
    restretch: Callable[[float], np.ndarray],
    proxy_scale: float = 1.0,
    frame_px: float | None = None,
    native_window: NativeWindow | None = None,
    grain_ratio: float | None = None,
) -> BlownCore | None:
    """Solve the "Hold back highlights" strength for the caller's own stretch.

    ``restretch(p)`` must render ``linear`` through the stretch the user has
    configured with ``highlights=p`` — so the value returned is solved against
    the very op that will draw it. ``proxy_scale`` is the editor proxy's step
    (``EditContext.proxy_scale``): pass it so a decimated proxy is judged on
    the export's scale and the same core gets the same answer at any step.
    ``frame_px`` is one sub's footprint in canvas pixels (``None`` = unknown):
    pass it so a mosaic's core is held to a single field's size floor rather
    than one that grows with the canvas. ``native_window`` (see
    :data:`NativeWindow`) lets a decimated proxy's core be measured on the
    source grid, where its rim is one native pixel at any step
    (:func:`_solve_on_native_window`); ``grain_ratio`` puts the proxy's grain on
    that grid. Without one — or when the window can't be had — the proxy
    answers, as it always has. Returns ``None`` when there is no recoverable
    blown core: no bright core at all, one too small to be anything but a star,
    one barely clipped, one already saturated in the linear data, or one the
    knob can't meaningfully reopen even at full strength.

    *Whether* there is a core worth a word (the size floor) is always decided on
    the proxy, against the whole picture; the window only measures it. The
    search is a bisection over the op's own slider steps, which is sound
    because more protection can only pull the shoulder in further — the flat
    share is monotone non-increasing in the strength.
    """
    base = restretch(0.0)
    measured = measure_blown_core(base, linear, proxy_scale, frame_px)
    if measured is None:
        return None
    core, linear_has_structure, area = measured
    scale = float(proxy_scale)
    if native_window is not None and np.isfinite(scale) and scale > 1.0:
        refined = _solve_on_native_window(core, linear, scale, native_window,
                                          grain_ratio, area)
        if refined is not _UNANSWERED:
            return refined
    return _solve(base, restretch, core, linear_has_structure, area, proxy_scale, area)
