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
from seestack.edit.registry import as_rgb, luminance

#: Display luminance at or above which a pixel counts as "at the ceiling". The
#: stretch clips to 1.0, so a blown core is a plateau of exactly 1.0; the small
#: slack admits the dithered rim around it.
_CEILING = 0.98

#: A core must cover at least this fraction of the covered pixels before it is
#: worth a suggestion. Scale-invariant on purpose (the measurement runs on the
#: editor proxy, whose size varies): 0.01 % is ~65 px on a 1000×650 proxy, which
#: is far more than a saturated *star* (a few pixels) and far less than a
#: washed-out galaxy/nebula core.
_MIN_CORE_AREA_FRAC = 1e-4
#: ...with an absolute floor so a tiny test/thumbnail image can't qualify a star.
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
#: button is worth offering. The knob walks the shoulder's knee down *before*
#: the midtones transfer, so on a very high-contrast frame (a sky median at a
#: thousandth of the normalization ceiling) the transfer squashes the whole
#: shoulder back together and the slider barely moves the picture. Offering a
#: suggestion there would be a button that does nothing, so say nothing instead.
_MIN_IMPROVEMENT = 0.05

#: The op's slider bounds/step (``tone.stretch``'s ``highlights`` param).
_STRENGTH_STEP = 0.05
_STRENGTH_MIN = 0.05
_STRENGTH_MAX = 1.0


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
    """The op's own slider steps, ascending — the only values worth suggesting."""
    n = int(round((_STRENGTH_MAX - _STRENGTH_MIN) / _STRENGTH_STEP)) + 1
    return [round(_STRENGTH_MIN + i * _STRENGTH_STEP, 2) for i in range(n)]


def measure_blown_core(display: np.ndarray,
                       linear: np.ndarray) -> tuple[np.ndarray, np.ndarray, int] | None:
    """``(core_mask, linear_has_structure, core_px)`` for the largest blown core.

    ``display`` is the image as the user sees it (post-stretch, 0..1 with NaN for
    uncovered pixels); ``linear`` is the image the stretch received, at the same
    shape. ``None`` means there is nothing to work with — no bright core at all,
    or one too small to be anything but a star.
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
    if area < max(_MIN_CORE_PX, int(_MIN_CORE_AREA_FRAC * n_covered)):
        return None

    # Structure in linear: normalize to the linear image's own robust range so
    # the threshold is comparable across gains/exposures, then call a gradient
    # "real" only when it clears a quarter of the measured grain. A core flat
    # here too was saturated at capture — nothing for the knob to recover.
    lum_l = luminance(lin)
    lo = float(np.nanpercentile(lum_l, 0.5))
    hi = float(np.nanpercentile(lum_l, 99.5))
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    norm_l = (lum_l - lo) / (hi - lo)
    sigma = estimate_noise_sigma(lin)
    tol = max(_FLAT_EPS, _LINEAR_STRUCTURE_SIGMA * sigma) if sigma else _FLAT_EPS
    return core, _local_gradient(norm_l) > tol, area


def _recoverable_flat_fraction(display: np.ndarray, core: np.ndarray,
                               linear_has_structure: np.ndarray, area: int) -> float:
    """Share of ``core`` that is flat in ``display`` yet structured in linear."""
    lum_d = luminance(as_rgb(np.asarray(display, dtype=np.float32)))
    flat = _local_gradient(lum_d) <= _FLAT_EPS
    return float(np.count_nonzero(core & flat & linear_has_structure)) / float(area)


def suggest_highlight_protect(
    linear: np.ndarray,
    restretch: Callable[[float], np.ndarray],
) -> BlownCore | None:
    """Solve the "Hold back highlights" strength for the caller's own stretch.

    ``restretch(p)`` must render ``linear`` through the stretch the user has
    configured with ``highlights=p`` — so the value returned is solved against
    the very op that will draw it. Returns ``None`` when there is no recoverable
    blown core: no bright core at all, one too small to be anything but a star,
    one barely clipped, one already saturated in the linear data, or one the
    knob can't meaningfully reopen even at full strength.

    The search is a bisection over the op's own slider steps, which is sound
    because more protection can only pull the shoulder in further — the flat
    share is monotone non-increasing in the strength.
    """
    base = restretch(0.0)
    measured = measure_blown_core(base, linear)
    if measured is None:
        return None
    core, linear_has_structure, area = measured

    def flat_at(p: float) -> float:
        return _recoverable_flat_fraction(
            restretch(p), core, linear_has_structure, area)

    severity = _recoverable_flat_fraction(base, core, linear_has_structure, area)
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
    return BlownCore(strength=strength, flat_fraction=round(severity, 3), core_px=area)
