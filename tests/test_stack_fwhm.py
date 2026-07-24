"""`_compute_stack_fwhm` — the finished stack's own median star size (sharpness).

The per-run counterpart of the noise-σ readout: it measures the combined image's
median FWHM once, normalised to native-frame pixels so a target's stacks are
comparable to each other and to the per-frame QC ``fwhm_px``.
"""

import numpy as np

from seestack.stack.stacker import _compute_stack_fwhm


def _stacked_green(sigma_px: float, size=(240, 320), seed: int = 3) -> np.ndarray:
    """An RGB "stacked" image with a fixed set of round Gaussian stars of a known
    width (``sigma_px``, in the image's own pixels) in the green channel, on a
    gently noisy sky. R/B copy green — colour is irrelevant to a FWHM measured on
    green."""
    h, w = size
    rng = np.random.default_rng(seed)
    green = rng.normal(1000.0, 15.0, size=(h, w)).astype(np.float32)
    box = int(max(9, round(sigma_px * 6)))
    box += (box + 1) % 2  # force odd so the star sits centred
    half = box // 2
    yy, xx = np.indices((box, box))
    kernel = np.exp(-((xx - half) ** 2 + (yy - half) ** 2) / (2 * sigma_px * sigma_px))
    star_rng = np.random.default_rng(99)
    for _ in range(30):
        cx = int(star_rng.integers(half + 2, w - half - 2))
        cy = int(star_rng.integers(half + 2, h - half - 2))
        peak = float(star_rng.uniform(4000, 15000))
        green[cy - half : cy - half + box, cx - half : cx - half + box] += peak * kernel
    return np.stack([green, green, green], axis=-1)


def test_measures_a_plausible_fwhm_on_a_star_field():
    rgb = _stacked_green(sigma_px=3.0)
    fwhm = _compute_stack_fwhm(rgb, drizzle=False, drizzle_scale=1.0)
    assert fwhm is not None
    # Round stars of a few px across → a few px FWHM (measured on the half-res
    # green, so ~ 2.355 * (sigma / 2) ≈ 3.5 px here); just assert a sane finite band.
    assert 1.0 < fwhm < 10.0


def test_sharper_stars_give_a_smaller_fwhm():
    """Monotonic in the physical star width — the whole point of the number."""
    tight = _compute_stack_fwhm(_stacked_green(sigma_px=2.0), drizzle=False, drizzle_scale=1.0)
    wide = _compute_stack_fwhm(_stacked_green(sigma_px=4.0), drizzle=False, drizzle_scale=1.0)
    assert tight is not None and wide is not None
    assert tight < wide


def test_drizzle_scale_is_divided_out_to_native_pixels():
    """A drizzle super-res canvas has finer pixels, so the raw FWHM in pixels is
    larger; dividing by the scale reports it in native-frame pixels (comparable to
    a non-drizzle run of the same target)."""
    rgb = _stacked_green(sigma_px=3.0)
    native = _compute_stack_fwhm(rgb, drizzle=False, drizzle_scale=1.0)
    drizzled = _compute_stack_fwhm(rgb, drizzle=True, drizzle_scale=2.0)
    assert native is not None and drizzled is not None
    # Same pixels measured, so the drizzle=2 result is the native one halved
    # (approx — each is independently rounded to 3 dp).
    assert abs(drizzled - native / 2.0) < 0.01


def test_no_stars_returns_none_never_raises():
    flat = np.full((200, 300, 3), 1000.0, dtype=np.float32)
    assert _compute_stack_fwhm(flat, drizzle=False, drizzle_scale=1.0) is None


def test_all_nan_canvas_returns_none():
    nan_rgb = np.full((200, 300, 3), np.nan, dtype=np.float32)
    assert _compute_stack_fwhm(nan_rgb, drizzle=False, drizzle_scale=1.0) is None


def test_tiny_canvas_returns_none_never_raises():
    tiny = np.zeros((3, 3, 3), dtype=np.float32)
    assert _compute_stack_fwhm(tiny, drizzle=False, drizzle_scale=1.0) is None


def test_nan_gaps_are_filled_not_fatal():
    """NaN = no-coverage on a real mosaic canvas; the measurement fills gaps with
    the sky median rather than crashing the sky estimate."""
    rgb = _stacked_green(sigma_px=3.0)
    rgb[:20, :, :] = np.nan  # a no-coverage border strip
    fwhm = _compute_stack_fwhm(rgb, drizzle=False, drizzle_scale=1.0)
    assert fwhm is not None and 1.0 < fwhm < 10.0
