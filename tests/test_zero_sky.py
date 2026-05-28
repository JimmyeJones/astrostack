"""
Per-frame zero-sky guarantee + auto-engage of final gradient removal on
mosaics.

These two together fix the "panel borders show as brightness steps in the
mosaic" bug: the per-frame ``Background2D`` fit isn't guaranteed to leave a
true zero sky residual (especially with bright targets in some panels), and
the per-panel residual offsets average coherently across each panel and
become visible. The zero-sky pass + masked final gradient cleanup get rid of
those steps.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.bg.per_frame import (
    BackgroundOptions,
    MODE_LUMINANCE,
    MODE_PER_CHANNEL,
    _zero_sky_per_channel,
    subtract_background,
)


def _frame_with_gradient_and_offset(offset: float, gradient_slope: float = 50.0):
    """One synthetic Seestar-like frame with a per-channel offset baked in."""
    rng = np.random.default_rng(int(offset * 1000) & 0xFFFFFF)
    h, w = 256, 384
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad = (xx / w) * gradient_slope
    img = np.stack([grad + 1000 + offset,
                    grad + 1100 + offset,
                    grad + 950 + offset], axis=-1).astype(np.float32)
    img += rng.normal(scale=10.0, size=img.shape).astype(np.float32)
    return img


def test_zero_sky_helper_zeros_sigma_clipped_median():
    rng = np.random.default_rng(0)
    img = rng.normal(loc=42.0, scale=5.0, size=(100, 120, 3)).astype(np.float32)
    # Plant some bright stars — they should NOT bias the sigma-clipped median.
    img[10:13, 20:23, :] += 5000.0
    _zero_sky_per_channel(img)
    for c in range(3):
        # Sigma-clipped median of (~0-mean noise + stars) should be ≈ 0.
        sky_pixels = img[..., c][img[..., c] < 50]
        assert abs(np.median(sky_pixels)) < 2.0


def test_per_channel_bg_flatten_drives_sky_to_zero():
    """After per-channel bg flatten, the sigma-clipped sky median is ~zero
    regardless of what the input frame's sky level was."""
    from astropy.stats import sigma_clipped_stats

    # Two "panels" with very different sky levels (different shooting time).
    a = _frame_with_gradient_and_offset(offset=0.0)
    b = _frame_with_gradient_and_offset(offset=200.0)
    flat_a = subtract_background(a, BackgroundOptions(mode=MODE_PER_CHANNEL, box_size=32),
                                 use_gpu=False)
    flat_b = subtract_background(b, BackgroundOptions(mode=MODE_PER_CHANNEL, box_size=32),
                                 use_gpu=False)
    for c in range(3):
        _, med_a, _ = sigma_clipped_stats(flat_a[..., c], sigma=3.0)
        _, med_b, _ = sigma_clipped_stats(flat_b[..., c], sigma=3.0)
        # Both panels' sky lands at ~0 — they'll average together cleanly.
        assert abs(med_a) < 1.0
        assert abs(med_b) < 1.0
        # And critically, the *difference* between panels is gone.
        assert abs(med_a - med_b) < 1.5


def test_luminance_mode_also_zero_sky():
    from astropy.stats import sigma_clipped_stats
    img = _frame_with_gradient_and_offset(offset=500.0)
    flat = subtract_background(img, BackgroundOptions(mode=MODE_LUMINANCE, box_size=32),
                               use_gpu=False)
    for c in range(3):
        _, med, _ = sigma_clipped_stats(flat[..., c], sigma=3.0)
        assert abs(med) < 1.0
