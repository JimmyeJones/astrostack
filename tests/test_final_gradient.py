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
    """A gradient sky peppered with thousands of *resolved* stars — like the
    built-in *cluster* preset's target. The object mask (detect + 16 px dilation)
    swells to cover >80% of every default box, which makes ``Background2D`` raise
    at ``exclude_percentile=80``.

    The stars are small Gaussians rather than single hot pixels: a real star is
    several pixels wide at Seestar seeing, and the mask builder deliberately
    ignores single-pixel (noise-sized) detections, so single pixels would make
    this a field of *noise*, not of stars."""
    rng = np.random.default_rng(11)
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad = (xx / w) * 200 + (yy / h) * 100
    rgb = np.stack([grad + 10, grad + 12, grad + 8], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=2.0, size=rgb.shape).astype(np.float32)
    ys = rng.integers(2, h - 2, n_stars)
    xs = rng.integers(2, w - 2, n_stars)
    amps = rng.uniform(150.0, 400.0, size=n_stars).astype(np.float32)
    # A 5x5 unit-peak Gaussian stamp (sigma ~1.06 px => ~2.5 px FWHM).
    dy, dx = np.mgrid[-2:3, -2:3].astype(np.float32)
    stamp = np.exp(-(dy * dy + dx * dx) / 2.25)
    for y, x, amp in zip(ys, xs, amps, strict=True):
        rgb[y - 2:y + 3, x - 2:x + 3, :] += (amp * stamp)[:, :, None]
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


