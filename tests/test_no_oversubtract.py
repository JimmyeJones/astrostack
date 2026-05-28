"""
Regression: per-frame bg flatten must not over-subtract on a frame containing
faint diffuse nebulosity.

The previous median-based sky estimate treated nebulosity-above-sky as part
of the "sky" and subtracted it, leaving the residual mean below zero. In a
mosaic that produces the classic darker-where-coverage-is-higher artefact:
N negative residuals averaged together = N times more negative.

The mode-based estimate (``2.5·median − 1.5·mean``) approximates the
histogram mode — the genuine sky peak — and is robust to faint diffuse
signal above it.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from astropy.stats import sigma_clipped_stats

from seestack.bg.per_frame import (
    BackgroundOptions,
    MODE_PER_CHANNEL,
    _zero_sky_per_channel,
    subtract_background,
)


def _frame_with_diffuse_nebula(h=256, w=384, *, sky=1000.0, nebula_amplitude=80.0,
                               seed=7):
    """Sky + Gaussian noise + a large smooth ~Gaussian-blob nebulosity in red."""
    rng = np.random.default_rng(seed)
    img = rng.normal(sky, 15.0, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.indices((h, w), dtype=np.float32)
    cy, cx = h * 0.6, w * 0.4
    blob = nebula_amplitude * np.exp(-((yy - cy) ** 2 / (h * 0.3) ** 2
                                       + (xx - cx) ** 2 / (w * 0.3) ** 2))
    # H-alpha-like: mostly red, small green, almost no blue.
    img[..., 0] += blob
    img[..., 1] += 0.3 * blob
    img[..., 2] += 0.1 * blob
    # A few bright stars to keep DAOStarFinder-style estimators happy.
    for _ in range(15):
        y = int(rng.integers(8, h - 8))
        x = int(rng.integers(8, w - 8))
        img[y - 2:y + 3, x - 2:x + 3, :] += 8000.0
    return img


def test_zero_sky_does_not_over_subtract_on_nebulosity():
    """The sigma-clipped MEAN of the post-flatten background pixels (excluding
    the nebula region) should be near zero — not pulled negative by an
    over-aggressive sky estimate."""
    img = _frame_with_diffuse_nebula()
    flat = subtract_background(
        img, BackgroundOptions(mode=MODE_PER_CHANNEL, box_size=64), use_gpu=False,
    )
    # Sample the corners — far from the nebula blob centred at (60%, 40%).
    corner_pixels = np.concatenate([
        flat[:32, :32, :].reshape(-1, 3),
        flat[:32, -32:, :].reshape(-1, 3),
        flat[-32:, -32:, :].reshape(-1, 3),
    ])
    for c, name in enumerate("RGB"):
        # Sigma-clipped mean of the corner sky — should be near zero.
        clipped_mean, _, _ = sigma_clipped_stats(corner_pixels[:, c], sigma=3.0)
        # The Gaussian blob's faint tail extends slightly into the corners on
        # this synthetic data (~5 ADU at the closest corner), so a small
        # residual bias is unavoidable. The tolerance still rules out the
        # heavy over-subtraction (-20+ ADU) we'd see without the mode +
        # object-mask fixes.
        assert -10.0 < clipped_mean < 10.0, (
            f"channel {name}: corner-sky mean = {clipped_mean:.2f} ADU "
            f"(over-subtracted)"
        )


def test_zero_sky_helper_is_mode_like_on_skewed_data():
    """The helper subtracts the *mode*, not the median, on a positively-skewed
    distribution — leaves diffuse signal above sky positive."""
    rng = np.random.default_rng(0)
    # Sky distribution with a long bright tail (simulates faint nebulosity).
    h, w = 200, 200
    sky = rng.normal(loc=100.0, scale=3.0, size=(h, w, 3)).astype(np.float32)
    # Skewed bright tail: 30% of pixels are 5-15 ADU above sky.
    skew_mask = rng.random((h, w)) < 0.3
    bright = rng.uniform(5.0, 15.0, size=(h, w)).astype(np.float32)
    sky[..., 0] += np.where(skew_mask, bright, 0)
    sky[..., 1] += np.where(skew_mask, 0.5 * bright, 0)
    sky[..., 2] += np.where(skew_mask, 0.2 * bright, 0)

    _zero_sky_per_channel(sky)
    # The mode of the original distribution is at the noise peak (~100).
    # After mode-subtract, that peak lands at 0 and the bright tail stays
    # positive. If we had used the median, the median (≈ peak + ~3 ADU)
    # would have been subtracted, pushing the noise peak negative.
    for c in range(3):
        clean_pixels = sky[..., c][~skew_mask]  # genuine "sky" pixels
        mean_clean = float(np.mean(clean_pixels))
        # The clean-sky mean must be ≥ 0 — never significantly negative.
        assert mean_clean > -1.0, f"channel {c}: clean sky mean {mean_clean:.2f} < 0"
