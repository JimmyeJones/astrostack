"""Final-stack gradient removal."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.bg.final_gradient import (
    FinalGradientOptions,
    _build_object_mask,
    remove_final_gradient,
)


def _stack_with_gradient_and_galaxy(h: int = 400, w: int = 600) -> np.ndarray:
    rng = np.random.default_rng(3)
    yy, xx = np.indices((h, w), dtype=np.float32)
    # Gradient brighter on the right.
    grad = (xx / w) * 200 + (yy / h) * 100
    rgb = np.stack([grad + 10, grad + 12, grad + 8], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=2.0, size=rgb.shape).astype(np.float32)
    # Tiny "galaxy" in the centre.
    cy, cx = h // 2, w // 2
    for dy in range(-12, 13):
        for dx in range(-12, 13):
            r2 = dy * dy + dx * dx
            rgb[cy + dy, cx + dx, :] += 200.0 * np.exp(-r2 / 80.0)
    return rgb


def test_disabled_is_passthrough():
    rgb = _stack_with_gradient_and_galaxy()
    out = remove_final_gradient(rgb, FinalGradientOptions(enabled=False))
    np.testing.assert_array_equal(out, rgb)


def test_per_channel_removes_gradient_without_eating_galaxy():
    rgb = _stack_with_gradient_and_galaxy()
    out = remove_final_gradient(
        rgb, FinalGradientOptions(enabled=True, mode="per_channel", box_size=80),
    )
    # Whole-frame median should drop well below the original 200-ADU gradient.
    h, w = rgb.shape[:2]
    for c in range(3):
        # Original median was ~150 ADU; after fit should be < 25 ADU.
        assert abs(np.median(out[..., c])) < 25
    # Galaxy centre should still be bright (>100 ADU above sky).
    cy, cx = h // 2, w // 2
    galaxy_centre = out[cy - 1 : cy + 2, cx - 1 : cx + 2, :].mean()
    assert galaxy_centre > 100


def test_luminance_mode_keeps_color_balance():
    rgb = _stack_with_gradient_and_galaxy()
    out = remove_final_gradient(
        rgb, FinalGradientOptions(enabled=True, mode="luminance", box_size=80),
    )
    for c in range(3):
        assert abs(np.median(out[..., c])) < 25


def test_object_mask_covers_bright_region():
    rgb = _stack_with_gradient_and_galaxy()
    mask = _build_object_mask(rgb, FinalGradientOptions(detect_sigma=2.5, dilate_px=5))
    h, w = rgb.shape[:2]
    cy, cx = h // 2, w // 2
    # Galaxy centre should be in the mask.
    assert mask[cy, cx]
    # Left-edge sky should not be in the mask.
    assert not mask[h // 2, 5]
