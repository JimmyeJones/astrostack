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


def test_small_image_does_not_raise_and_still_flattens():
    """A sub-box image (< ~768 px) with the *default* 256 px box must not fail:
    a box wider than the frame leaves too few unmasked boxes to survive
    ``exclude_percentile`` and photutils raises. Since the Auto recipe includes
    ``final_gradient``, that would break the whole Auto preview/export on a small
    proxy. The box is now clamped to tile the image (mirroring
    ``BackgroundOptions.for_image_size``), so the op degrades gracefully."""
    rng = np.random.default_rng(7)
    h, w = 200, 220
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad = (xx / w) * 200 + (yy / h) * 100
    rgb = np.stack([grad + 10, grad + 12, grad + 8], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=2.0, size=rgb.shape).astype(np.float32)

    for mode in ("luminance", "per_channel"):
        errors: list[str] = []
        out = remove_final_gradient(
            rgb, FinalGradientOptions(enabled=True, mode=mode, box_size=256),
            errors=errors,
        )
        # No surfaced error (the editor turns a non-empty list into a hard
        # RuntimeError), no NaN introduced, and the gradient is actually reduced.
        assert errors == [], f"{mode}: {errors}"
        assert out.shape == rgb.shape
        assert np.isfinite(out).all()
        assert np.median(np.abs(out[..., 1])) < np.median(np.abs(rgb[..., 1]))


def test_full_size_box_is_unchanged_by_the_clamp():
    """On a real Seestar-size stack the 256 px box already tiles the frame, so
    the clamp is a no-op and the result is identical to the pre-clamp behaviour
    — the small-image guard must not perturb full-res exports (parity)."""
    rgb = _stack_with_gradient_and_galaxy(h=1200, w=1600)
    out = remove_final_gradient(
        rgb, FinalGradientOptions(enabled=True, mode="per_channel", box_size=256),
    )
    # Gradient flattened as usual (box 256 tiles a 1200×1600 frame ≥ 4×), galaxy
    # intact — same acceptance as the standard-size tests.
    for c in range(3):
        assert abs(np.median(out[..., c])) < 25
    cy, cx = 600, 800
    assert out[cy - 1:cy + 2, cx - 1:cx + 2, :].mean() > 100


def _dense_star_field(h: int = 900, w: int = 900, n_stars: int = 6000) -> np.ndarray:
    """A gradient sky peppered with thousands of point sources — like the
    built-in *cluster* preset's target. The object mask (sigma-clip + 16 px
    dilation) swells to cover >80% of every default box, which makes
    ``Background2D`` raise at ``exclude_percentile=80``."""
    rng = np.random.default_rng(11)
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad = (xx / w) * 200 + (yy / h) * 100
    rgb = np.stack([grad + 10, grad + 12, grad + 8], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=2.0, size=rgb.shape).astype(np.float32)
    ys = rng.integers(0, h, n_stars)
    xs = rng.integers(0, w, n_stars)
    rgb[ys, xs, :] += rng.uniform(150.0, 400.0, size=(n_stars, 1)).astype(np.float32)
    return rgb


def test_dense_field_degrades_instead_of_giving_up():
    """A dense star field masks >80% of every box, so the strict
    ``exclude_percentile=80`` fit raises and the op used to vanish entirely
    (silently losing gradient removal on clusters / very-flat fields). It must
    now degrade to a coarse fit — no surfaced error, gradient reduced."""
    rgb = _dense_star_field()

    # Sanity: the strict-only path (what shipped before — a single
    # ``exclude_percentile=80`` fit) really does fail here, so this is a genuine
    # regression test (fails before / passes after).
    from astropy.stats import SigmaClip
    from photutils.background import Background2D, MMMBackground

    from seestack.bg import final_gradient as fg

    mask = fg._build_object_mask(rgb, FinalGradientOptions(enabled=True))
    finite = np.isfinite(rgb[..., 1])
    clean = np.where(finite, rgb[..., 1], 0.0).astype(np.float32, copy=False)
    h, w = clean.shape[:2]
    box = max(1, min(min(256, max(8, min(h // 4, w // 4))), h, w))
    with pytest.raises(Exception):
        Background2D(
            clean, box_size=(box, box), filter_size=(3, 3),
            sigma_clip=SigmaClip(sigma=3.0), bkg_estimator=MMMBackground(),
            mask=mask | ~finite, exclude_percentile=80.0,
        )

    for mode in ("per_channel", "luminance"):
        errors: list[str] = []
        out = remove_final_gradient(
            rgb, FinalGradientOptions(enabled=True, mode=mode), errors=errors,
        )
        assert errors == [], f"{mode}: {errors}"
        assert out.shape == rgb.shape
        assert np.isfinite(out).all()
        # The op actually did something (didn't return the input unchanged) and
        # the large-scale left→right tilt is reduced rather than preserved.
        assert not np.array_equal(out, rgb), f"{mode}: op was a silent no-op"
        left = np.median(out[:, :100, 1])
        right = np.median(out[:, -100:, 1])
        before = np.median(rgb[:, -100:, 1]) - np.median(rgb[:, :100, 1])
        assert abs(right - left) < abs(before), f"{mode}: tilt not reduced"


def test_ladder_first_rung_matches_strict_fit():
    """A frame whose fit succeeds at the tuned ``exclude_percentile=80`` must be
    byte-for-byte unchanged by the degradation ladder — the retry only ever
    kicks in *after* the strict fit fails, so normal exports stay identical."""
    from seestack.bg import final_gradient as fg

    rgb = _stack_with_gradient_and_galaxy(h=1200, w=1600)
    mask = fg._build_object_mask(rgb, FinalGradientOptions(enabled=True))
    ladder = fg._fit_background_2d(rgb[..., 1], mask, box_size=256)

    # Reproduce exactly the strict single-attempt fit the old code did.
    from astropy.stats import SigmaClip
    from photutils.background import Background2D, MMMBackground

    finite = np.isfinite(rgb[..., 1])
    clean = np.where(finite, rgb[..., 1], 0.0).astype(np.float32, copy=False)
    h, w = clean.shape[:2]
    box = min(256, max(8, min(h // 4, w // 4)))
    box = max(1, min(box, h, w))
    strict = Background2D(
        clean, box_size=(box, box), filter_size=(3, 3),
        sigma_clip=SigmaClip(sigma=3.0), bkg_estimator=MMMBackground(),
        mask=mask | ~finite, exclude_percentile=80.0,
    ).background.astype(np.float32, copy=False)
    np.testing.assert_array_equal(ladder, strict)


def test_object_mask_covers_bright_region():
    rgb = _stack_with_gradient_and_galaxy()
    mask = _build_object_mask(rgb, FinalGradientOptions(detect_sigma=2.5, dilate_px=5))
    h, w = rgb.shape[:2]
    cy, cx = h // 2, w // 2
    # Galaxy centre should be in the mask.
    assert mask[cy, cx]
    # Left-edge sky should not be in the mask.
    assert not mask[h // 2, 5]
