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
* **Identical sampling.** Measure both on native-resolution (or identically
  strided) arrays; never box-average one side and stride the other, or the
  averaged side's noise falls faster and biases the ratio downward.

Both σ are measured *raw* (un-normalized) on the same ADU scale, so their ratio
is the physical noise ratio regardless of each image's absolute pedestal.
"""

from __future__ import annotations

import warnings

import numpy as np

# Need at least this many finite neighbour-difference pairs for a trustworthy MAD.
_MIN_PAIRS = 256
# Object threshold (in rough-σ above the median) above which a pixel is treated as
# signal — a star or a bright target's body/core — and dropped from the noise
# estimate. High enough (many σ) that it never truncates the background *noise*
# distribution itself, so it only ever removes real signal.
_OBJECT_SIGMA = 4.0


def _luminance(rgb: np.ndarray) -> np.ndarray:
    """Channel-mean luminance as a 2-D float array (NaN-preserving)."""
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 2:
        return arr
    with warnings.catch_warnings():
        # Fully-uncovered (all-NaN) pixels yield a harmless "empty slice" warning.
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(arr, axis=-1)


def _diff_sigma(lum: np.ndarray, keep: np.ndarray) -> float | None:
    """σ from the MAD of adjacent-pixel differences where *both* endpoints are in
    ``keep``. For pure noise ``Var(Iᵢ₊₁ − Iᵢ) = 2σ²`` → ``σ = 1.4826·MAD/√2``."""
    diffs = []
    for a, b, ka, kb in (
        (lum[:, 1:], lum[:, :-1], keep[:, 1:], keep[:, :-1]),
        (lum[1:, :], lum[:-1, :], keep[1:, :], keep[:-1, :]),
    ):
        valid = ka & kb
        d = (a - b)[valid]
        if d.size:
            diffs.append(d)
    if not diffs:
        return None
    d = np.concatenate(diffs)
    if d.size < _MIN_PAIRS:
        return None
    mad = float(np.median(np.abs(d - np.median(d))))
    sigma = 1.4826 * mad / np.sqrt(2.0)
    if not np.isfinite(sigma) or sigma <= 0:
        return None
    return sigma


def _background_sigma(lum: np.ndarray) -> float | None:
    """Raw robust background-noise σ of a 2-D luminance array.

    On smooth sky the difference of neighbouring pixels is dominated by noise and
    its MAD is robust to the minority of large jumps at star edges. To also keep a
    *bright extended target* (an edge-on galaxy/nebula, not a minority of pixels)
    out of the estimate, a second pass drops clearly-bright pixels at a high object
    threshold (``median + _OBJECT_SIGMA·σ``) — far enough above sky that it removes
    real signal without truncating the background noise distribution — and
    re-measures over what remains.

    Returns ``None`` when there aren't enough finite pairs to trust the MAD.
    """
    if lum.ndim != 2:
        return None
    finite = np.isfinite(lum)
    # Pass 1: rough σ from all finite neighbour differences (robust to stars).
    rough = _diff_sigma(lum, finite)
    if rough is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = float(np.nanmedian(lum))
    if not np.isfinite(med):
        return rough
    # Pass 2: re-measure over the background (drop signal pixels).
    keep = finite & (lum <= med + _OBJECT_SIGMA * rough)
    refined = _diff_sigma(lum, keep)
    return refined if refined is not None else rough


def noise_ratio(sub_rgb: np.ndarray, stack_rgb: np.ndarray) -> float | None:
    """Background-noise reduction factor ``σ_sub / σ_stack``, or ``None`` when
    either side can't be measured.

    Both inputs must be **linear** arrays on the **same ADU scale** and sampled
    the same way (see the module docstring); the returned ratio is then the
    physical background-noise reduction stacking achieved, landing near
    √(n_frames) for a healthy weighted-mean stack.
    """
    sub_sigma = _background_sigma(_luminance(sub_rgb))
    stack_sigma = _background_sigma(_luminance(stack_rgb))
    if sub_sigma is None or stack_sigma is None or stack_sigma <= 0:
        return None
    ratio = sub_sigma / stack_sigma
    if not np.isfinite(ratio) or ratio <= 0:
        return None
    return float(ratio)
