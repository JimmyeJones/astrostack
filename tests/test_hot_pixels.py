"""Hot/cold pixel suppression."""

import numpy as np
import pytest

pytest.importorskip("scipy")

from seestack.bg.hot_pixels import suppress_hot_cold_pixels


def test_hot_pixel_replaced_with_neighbourhood():
    rng = np.random.default_rng(0)
    rgb = rng.normal(loc=1000, scale=10, size=(64, 64, 3)).astype(np.float32)
    # Plant a hot pixel.
    rgb[32, 32, 1] = 60000.0
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    # The hot pixel should be brought close to its neighbours.
    assert out[32, 32, 1] < 1500
    # Untouched neighbours.
    np.testing.assert_allclose(out[10, 10, 1], rgb[10, 10, 1], atol=1.0)


def test_cold_pixel_replaced():
    rng = np.random.default_rng(1)
    rgb = rng.normal(loc=1000, scale=10, size=(64, 64, 3)).astype(np.float32)
    rgb[40, 20, 0] = -50000.0
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    assert out[40, 20, 0] > 500


def test_constant_image_passthrough():
    rgb = np.full((32, 32, 3), 1000.0, dtype=np.float32)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    np.testing.assert_array_equal(out, rgb)


def test_suppression_still_works_with_nan_coverage_gap():
    """Regression: a NaN coverage gap (mosaic / partial overlap) must not disable
    the whole suppression. Previously the noise floor was a non-NaN-aware median
    over the residual, so any NaN made the threshold NaN and the pass no-op'd —
    every hot/cold pixel survived into the stack."""
    rng = np.random.default_rng(3)
    rgb = rng.normal(loc=100.0, scale=3.0, size=(64, 64, 3)).astype(np.float32)
    rgb[20, 30, :] = 6000.0  # hot pixels away from the gap
    rgb[40, 50, :] = 6000.0
    rgb[:, :10, :] = np.nan  # an uncovered region (NaN = no coverage)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    # Hot pixels are repaired to the local sky despite the gap (were ~6000 before).
    assert out[20, 30, 1] < 500
    assert out[40, 50, 1] < 500
    # The coverage gap is preserved as NaN (never turned into zeros/finite values).
    assert np.isnan(out[5, 5, 0])
    assert np.isfinite(out[:, 10:, :]).all()


def test_all_nan_channel_is_left_untouched():
    """A fully-uncovered channel has no valid residual to estimate noise from —
    it must be skipped cleanly, not crash or emit spurious values."""
    rgb = np.full((16, 16, 3), np.nan, dtype=np.float32)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    assert np.isnan(out).all()


def _gaussian_star_field(fwhm_px, *, seed, size=200, sky=1000.0,
                         read_noise=8.0, nstars=30):
    """A synthetic sky of Gaussian stars with Poisson + read noise, plus the
    per-star ground-truth integrated flux above sky. Mirrors real Seestar OSC
    data: undersampled 1.5–2.5 px-FWHM cores on a noisy background."""
    rng = np.random.default_rng(seed)
    gsig = fwhm_px / 2.3548
    img = np.full((size, size), sky, dtype=np.float64)
    ys = rng.uniform(12, size - 12, nstars)
    xs = rng.uniform(12, size - 12, nstars)
    peaks = rng.uniform(3000, 30000, nstars)
    yy, xx = np.mgrid[0:size, 0:size]
    flux_true = np.zeros(nstars)
    for i in range(nstars):
        g = peaks[i] * np.exp(-((yy - ys[i]) ** 2 + (xx - xs[i]) ** 2)
                              / (2 * gsig ** 2))
        img += g
        flux_true[i] = g.sum()
    noisy = (rng.poisson(np.clip(img, 0, None)).astype(np.float64)
             + rng.normal(0, read_noise, img.shape))
    return noisy.astype(np.float32), sky, ys, xs, flux_true, gsig


@pytest.mark.parametrize("fwhm", [3.0, 2.0, 1.5])
def test_undersampled_star_cores_keep_their_flux(fwhm):
    """Regression: the suppression must not flatten sharp *real* star cores.

    Before the star-safety gate, a naive "far from the 3×3 median" test clipped
    every undersampled star peak against a sky-noise floor, dropping integrated
    star flux by ~21% (FWHM 3.0) up to ~71% (FWHM 1.5) — dimming and
    colour-shifting every star in the stack. The gate protects a star peak
    (whose neighbourhood is elevated) while still repairing isolated defects.
    """
    noisy, sky, ys, xs, flux_true, gsig = _gaussian_star_field(fwhm, seed=42)
    rgb = np.stack([noisy, noisy, noisy], axis=-1)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)[..., 0]
    removed = noisy.astype(np.float64) - out.astype(np.float64)  # >0 where clipped
    rad = int(np.ceil(4 * gsig)) + 1
    frac_removed = []
    for i, (y, x) in enumerate(zip(ys, xs, strict=False)):
        y0, y1 = int(y) - rad, int(y) + rad + 1
        x0, x1 = int(x) - rad, int(x) + rad + 1
        frac_removed.append(removed[y0:y1, x0:x1].sum() / flux_true[i])
    # Keep ≥98% of every star's integrated flux (was down to ~29% pre-fix).
    assert np.mean(frac_removed) < 0.02
    assert np.max(frac_removed) < 0.05