def _lp_gradient_stack(
    h: int = 300, w: int = 480, *, gradient: bool = True, nebula: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """A realistic *background-subtracted* OSC stack: what the editor actually sees.

    Per-frame flatten leaves a residual sky tilt whose amplitude scales with each
    channel's own sky level (light pollution is brightest where the sky is
    brightest), so R/G/B are tilted by different amounts — measured on a 12-sub
    S30 scene as +42/+71/+34 ADU on σ≈20 ADU stack noise. That per-channel
    *scaling* is what a single luminance model plus a per-channel constant cannot
    flatten, and what the per-channel STF stretch then turns into a spatial colour
    split. Includes a faint red nebula so a fix can be checked for eating it.

    Returns ``(rgb, nebula_profile)``.
    """
    rng = np.random.default_rng(17)
    yy, xx = np.indices((h, w), dtype=np.float32)
    ramp = (xx / (w - 1)) * 0.75 + (yy / (h - 1)) * 0.25
    tilts = (42.0, 71.0, 34.0) if gradient else (0.0, 0.0, 0.0)
    rgb = np.stack([ramp * t for t in tilts], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=20.0, size=rgb.shape).astype(np.float32)

    # A handful of resolved white stars (the mask must still find these).
    dy, dx = np.mgrid[-3:4, -3:4].astype(np.float32)
    stamp = np.exp(-(dy * dy + dx * dx) / 2.25)
    for y, x, amp in zip(rng.integers(4, h - 4, 40), rng.integers(4, w - 4, 40),
                         rng.uniform(300.0, 2000.0, 40), strict=True):
        rgb[y - 3:y + 4, x - 3:x + 4, :] += (amp * stamp).astype(np.float32)[:, :, None]

    prof = np.exp(-(((yy - h * 0.42) / (h * 0.16)) ** 2
                    + ((xx - w * 0.58) / (w * 0.13)) ** 2)).astype(np.float32)
    if nebula:
        for c, amp in enumerate((55.0, 18.0, 32.0)):   # faint, and strongly red
            rgb[..., c] += prof * amp
    return rgb, prof


def _sky_band_medians(rgb: np.ndarray, bands: int = 8) -> np.ndarray:
    """Per-channel sky median in each vertical band — ``(bands, 3)``."""
    h, w = rgb.shape[:2]
    rows = slice(int(h * 0.80), int(h * 0.95))       # below the nebula
    edges = np.linspace(0, w, bands + 1).astype(int)
    return np.array([[float(np.nanmedian(rgb[rows, edges[i]:edges[i + 1], c]))
                      for c in range(3)] for i in range(bands)])


def _colour_spread(rgb: np.ndarray) -> float:
    """Worst cross-channel disagreement of the sky across the frame, in ADU.

    This *is* the "purple down one side, green down the other" defect: a neutral
    sky has all three channels at the same level everywhere, so any band where
    they diverge becomes a colour wash once the per-channel STF stretches them.
    """
    bands = _sky_band_medians(rgb)
    return float(np.max(bands.max(axis=1) - bands.min(axis=1)))


def _core_chroma(rgb: np.ndarray, prof: np.ndarray) -> float:
    core = prof > 0.8
    levels = np.array([float(np.nanmedian(rgb[..., c][core])) for c in range(3)])
    return float((levels.max() - levels.min()) / max(levels.max(), 1e-6))


def test_object_mask_is_not_starved_by_a_sky_gradient():
    """The detection threshold must be *local*.

    Against a whole-frame median, a frame that still carries an ordinary
    light-pollution gradient reads its entire bright half as "object" — measured
    on a realistic S30 scene as 5 % of the dim fifth masked vs 66 % of the bright
    fifth. That starves ``Background2D`` of sky exactly where the gradient is, so
    the gradient pass can only remove a tenth of the tilt it exists to remove.
    """
    rgb, _ = _lp_gradient_stack(nebula=False)
    mask = _build_object_mask(rgb, FinalGradientOptions(enabled=True))
    w = rgb.shape[1]
    dim = float(mask[:, : w // 8].mean())
    bright = float(mask[:, -w // 8:].mean())
    # The brightest eighth of the sky is sky, not object.
    assert bright < 0.35, f"bright edge {bright:.0%} masked"
    assert bright < dim + 0.25, f"mask skewed to the bright side: {dim:.0%} vs {bright:.0%}"


def test_object_mask_ignores_noise_sized_detections():
    """A σ-threshold flags ~0.6 % of pixels *anywhere*; dilating those single-pixel
    spikes by the default 16 px swells the mask over most of the frame, starving
    the fit on a frame that has no objects to speak of."""
    rgb, _ = _lp_gradient_stack(gradient=False, nebula=False)
    mask = _build_object_mask(rgb, FinalGradientOptions(enabled=True))
    assert mask.mean() < 0.35, f"{mask.mean():.0%} of a near-empty frame masked"


def test_luminance_mode_flattens_each_channels_own_gradient():
    """The ⭐⭐ one-click-colour bug: light pollution tilts each channel by a
    different amount, so shared-luminance removal leaves a spatial *colour* split
    that the per-channel STF stretch then makes obvious (measured end-to-end:
    −15 % green down one side, +11 % up the other). The default must flatten each
    channel's own gradient — and must not eat the faint nebula doing it."""
    rgb, prof = _lp_gradient_stack()
    before = _colour_spread(rgb)
    assert before > 25.0, "scene should start with a real colour split"

    out = remove_final_gradient(
        rgb, FinalGradientOptions(enabled=True, mode="luminance", box_size=256))
    after = _colour_spread(out)
    assert after < 0.25 * before, f"colour split survived: {before:.1f} → {after:.1f} ADU"
    # The faint nebula keeps its colour — the measured hazard of the naive fixes.
    assert _core_chroma(out, prof) > 0.8 * _core_chroma(rgb, prof)
    assert np.isfinite(out).all()


def test_match_channels_off_is_brightness_only():
    """The historical behaviour stays reachable: one luminance model plus a
    per-channel *constant* flattens brightness but leaves the colour split."""
    rgb, _ = _lp_gradient_stack()
    opts = dict(enabled=True, mode="luminance", box_size=256)
    off = remove_final_gradient(rgb, FinalGradientOptions(match_channels=False, **opts))
    on = remove_final_gradient(rgb, FinalGradientOptions(match_channels=True, **opts))
    assert _colour_spread(off) > 3.0 * _colour_spread(on)


def test_match_channels_does_not_invent_a_cast_on_a_flat_frame():
    """On a stack with no gradient left to remove, the per-channel pass must find
    nothing — it must not fit its own noise into a new colour cast. (Fitting raw
    pixels with outlier clipping does exactly that, because the clipping bites
    harder wherever the object mask is denser; the fit uses per-tile medians,
    which are unbiased however much of a tile the mask removed.)"""
    rgb, _ = _lp_gradient_stack(gradient=False)
    opts = dict(enabled=True, mode="luminance", box_size=256)
    plain = remove_final_gradient(rgb, FinalGradientOptions(match_channels=False, **opts))
    matched = remove_final_gradient(rgb, FinalGradientOptions(match_channels=True, **opts))
    assert _colour_spread(matched) < _colour_spread(plain) + 1.5


def test_object_mask_covers_bright_region():
    rgb = _stack_with_gradient_and_galaxy()
    mask = _build_object_mask(rgb, FinalGradientOptions(detect_sigma=2.5, dilate_px=5))
    h, w = rgb.shape[:2]
    cy, cx = h // 2, w // 2
    # Galaxy centre should be in the mask.
    assert mask[cy, cx]
    # Left-edge sky should not be in the mask.
    assert not mask[h // 2, 5]
