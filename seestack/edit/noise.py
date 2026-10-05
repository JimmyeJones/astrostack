"""Robust background-noise estimation for a data-driven denoise-strength default.

The editor's ``detail.denoise`` op has a 0..1 *strength* knob a beginner can't
reason about. This module estimates the image's background noise and maps it to a
sensible starting strength, offered as a one-click suggestion (the same idiom the
PSF-from-stars button uses for deconvolution).

Pure-numpy on purpose: the estimate must never depend on an optional runtime
(e.g. PyWavelets) that may be absent, and it stays engine-side so it's testable
in isolation from the webapp.
"""

from __future__ import annotations

import warnings

import numpy as np

from seestack.edit.registry import as_rgb

# Normalized background σ at (or above) which the strongest denoise is suggested.
# Noise is measured in units of the image's own robust signal range (see
# ``estimate_noise_sigma``), so this threshold is comparable across gain/exposure.
_SIGMA_FULL = 0.05
# Never suggest a stronger cut than the op allows, nor a no-op — a suggestion the
# user clicks should always do *something* mild even on a clean image.
_STRENGTH_MIN = 0.1
_STRENGTH_MAX = 1.0
_STRENGTH_STEP = 0.05
# Floor on ``grain_lag_ratio``. A real reprojection kernel's correlation bottoms
# out around 0.54 (measured: 1.00 / 0.69 / 0.65 / 0.64 at lags 1..4 on a
# ~0.7 px-correlated field), so this is a rail against a measuring window that
# holds structure rather than sky — far enough below anything physical that it
# never shapes an ordinary answer.
_GRAIN_RATIO_FLOOR = 0.25


def _normalized_luminance(rgb: np.ndarray) -> np.ndarray | None:
    """The image's mean-channel luminance, rescaled to its own robust signal
    range (0.5..99.5th percentile), or ``None`` when it can't be measured.

    Factored out of :func:`estimate_noise_sigma` so the lag sweep next door
    measures its two lags in *one* normalization — see :func:`grain_lag_ratio`,
    whose whole correctness argument is that the scale divides out.
    """
    with warnings.catch_warnings():
        # Fully-uncovered (all-NaN) pixels yield a harmless "empty slice" warning.
        warnings.simplefilter("ignore", RuntimeWarning)
        lum = np.nanmean(as_rgb(np.asarray(rgb, dtype=np.float32)), axis=-1)
    if lum.ndim != 2 or np.isfinite(lum).sum() < 64:
        return None
    lo = float(np.nanpercentile(lum, 0.5))
    hi = float(np.nanpercentile(lum, 99.5))
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    return (lum - lo) / (hi - lo)


def _lag_sigma(norm: np.ndarray, lag: int = 1) -> float | None:
    """σ estimated from pixel differences ``lag`` apart on an already-normalized
    plane, or ``None`` when there is nothing measurable.

    ``lag`` is in the array's *own* pixels. For noise whose pixel-to-pixel
    correlation has died out by that separation this is the honest σ; at a
    separation *shorter* than the correlation length it reads low, because
    ``Var(Iᵢ₊ₗ − Iᵢ) = 2σ²(1 − ρ(l))`` and ``ρ`` has not reached 0 yet. That is
    the whole content of :func:`grain_lag_ratio`.
    """
    if lag < 1:
        return None
    diffs = []
    for d in (norm[lag:, :] - norm[:-lag, :], norm[:, lag:] - norm[:, :-lag]):
        d = d[np.isfinite(d)]
        if d.size:
            diffs.append(d)
    if not diffs:
        return None
    d = np.concatenate(diffs)
    mad = float(np.median(np.abs(d - np.median(d))))
    sigma = 1.4826 * mad / np.sqrt(2.0)
    if not np.isfinite(sigma) or sigma <= 0:
        return None
    return sigma