def test_star_field_still_removes_an_injected_hot_pixel():
    """The star-safety gate must not blind the pass to real defects: an isolated
    hot spike planted between the stars is still repaired to the local sky."""
    noisy, sky, ys, xs, _flux, _gsig = _gaussian_star_field(2.0, seed=7)
    # Plant a hot pixel on empty sky (well away from any star centre).
    hy, hx = 5, 5
    assert noisy[hy, hx] < sky + 200  # genuinely on background
    noisy[hy, hx] = 55000.0
    rgb = np.stack([noisy, noisy, noisy], axis=-1)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)[..., 0]
    assert out[hy, hx] < sky + 500  # repaired to ~sky


def test_bright_outlier_gate_preserves_colour_balance():
    """The old pass clipped R/G/B star cores by *different* amounts (a per-channel
    bias → colour cast). With the gate, an achromatic star must stay achromatic:
    all three channels keep essentially all of their flux."""
    noisy, sky, ys, xs, flux_true, gsig = _gaussian_star_field(1.8, seed=11)
    rgb = np.stack([noisy, noisy, noisy], axis=-1)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    rad = int(np.ceil(4 * gsig)) + 1
    per_channel = []
    for c in range(3):
        removed = noisy.astype(np.float64) - out[..., c].astype(np.float64)
        tot = sum(
            removed[int(y) - rad:int(y) + rad + 1,
                    int(x) - rad:int(x) + rad + 1].sum()
            for y, x in zip(ys, xs, strict=False)
        )
        per_channel.append(tot / flux_true.sum())
    # No channel loses meaningful flux, and the channels agree (no colour shift).
    assert max(per_channel) < 0.02
    assert max(per_channel) - min(per_channel) < 0.01


def _debayered_star_field(fwhm_px, *, seed, hot_sites=(), size=140, sky=1000.0):
    """A raw RGGB Bayer mosaic of undersampled Gaussian stars (+ optional single
    hot CFA sites), run through the *real* ``bilinear_debayer`` — i.e. the exact
    production order raw→debayer→suppress in which the star-core clipping bug
    bit. Returns (debayered_rgb, star_centres, per_star_flux, hot_sites)."""
    from seestack.io.fits_loader import bilinear_debayer

    rng = np.random.default_rng(seed)
    gsig = fwhm_px / 2.3548
    yy, xx = np.mgrid[0:size, 0:size]
    mosaic = np.full((size, size), sky, dtype=np.float64)
    centres, fluxes = [], []
    for i in range(8):
        cy, cx = 20 + i * 13, 40
        g = 20000.0 * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * gsig ** 2))
        mosaic += g
        centres.append((cy, cx))
        fluxes.append(g.sum())
    for (hy, hx) in hot_sites:
        mosaic[hy, hx] = 60000.0
    mosaic = (rng.poisson(np.clip(mosaic, 0, None)).astype(np.float64)
              + rng.normal(0, 8.0, mosaic.shape))
    rgb = bilinear_debayer(mosaic.astype(np.float32), pattern="RGGB")
    return rgb, centres, np.asarray(fluxes), gsig


@pytest.mark.parametrize("fwhm", [3.0, 2.0, 1.5])
def test_debayered_star_cores_keep_their_flux(fwhm):
    """Regression for the *real pipeline* order (raw→bilinear_debayer→suppress).

    After a bilinear debayer an undersampled star aliases into a single-channel
    checkerboard whose 3×3 median collapses to ~sky — so even an "isolated vs
    its own neighbourhood" test clips it. Integrated star luminance dropped
    ~21% (FWHM 3.0) up to ~71% (FWHM 1.5) before the cross-channel / all-channel
    star guard. Assert ≥95% of every star's luminance survives."""
    rgb, centres, fluxes, gsig = _debayered_star_field(fwhm, seed=3)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    removed = rgb.sum(2).astype(np.float64) - out.sum(2).astype(np.float64)
    rad = int(np.ceil(4 * gsig)) + 1
    frac = []
    for (cy, cx), tf in zip(centres, fluxes, strict=False):
        # A white star debayers to ~equal energy in all 3 channels, so its
        # luminance ≈ 3× the mono illumination; normalise against that.
        frac.append(removed[cy - rad:cy + rad + 1, cx - rad:cx + rad + 1].sum()
                    / (3 * tf))
    assert np.mean(frac) < 0.02
    assert np.max(frac) < 0.05


def test_debayered_single_cfa_hot_pixel_is_suppressed():
    """The star guard must not blind the pass to real CFA defects: an isolated
    single hot sensor site, spread into a 3×3 halo by the debayer, is still
    knocked down well below its debayered peak (as on the drizzle path)."""
    rad_hot = [(20, 100), (46, 101), (72, 100), (98, 101)]  # varied Bayer phases
    rgb, _c, _f, _g = _debayered_star_field(2.0, seed=4, hot_sites=rad_hot)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    for (hy, hx) in rad_hot:
        pk = int(np.argmax(rgb[hy, hx]))  # the channel the CFA defect landed in
        assert out[hy, hx, pk] < 0.6 * rgb[hy, hx, pk]


def test_many_hot_pixels():
    """Field of dozens of hot pixels should all get suppressed."""
    rng = np.random.default_rng(2)
    rgb = rng.normal(loc=1000, scale=10, size=(128, 128, 3)).astype(np.float32)
    # Plant 30 random hot pixels.
    ys = rng.integers(2, 126, size=30)
    xs = rng.integers(2, 126, size=30)
    rgb[ys, xs, 1] += 20000
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    # After suppression, none of the planted pixels should still be > 10000 ADU
    # above the local sky.
    for y, x in zip(ys, xs):
        assert out[y, x, 1] - 1000 < 5000
