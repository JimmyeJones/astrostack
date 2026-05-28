"""
NaN-aware autostretch + linear TIFF normalization.

The mosaic union canvas has large uncovered (NaN) regions. The export/stretch
code must compute its statistics over the *covered* pixels only — otherwise
those NaN-as-zero regions drag the per-channel black point to ~0 and corrupt
the colour balance (the "extremely red mosaic" bug).
"""

import numpy as np
import pytest

from seestack.gui.thumbnail import autostretch
from seestack.stack.output import _autostretch_for_export, _to_uint16_linear


def _covered_image_with_nan_gaps(h=200, w=300, *, gap_fraction=0.5):
    """A neutral-grey 'sky' image where ``gap_fraction`` of the canvas is NaN."""
    rng = np.random.default_rng(0)
    # Neutral sky: all 3 channels at ~1000 ADU with matched noise.
    img = rng.normal(1000.0, 30.0, size=(h, w, 3)).astype(np.float32)
    # A few bright neutral stars.
    for _ in range(20):
        y = int(rng.integers(10, h - 10))
        x = int(rng.integers(10, w - 10))
        img[y - 2:y + 3, x - 2:x + 3, :] += 8000.0
    # Carve a big NaN region (uncovered canvas).
    gap_cols = int(w * gap_fraction)
    img[:, :gap_cols, :] = np.nan
    return img


def test_autostretch_ignores_nan_gaps_keeps_color_neutral():
    """A neutral image with NaN gaps must stretch to a neutral (grey) result —
    the NaN region must not introduce a colour cast."""
    img = _covered_image_with_nan_gaps(gap_fraction=0.5)
    out = autostretch(img)
    # Covered region only.
    covered = np.isfinite(img[..., 0])
    r = out[..., 0][covered]
    g = out[..., 1][covered]
    b = out[..., 2][covered]
    # The three channels' medians should be close — neutral sky stays neutral.
    mr, mg, mb = np.median(r), np.median(g), np.median(b)
    spread = max(mr, mg, mb) - min(mr, mg, mb)
    assert spread < 0.06, f"channel medians diverged: R={mr:.3f} G={mg:.3f} B={mb:.3f}"
    # And the sky should land near the target_bg (0.20 default), not crushed to 0.
    assert 0.08 < mg < 0.45


def test_autostretch_without_nan_still_works():
    """Regression: a fully-covered image (no NaN) still stretches sanely."""
    rng = np.random.default_rng(1)
    img = rng.normal(1000.0, 30.0, size=(100, 120, 3)).astype(np.float32)
    out = autostretch(img)
    assert out.shape == img.shape
    assert np.isfinite(out).all()
    assert 0.0 <= out.min() and out.max() <= 1.0


def test_autostretch_all_nan_returns_zeros():
    img = np.full((20, 20, 3), np.nan, dtype=np.float32)
    out = autostretch(img)
    assert out.shape == img.shape
    assert np.all(out == 0.0)


def test_to_uint16_linear_skips_nan_for_percentiles():
    """The linear TIFF percentile range must come from covered pixels only."""
    img = _covered_image_with_nan_gaps(gap_fraction=0.6)
    u16 = _to_uint16_linear(img)
    assert u16.dtype == np.uint16
    covered = np.isfinite(img[..., 0])
    # Uncovered region → 0 (black).
    assert np.all(u16[~covered] == 0)
    # Covered sky should use a healthy chunk of the 16-bit range, not be
    # crushed near zero by the NaN-region zeros.
    covered_vals = u16[covered]
    assert covered_vals.max() > 30000  # bright stars reach high
    assert np.median(covered_vals) > 200  # sky isn't crushed to black


def test_autostretch_for_export_passes_nan_through():
    """_autostretch_for_export must not pre-zero NaN — it should rely on
    autostretch's nan-awareness."""
    img = _covered_image_with_nan_gaps(gap_fraction=0.5)
    out = _autostretch_for_export(img)
    covered = np.isfinite(img[..., 0])
    # Same neutrality check as the direct autostretch test.
    mr = np.median(out[..., 0][covered])
    mg = np.median(out[..., 1][covered])
    mb = np.median(out[..., 2][covered])
    spread = max(mr, mg, mb) - min(mr, mg, mb)
    assert spread < 0.06
