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


def estimate_noise_sigma(rgb: np.ndarray) -> float | None:
    """Robust estimate of an image's background-noise σ, in units normalized to
    its own robust signal range (0.5..99.5th percentile) so the value is
    comparable across different gains/exposures.

    Uses adjacent-pixel differences: on a smooth sky background the difference of
    neighbouring pixels is dominated by noise, and the MAD of those differences
    is robust to the minority of large jumps at star/nebula edges. For pure noise
    ``Var(Iᵢ₊₁ − Iᵢ) = 2σ²``, so ``σ = 1.4826·MAD(diff)/√2``.

    Returns ``None`` when there aren't enough finite pixels or the image has no
    dynamic range to normalize against.
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
    norm = (lum - lo) / (hi - lo)

    diffs = []
    for d in (norm[1:, :] - norm[:-1, :], norm[:, 1:] - norm[:, :-1]):
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


def suggest_denoise_strength(rgb: np.ndarray) -> tuple[float | None, float | None]:
    """``(noise_sigma, strength)`` for the denoise op, or ``(None, None)`` when
    the image can't be measured. ``strength`` scales linearly with the normalized
    noise up to ``_SIGMA_FULL``, clamped to the op's usable range and rounded to
    its slider step."""
    sigma = estimate_noise_sigma(rgb)
    if sigma is None:
        return None, None
    raw = sigma / _SIGMA_FULL
    strength = max(_STRENGTH_MIN, min(_STRENGTH_MAX, raw))
    strength = round(strength / _STRENGTH_STEP) * _STRENGTH_STEP
    return round(sigma, 4), round(strength, 2)
