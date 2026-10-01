"""Quantify what stacking bought: the background-noise reduction ratio between a
single sub and the finished stack.

Powers the "stacking cut your noise ~N×" badge on the one-frame-vs-stack reveal.
A weighted-mean stack of ``N`` frames reduces per-pixel background noise by ~√N,
so this ratio lands near √(n_frames) on a healthy stack — a concrete, shareable
number a beginner immediately understands, and a plain reminder of *why* more
subs help.

Pure-numpy, engine-side (no webapp import) so it's unit-testable in isolation.
The honesty of the number rests on two things the caller must respect:

* **Linear domain.** Measure the linear sub (debayered, pre-stretch) against the
  linear master — never the display-stretched preview PNGs, whose non-linear STF
  compresses the sky and would distort a σ ratio.
* **Matched pixel area.** Both sides must describe the same patch of sky per
  pixel. A drizzled master's pixels are *finer* than the sub's, and a finer
  pixel is a **noisier** one — it gathers a smaller share of each frame's light
  — so measuring it as it sits makes the stack look less clean than it is: read
  against ground truth through the real drizzle kernel, the badge comes in
  **11 % low at ×2 and 16 % low at ×3** (``tests/test_noise_ratio_drizzle.py``).
  Pass the run's canvas supersampling as ``stack_supersampling`` and the stack
  side is averaged down to the sub's pixel area before it is measured, which
  brings every scale on the app's own ladder back to within ~3 % of the native
  reading. Never box-average one side and stride the other by hand.

Both σ are measured *raw* (un-normalized) on the same ADU scale, so their ratio
is the physical noise ratio regardless of each image's absolute pedestal.

**Neither side has independent pixels, and the estimator is built for that.**
The classic adjacent-pixel estimator (σ from the MAD of ``Iᵢ₊₁ − Iᵢ``) assumes
neighbouring pixels are independent. Nothing in this pipeline delivers that: the
sub reaches us through :func:`~seestack.io.fits_loader.bilinear_debayer`, and the
master through a registration warp and, on most runs, a drizzle kernel. Every one
of those spreads a pixel's noise into its neighbours, so a lag-1 difference
under-reads σ — and it under-reads the *master* more than the sub, because the
master carries the extra resampling. The ratio inherits the quotient and reads
high; measured against ground truth on a debayer+warp fixture it came in **+9 %**
on a native master and **+119 %** on a 2×-**upsampled** one (see
``tests/test_noise_ratio_correlated.py`` — that upsample is a stand-in whose
blur, unlike the real drizzle kernel, lowers the master's σ; the kernel itself is
measured in ``tests/test_noise_ratio_drizzle.py``). Since the reduction a mean of ``N``
frames can buy is bounded, that inflation is the estimator being fooled and not a
good stack — and its direction is toward *silence*, because
:func:`seestack.stackhealth.noise_vs_expected` only nudges when the number comes
in **low**.

So σ is measured with a **second difference at a lag chosen from the data**:
``I(x−L) − 2·I(x) + I(x+L)``, whose variance is ``6σ²`` for independent noise,
walked over increasing ``L`` until the estimate stops growing (correlation is
what was holding it down, so the plateau is where the pixels being differenced
have finally stopped sharing noise). Two properties make that walk safe:

* a **second** difference is exactly zero on a linear ramp, so a sky gradient —
  which a first difference at a long lag would swallow whole — contributes
  nothing, and the estimate is flat across the plateau rather than climbing
  through it;
* the lag is chosen **per side**, so a 2×-drizzled master (whose correlation is
  twice as wide in its own pixels) is measured at its own lag without the sub
  being dragged along.
"""

from __future__ import annotations

import warnings

import numpy as np

