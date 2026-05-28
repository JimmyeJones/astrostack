"""Per-frame background flatten."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.bg.per_frame import BackgroundOptions, subtract_background  # noqa: E402


def test_subtract_background_removes_gradient():
    """A linear gradient over a noisy sky should come out flat."""
    rng = np.random.default_rng(7)
    h, w = 200, 280
    yy, xx = np.indices((h, w), dtype=np.float32)
    # Per-channel gradients with different slopes — what light pollution looks like.
    grad_r = (xx / w) * 200 + 1000
    grad_g = (yy / h) * 150 + 1100
    grad_b = ((xx + yy) / (h + w)) * 100 + 950
    noise = rng.normal(scale=10.0, size=(h, w, 3)).astype(np.float32)
    rgb = np.stack([grad_r, grad_g, grad_b], axis=-1).astype(np.float32) + noise

    flat = subtract_background(rgb, BackgroundOptions(box_size=32, enabled=True))

    # After flattening, each channel's median should be near zero (the sky
    # level is gone) AND the residual std should be close to the original
    # noise scale of 10 ADU — meaning we've removed the gradient and are
    # left with just pixel noise.
    for c in range(3):
        assert abs(np.median(flat[..., c])) < 5.0
        residual_std = float(np.std(flat[..., c]))
        # Original noise was scale=10. After subtracting a fitted surface, we
        # expect a few percent inflation from the imperfect fit. ≤25 ADU is a
        # generous bound that catches a totally-broken fit while allowing
        # normal residuals.
        assert residual_std < 25.0


def test_subtract_background_disabled_is_passthrough():
    rgb = np.full((100, 100, 3), 1234.5, dtype=np.float32)
    out = subtract_background(rgb, BackgroundOptions(enabled=False))
    np.testing.assert_array_equal(out, rgb)


def test_for_image_size_shrinks_box():
    opts = BackgroundOptions(box_size=200)
    adjusted = opts.for_image_size(100, 100)
    assert adjusted.box_size <= 25  # max_box = min(h, w) // 4


def test_subtract_background_handles_constant():
    """No gradient + no signal — result should still be near zero."""
    rgb = np.full((128, 128, 3), 1500.0, dtype=np.float32)
    out = subtract_background(rgb, BackgroundOptions(box_size=32))
    # Constant input → constant background → zero residual.
    assert np.all(np.abs(out) < 1.0)
