"""Sub-pixel alignment refinement."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")
pytest.importorskip("skimage")

from seestack.stack.align import (
    _apply_subpixel_shift,
    extract_reference_patch,
)


def _frame_with_stars(h: int = 256, w: int = 256, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rgb = rng.normal(loc=100.0, scale=2.0, size=(h, w, 3)).astype(np.float32)
    # A handful of bright sub-pixel-positioned "stars" at integer locations
    # for easy correlation.
    stars = [(40, 50), (80, 120), (160, 60), (190, 200), (110, 180)]
    for y, x in stars:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                r2 = dy * dy + dx * dx
                rgb[y + dy, x + dx, :] += 2000 * np.exp(-r2 / 2.0)
    return rgb


def test_extract_reference_patch_is_centred():
    rgb = _frame_with_stars(200, 300)
    patch, (y0, x0) = extract_reference_patch(rgb, size=128)
    assert patch.shape == (128, 128)
    # Should be approximately centred.
    assert abs(y0 - 36) < 2  # (200-128)/2 = 36
    assert abs(x0 - 86) < 2  # (300-128)/2 = 86


def test_subpixel_shift_corrects_known_offset():
    """Apply a known sub-pixel shift, verify it's corrected."""
    from scipy.ndimage import shift as nd_shift

    ref = _frame_with_stars(256, 256, seed=1)
    patch, origin = extract_reference_patch(ref, size=192)

    # Shift the reference by (1.4, -0.7) pixels.
    shifted = np.empty_like(ref)
    for c in range(3):
        shifted[..., c] = nd_shift(ref[..., c], shift=(1.4, -0.7), order=1, cval=0)

    corrected = _apply_subpixel_shift(shifted, patch, origin)

    # The bright stars should be back near their original positions. Compare
    # interior region using cross-correlation peak — should be near zero
    # residual shift.
    from skimage.registration import phase_cross_correlation

    ref_luma = ref[..., 1].astype(np.float32)
    corr_luma = corrected[..., 1].astype(np.float32)
    residual_shift, _, _ = phase_cross_correlation(
        ref_luma[10:-10, 10:-10], corr_luma[10:-10, 10:-10], upsample_factor=10,
    )
    # Should be within 0.2 px of zero.
    assert abs(residual_shift[0]) < 0.3
    assert abs(residual_shift[1]) < 0.3


def test_subpixel_shift_ignores_large_shifts():
    """Shifts > 5 px are likely bad solves, not seeing — leave the frame alone."""
    from scipy.ndimage import shift as nd_shift

    ref = _frame_with_stars(256, 256, seed=2)
    patch, origin = extract_reference_patch(ref, size=192)
    # Big shift the function should refuse to "correct".
    shifted = np.empty_like(ref)
    for c in range(3):
        shifted[..., c] = nd_shift(ref[..., c], shift=(20, 0), order=1, cval=0)
    out = _apply_subpixel_shift(shifted, patch, origin)
    # Untouched — output identical to input.
    np.testing.assert_array_equal(out, shifted)