# Need at least this many finite neighbour-difference pairs for a trustworthy MAD.
_MIN_PAIRS = 256
# Cap on how many of them the MAD is actually taken over. A MAD of 400k samples
# is precise to ~0.2 %, the walk below takes up to five of them per side, and the
# reveal card's endpoint is fetched eagerly on every Target-page load — so a
# deterministic odd stride (odd so it can never land on one Bayer phase) buys
# back most of the walk's cost for nothing that shows in the number.
_MAX_PAIRS = 400_000
# Object threshold (in rough-σ above the median) above which a pixel is treated as
# signal — a star or a bright target's body/core — and dropped from the noise
# estimate. High enough (many σ) that it never truncates the background *noise*
# distribution itself, so it only ever removes real signal.
_OBJECT_SIGMA = 4.0
# Pixel lags the estimate is walked over, smallest first. 16 is the ceiling
# because it is already wide enough for a drizzled master (measured: a 2× drizzle
# over a bilinear debayer and a bilinear registration warp plateaus at 8), and a
# lag beyond the correlation length buys nothing while giving real structure more
# room to creep in.
_LAGS = (1, 2, 4, 8, 16)
# The plateau test: a lag that adds less than this to the previous estimate is
# not finding any more correlation, so the walk stops there. Loose enough that
# the MAD's own sampling noise doesn't keep it walking, tight enough that the
# genuine climb out of a correlated regime (which is tens of percent per step)
# never reads as flat.
_PLATEAU_TOL = 0.02
# Largest integer block the stack side may be averaged down by to reach the sub's
# pixel area (see the module docstring's "Matched pixel area"). Eight is well past
# the app's own ceiling — the drizzle ladder stops at
# ``seestack.printexport.DRIZZLE_MAX_USEFUL_SCALE`` — so this only ever binds on a
# nonsense ``drizzle_scale``, which it keeps from binning a crop away to nothing.
_AREA_MATCH_MAX_BLOCK = 8
# …and the smallest side the binned array may come out with. The endpoint measures
# a 1024² crop, which is still 128² at the cap, so this never binds there; it is
# the guard for a caller handing in a small patch, where losing the samples the
# MAD needs would be a worse trade than leaving the sampling unmatched.
_AREA_MATCH_MIN_SIDE = 64


def area_match_block(supersampling: float | None) -> int:
    """How many stack pixels per axis make up one sub pixel's worth of sky.

    ``1`` — i.e. *change nothing* — for a native run, and for anything unusable
    (``None``, non-finite, or below 1.0, which the engine itself clamps: see
    ``webapp.field_fulls._supersampling``). So the only runs measured any
    differently from before are the genuinely super-sampled ones, and a
    non-drizzled library keeps every number it already had.

    Rounded to an integer rather than honoured exactly, because the correction is
    a block mean and a block is whole pixels. Measured across the app's ladder
    (``tests/test_noise_ratio_drizzle.py``): the worst residual a rounded block
    leaves is **3 %** against the native reading, where leaving the sampling
    unmatched costs 11–16 %. An *exact* area-weighted resample was tried and is
    **worse** (+4 to +7 %) — its fractional weights smear neighbouring pixels
    that the drizzle kernel has already correlated, which is the very thing the
    estimator's lag walk is measuring.
    """
    try:
        scale = float(supersampling) if supersampling is not None else 1.0
    except (TypeError, ValueError):
        return 1
    if not np.isfinite(scale) or scale < 1.0:
        return 1
    return int(min(_AREA_MATCH_MAX_BLOCK, max(1, round(scale))))