def estimate_noise_sigma(rgb: np.ndarray) -> float | None:
    """Robust estimate of an image's background-noise σ, in units normalized to
    its own robust signal range (0.5..99.5th percentile) so the value is
    comparable across different gains/exposures.

    Uses adjacent-pixel differences: on a smooth sky background the difference of
    neighbouring pixels is dominated by noise, and the MAD of those differences
    is robust to the minority of large jumps at star/nebula edges. For pure noise
    ``Var(Iᵢ₊₁ − Iᵢ) = 2σ²``, so ``σ = 1.4826·MAD(diff)/√2``.

    **It is a lag-1 estimator, so it answers in the units of the grid it is
    handed** — on a decimated proxy "adjacent" means ``step`` full-resolution
    pixels apart, and a stacker's reprojection leaves the noise correlated over
    ~1 px, so the same sky reads larger through a bigger stride.
    :func:`grain_lag_ratio` measures that factor so a caller working on a proxy
    can put the number back on the full-resolution grid its thresholds were
    calibrated on.

    Returns ``None`` when there aren't enough finite pixels or the image has no
    dynamic range to normalize against.
    """
    norm = _normalized_luminance(rgb)
    if norm is None:
        return None
    return _lag_sigma(norm, 1)


def grain_lag_ratio(rgb: np.ndarray, lag: int) -> float | None:
    """``σ(lag 1) / σ(lag)`` for these pixels — how much *smaller* the lag-1 grain
    estimator reads than the same estimator at a separation of ``lag`` pixels.

    This is the correction a caller measuring noise on a proxy decimated by
    ``step`` needs: the proxy's own lag-1 differences are the full-resolution
    image's lag-``step`` differences (literally the same pixel pairs), so
    multiplying the proxy's σ by this ratio returns the number a lag-1 read of
    the full-resolution image would have given. Both halves are measured on one
    array through :func:`_normalized_luminance`, so the normalization — the part
    that would otherwise have to be calibrated between the two grids — divides
    out exactly and what is left is a property of the noise's correlation alone.

    Consequences worth knowing:

    * **Uncorrelated (white) noise gives 1.0**, because σ does not depend on the
      separation at all. So an image whose grain is already pixel-independent is
      left exactly where it was — the control that says this is a correction and
      not a tuning.
    * ``lag <= 1`` gives 1.0 without measuring anything (nothing to correct).
    * The ratio is **at most 1** by construction: correlation can only shrink the
      short-lag difference. It is clamped there, and to a floor well below
      anything a real reprojection kernel produces, as a rail against a window
      that is all structure rather than sky — never as a tuning knob.

    ``None`` when the pixels can't be measured at either lag.
    """
    lag = int(lag)
    if lag <= 1:
        return 1.0
    norm = _normalized_luminance(rgb)
    if norm is None:
        return None
    near = _lag_sigma(norm, 1)
    far = _lag_sigma(norm, lag)
    if near is None or far is None or far <= 0:
        return None
    return float(np.clip(near / far, _GRAIN_RATIO_FLOOR, 1.0))


def suggest_denoise_strength(rgb: np.ndarray,
                             grain_ratio: float | None = None,
                             ) -> tuple[float | None, float | None]:
    """``(noise_sigma, strength)`` for the denoise op, or ``(None, None)`` when
    the image can't be measured. ``strength`` scales linearly with the normalized
    noise up to ``_SIGMA_FULL``, clamped to the op's usable range and rounded to
    its slider step.

    ``grain_ratio`` is :func:`grain_lag_ratio` for the grid ``rgb`` lives on, for
    a caller measuring a *decimated* proxy: ``_SIGMA_FULL`` is a full-resolution
    bar, so a strided read has to be put back on that grid before it is compared
    against it. ``None`` (the default) or ``1.0`` ⇒ the measurement is taken as
    it comes, which is what a full-resolution caller wants.
    """
    sigma = estimate_noise_sigma(rgb)
    if sigma is None:
        return None, None
    if grain_ratio is not None and np.isfinite(grain_ratio) and 0 < grain_ratio <= 1:
        sigma = float(sigma * grain_ratio)
    raw = sigma / _SIGMA_FULL
    strength = max(_STRENGTH_MIN, min(_STRENGTH_MAX, raw))
    strength = round(strength / _STRENGTH_STEP) * _STRENGTH_STEP
    return round(sigma, 4), round(strength, 2)