def _block_mean(lum: np.ndarray, block: int) -> np.ndarray | None:
    """``lum`` averaged over non-overlapping ``block``×``block`` squares.

    A **plain** mean, not a ``nanmean``: a block holding an uncovered pixel comes
    out NaN and is dropped by the estimator's own finite mask, which is the
    engine-wide "NaN = no coverage" rule — a partly-covered block is not a
    background sample, and averaging over whatever part of it happens to be
    covered would put a differently-sampled pixel into the estimate.

    ``None`` when there would not be enough left to measure.
    """
    if block <= 1 or lum.ndim != 2:
        return None
    h = (lum.shape[0] // block) * block
    w = (lum.shape[1] // block) * block
    if min(h, w) // block < _AREA_MATCH_MIN_SIDE:
        return None
    return (lum[:h, :w]
            .reshape(h // block, block, w // block, block)
            .mean(axis=(1, 3))
            .astype(np.float32))


def _luminance(rgb: np.ndarray) -> np.ndarray:
    """Channel-mean luminance as a 2-D float array (NaN-preserving)."""
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 2:
        return arr
    with warnings.catch_warnings():
        # Fully-uncovered (all-NaN) pixels yield a harmless "empty slice" warning.
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(arr, axis=-1)


def _lag_sigma(lum: np.ndarray, keep: np.ndarray, lag: int) -> float | None:
    """σ from the MAD of second differences ``I(x−L) − 2·I(x) + I(x+L)`` taken at
    ``lag`` along both axes, over triples whose three endpoints are all in
    ``keep``. For noise that is independent at that separation
    ``Var = 6σ²`` → ``σ = 1.4826·MAD/√6``; for a linear ramp it is exactly 0, so
    a sky gradient contributes nothing however long the lag."""
    diffs = []
    if lum.shape[0] > 2 * lag:
        valid = keep[2 * lag:] & keep[lag:-lag] & keep[:-2 * lag]
        d = (lum[2 * lag:] - 2.0 * lum[lag:-lag] + lum[:-2 * lag])[valid]
        if d.size:
            diffs.append(d)
    if lum.shape[1] > 2 * lag:
        valid = (keep[:, 2 * lag:] & keep[:, lag:-lag] & keep[:, :-2 * lag])
        d = (lum[:, 2 * lag:] - 2.0 * lum[:, lag:-lag]
             + lum[:, :-2 * lag])[valid]
        if d.size:
            diffs.append(d)
    if not diffs:
        return None
    d = np.concatenate(diffs)
    if d.size < _MIN_PAIRS:
        return None
    if d.size > _MAX_PAIRS:
        step = int(d.size // _MAX_PAIRS) + 1
        if step % 2 == 0:            # odd, so a stride can never land on one
            step += 1                # Bayer phase
        d = d[::step]
    mad = float(np.median(np.abs(d - np.median(d))))
    sigma = 1.4826 * mad / np.sqrt(6.0)
    if not np.isfinite(sigma) or sigma <= 0:
        return None
    return sigma


def _background_sigma(lum: np.ndarray) -> float | None:
    """Raw robust background-noise σ of a 2-D luminance array.

    Two passes and a walk. Pass 1 takes a rough σ at lag 1 over every finite
    pixel — the MAD is robust to the minority of large jumps at star edges, so
    this is good enough to locate the sky. Pass 2 drops clearly-bright pixels at
    a high object threshold (``median + _OBJECT_SIGMA·σ``) — far enough above sky
    that it removes real signal without truncating the background noise
    distribution — which also keeps a *bright extended target* (an edge-on
    galaxy/nebula, not a minority of pixels) out of the estimate.

    The walk over ``_LAGS`` is what makes the number honest on pixels this
    pipeline has correlated (see the module docstring): the estimate climbs as
    the lag leaves the correlation behind and flattens once it has, so the first
    lag that adds less than ``_PLATEAU_TOL`` is where the differenced pixels have
    stopped sharing noise. The rough pass stays at lag 1 deliberately — it only
    has to place the object threshold, and a threshold set from an under-read σ
    is *tighter*, i.e. it keeps less signal, never more.

    Returns ``None`` when there aren't enough finite triples to trust the MAD.
    """
    if lum.ndim != 2:
        return None
    finite = np.isfinite(lum)
    rough = _lag_sigma(lum, finite, 1)
    if rough is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = float(np.nanmedian(lum))
    if not np.isfinite(med):
        return rough
    keep = finite & (lum <= med + _OBJECT_SIGMA * rough)
    best: float | None = None
    previous: float | None = None
    for lag in _LAGS:
        sigma = _lag_sigma(lum, keep, lag)
        if sigma is None:
            break
        if previous is not None and sigma <= previous * (1.0 + _PLATEAU_TOL):
            best = max(previous, sigma)
            break
        previous = sigma
        best = sigma
    return best if best is not None else rough


def noise_ratio(sub_rgb: np.ndarray, stack_rgb: np.ndarray, *,
                stack_supersampling: float | None = 1.0) -> float | None:
    """Background-noise reduction factor ``σ_sub / σ_stack``, or ``None`` when
    either side can't be measured.

    Both inputs must be **linear** arrays on the **same ADU scale** (see the
    module docstring); the returned ratio is then the physical background-noise
    reduction stacking achieved, landing near √(n_frames) for a healthy
    weighted-mean stack.

    ``stack_supersampling`` is how many stack pixels there are per sub pixel
    along one axis — a drizzled run's canvas scale, which
    ``webapp.field_fulls.canvas_supersampling`` reads off the run's own recorded
    options. The stack side is averaged down by that factor first, so both sides
    describe one patch of sky per pixel; the default ``1.0`` leaves it untouched
    and is exactly what every non-drizzled run wants. Pass it whenever you know
    it: a caller that doesn't reads a drizzled stack 11–16 % *worse* than it is
    (module docstring), and the low-noise nudge is the one direction this number
    is acted on.
    """
    stack_lum = _luminance(stack_rgb)
    matched = _block_mean(stack_lum, area_match_block(stack_supersampling))
    if matched is not None:
        stack_lum = matched
    sub_sigma = _background_sigma(_luminance(sub_rgb))
    stack_sigma = _background_sigma(stack_lum)
    if sub_sigma is None or stack_sigma is None or stack_sigma <= 0:
        return None
    ratio = sub_sigma / stack_sigma
    if not np.isfinite(ratio) or ratio <= 0:
        return None
    return float(ratio)
