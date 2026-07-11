"""Photometric color calibration (gray-star path; Gaia path mocked)."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.post.color_cal import (
    ColorCalibrationOptions,
    _apply_scale,
    _solve_gray_star,
    calibrate_color,
)


def _starfield(h: int = 256, w: int = 384, n_stars: int = 80,
               r_gain: float = 1.0, b_gain: float = 1.0, seed: int = 0) -> np.ndarray:
    """Synthetic starfield where R and B are scaled by user-supplied factors."""
    rng = np.random.default_rng(seed)
    rgb = rng.normal(loc=100, scale=2, size=(h, w, 3)).astype(np.float32)
    for _ in range(n_stars):
        y = int(rng.integers(8, h - 8))
        x = int(rng.integers(8, w - 8))
        peak = float(rng.uniform(3000, 12000))
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                r2 = dy * dy + dx * dx
                # Stars are "neutral" before applying the camera gain bias.
                rgb[y + dy, x + dx, 0] += peak * r_gain * np.exp(-r2 / 2.0)
                rgb[y + dy, x + dx, 1] += peak * np.exp(-r2 / 2.0)
                rgb[y + dy, x + dx, 2] += peak * b_gain * np.exp(-r2 / 2.0)
    return rgb


def test_gray_star_solver_balances_neutral_field():
    """Gray-star calibration on a field of perfectly neutral stars: scales ≈ 1."""
    rgb = _starfield(r_gain=1.0, b_gain=1.0)
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    assert result.mode_used == "gray_star"
    sr, sg, sb = result.scale_rgb
    assert abs(sr - 1.0) < 0.1
    assert sg == 1.0
    assert abs(sb - 1.0) < 0.1


def test_gray_star_corrects_red_bias():
    """Camera has R gain = 0.6 (red is weak). Gray-star should boost R."""
    rgb = _starfield(r_gain=0.6, b_gain=1.0, seed=2)
    _, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    sr, sg, sb = result.scale_rgb
    # We expect R scale ≈ 1/0.6 ≈ 1.67 to compensate.
    assert sr > 1.3
    assert sg == 1.0
    # B is unaffected.
    assert abs(sb - 1.0) < 0.2


def test_disabled_is_passthrough():
    rgb = _starfield()
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(enabled=False))
    np.testing.assert_array_equal(out, rgb)
    assert result.mode_used == "none"


def test_falls_back_to_background_neutral_when_too_few_stars():
    """When gray-star can't run (no usable stars), the starless fallback still
    runs a background-neutral white balance. On an already-neutral flat field it
    resolves to a no-op (scales ≈ 1) — but reports it honestly, and the pixels
    are unchanged."""
    rgb = np.full((64, 64, 3), 100.0, dtype=np.float32)  # no stars, no cast
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    assert result.mode_used == "background_neutral"
    sr, sg, sb = result.scale_rgb
    assert sg == 1.0
    assert abs(sr - 1.0) < 1e-6 and abs(sb - 1.0) < 1e-6
    np.testing.assert_allclose(out, rgb, rtol=0, atol=1e-4)
    # The reason the star path was skipped is carried in the note for provenance.
    assert "stars found" in result.notes


def test_background_neutral_fallback_removes_a_starless_cast():
    """A sparse-star field with a real background colour cast (the sparse-star
    OSC case: a diffuse galaxy/nebula on a thin star field) is now
    background-neutralised instead of shipping the raw cast. Fails before the
    fallback existed (would be mode 'none', cast left in)."""
    rng = np.random.default_rng(11)
    # Neutral-grey sky at 100 ADU, then a green cast (G lifted, R/B suppressed)
    # and per-channel noise — no stars bright enough to detect.
    rgb = rng.normal(loc=100.0, scale=1.5, size=(200, 200, 3)).astype(np.float32)
    rgb[..., 0] *= 0.80   # red suppressed
    rgb[..., 1] *= 1.30   # green cast
    rgb[..., 2] *= 0.85   # blue suppressed
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=20,
    ))
    assert result.mode_used == "background_neutral"
    # After the balance the sky-background medians must be near-neutral.
    def _sky_median(img, c):
        luma = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        sky = luma <= np.median(luma)
        return float(np.median(img[..., c][sky]))
    mr, mg, mb = (_sky_median(out, c) for c in range(3))
    assert abs(mr - mg) / mg < 0.02
    assert abs(mb - mg) / mg < 0.02


def test_background_neutral_fallback_is_nan_aware_on_a_mosaic():
    """Uncovered (NaN) mosaic pixels must be ignored by the sky measurement and
    left NaN by the balance."""
    rng = np.random.default_rng(12)
    rgb = rng.normal(loc=100.0, scale=1.5, size=(120, 200, 3)).astype(np.float32)
    rgb[..., 0] *= 0.80
    rgb[..., 1] *= 1.30
    rgb[:, :110, :] = np.nan  # large uncovered region
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=20,
    ))
    assert result.mode_used == "background_neutral"
    assert np.isnan(out[0, 0, 0])          # gap stays NaN
    covered = np.isfinite(out[..., 0])
    assert np.isfinite(out[..., 0][covered]).all()


def test_background_neutral_gives_up_cleanly_on_a_tiny_canvas():
    """Below the sky-pixel floor the fallback declines rather than balancing off
    noise — the genuine 'none' path is preserved."""
    rgb = np.full((8, 8, 3), 100.0, dtype=np.float32)  # 64 px < _MIN_SKY_PIXELS
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    assert result.mode_used == "none"
    assert result.scale_rgb == (1.0, 1.0, 1.0)
    np.testing.assert_array_equal(out, rgb)


def test_apply_scale_handles_nan():
    rgb = np.full((4, 4, 3), 100.0, dtype=np.float32)
    rgb[0, 0, :] = np.nan
    out = _apply_scale(rgb, (2.0, 1.0, 0.5))
    assert np.isnan(out[0, 0, 0])
    assert out[1, 1, 0] == 200.0
    assert out[1, 1, 2] == 50.0


def test_solve_gaia_matches_when_catalog_larger_than_detections(monkeypatch):
    """Regression: the Gaia solver ANDed per-detection and per-catalog masks.

    When the Gaia catalog has more rows than we have detections (the normal
    case — a cone query returns far more stars than we detect), the old code
    ``matched & np.isfinite(color) & ...`` combined arrays of different
    lengths and raised, so Gaia calibration silently fell back to gray-star.
    Here the catalog is deliberately larger than the detection list.
    """
    from astropy.table import Table
    from astropy.wcs import WCS
    from seestack.post import color_cal
    from seestack.post.color_cal import _solve_gaia

    # A trivial TAN WCS: 1 px == 1 arcsec near the origin.
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crpix = [50.0, 50.0]
    wcs.wcs.crval = [180.0, 0.0]
    wcs.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]

    n_det = 20
    rng = np.random.default_rng(3)
    xs = rng.uniform(5, 95, n_det)
    ys = rng.uniform(5, 95, n_det)
    sources = Table({"xcentroid": xs, "ycentroid": ys})

    # Detections are neutral stars (R/G = B/G = 1). Give the catalog rows a
    # colour (BP-RP = 0) so the expected ratios are the intercepts a_r / a_b.
    fluxes = np.full((n_det, 3), 1000.0, dtype=np.float32)

    # Catalog = the true detection positions PLUS a pile of extra far-away
    # rows, so len(catalog) > len(detections). Nearest-match must still pick
    # the co-located rows.
    det_world = wcs.pixel_to_world(xs, ys)
    cat_ra = list(det_world.ra.deg) + list(180.0 + rng.uniform(0.2, 0.4, 50))
    cat_dec = list(det_world.dec.deg) + list(rng.uniform(0.2, 0.4, 50))
    n_cat = len(cat_ra)
    gaia_table = Table({
        "ra": np.asarray(cat_ra),
        "dec": np.asarray(cat_dec),
        "phot_bp_mean_mag": np.full(n_cat, 12.0),
        "phot_rp_mean_mag": np.full(n_cat, 12.0),   # BP-RP = 0
        "phot_g_mean_mag": np.full(n_cat, 12.0),
    })

    class _FakeJob:
        def get_results(self):
            return gaia_table

    class _FakeGaia:
        ROW_LIMIT = 0

        @staticmethod
        def cone_search_async(coordinate, radius):
            return _FakeJob()

    import sys
    import types
    fake_mod = types.ModuleType("astroquery.gaia")
    fake_mod.Gaia = _FakeGaia
    monkeypatch.setitem(sys.modules, "astroquery.gaia", fake_mod)

    rgb = np.zeros((100, 100, 3), dtype=np.float32)
    opts = ColorCalibrationOptions(enabled=True, mode="gaia", min_stars=5)
    scale, n, note = _solve_gaia(rgb, fluxes, sources, wcs, opts)

    # With neutral stars (measured R/G = B/G = 1) and BP-RP = 0, the fitted
    # scales should equal the model intercepts a_r=0.95, a_b=1.10.
    assert n >= 5
    assert abs(scale[0] - 0.95) < 0.05
    assert scale[1] == 1.0
    assert abs(scale[2] - 1.10) < 0.05


def test_solve_gaia_clamps_a_negative_channel_scale(monkeypatch):
    """Regression: an extremely-reddened field must not invert the blue channel.

    The linear-in-colour model predicts ``expected_bg = 1.10 - 0.45·(BP-RP)``,
    which goes negative once the median matched-star colour exceeds ~2.44. Before
    the clamp, ``scale_b = median(expected_bg / measured_bg)`` then went negative
    and, applied, would *flip* the blue channel. The solver now clamps every
    solved scale to a positive range.
    """
    from astropy.table import Table
    from astropy.wcs import WCS
    from seestack.post import color_cal  # noqa: F401
    from seestack.post.color_cal import _MIN_CAL_SCALE, _solve_gaia

    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crpix = [50.0, 50.0]
    wcs.wcs.crval = [180.0, 0.0]
    wcs.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]

    n_det = 20
    rng = np.random.default_rng(7)
    xs = rng.uniform(5, 95, n_det)
    ys = rng.uniform(5, 95, n_det)
    sources = Table({"xcentroid": xs, "ycentroid": ys})
    fluxes = np.full((n_det, 3), 1000.0, dtype=np.float32)

    det_world = wcs.pixel_to_world(xs, ys)
    cat_ra = list(det_world.ra.deg)
    cat_dec = list(det_world.dec.deg)
    n_cat = len(cat_ra)
    # BP-RP = 3.0 → expected_bg = 1.10 - 0.45·3.0 = -0.25 (negative).
    gaia_table = Table({
        "ra": np.asarray(cat_ra),
        "dec": np.asarray(cat_dec),
        "phot_bp_mean_mag": np.full(n_cat, 14.0),
        "phot_rp_mean_mag": np.full(n_cat, 11.0),   # BP-RP = 3.0
        "phot_g_mean_mag": np.full(n_cat, 12.0),
    })

    class _FakeJob:
        def get_results(self):
            return gaia_table

    class _FakeGaia:
        ROW_LIMIT = 0

        @staticmethod
        def cone_search_async(coordinate, radius):
            return _FakeJob()

    import sys
    import types
    fake_mod = types.ModuleType("astroquery.gaia")
    fake_mod.Gaia = _FakeGaia
    monkeypatch.setitem(sys.modules, "astroquery.gaia", fake_mod)

    rgb = np.zeros((100, 100, 3), dtype=np.float32)
    opts = ColorCalibrationOptions(enabled=True, mode="gaia", min_stars=5)
    scale, n, note = _solve_gaia(rgb, fluxes, sources, wcs, opts)

    # Without the clamp scale_b would be ≈ -0.25; it must instead be a positive
    # value at least the floor, so applying it can never invert the channel.
    assert scale[2] >= _MIN_CAL_SCALE
    assert scale[1] == 1.0
    assert "clamped" in note


def test_solve_gray_star_directly():
    fluxes = np.array([[100, 200, 150]] * 50, dtype=np.float32)
    scale, n, note = _solve_gray_star(fluxes)
    # R scale = G/R = 200/100 = 2.0
    assert abs(scale[0] - 2.0) < 0.01
    assert scale[1] == 1.0
    # B scale = G/B = 200/150 ≈ 1.33
    assert abs(scale[2] - 200/150) < 0.01
    assert n == 50


def test_solve_gray_star_clamps_an_out_of_range_channel_scale():
    """A detected-star population where one channel's median flux is far below G
    (a strongly colour-biased field / residual cast) previously made
    ``_solve_gray_star`` return an unbounded scale — e.g. ``med_g/med_r ≈ 50`` —
    which ``_apply_scale`` then multiplied straight into the channel, blowing it
    out. Unlike the Gaia path, the gray-star solver applied its raw ratios with
    no clamp. It now clamps to the same ``[_MIN_CAL_SCALE, _MAX_CAL_SCALE]`` range
    so calibration can only rescale a channel, never extinguish or over-amplify
    it. Fails before / passes after the fix."""
    from seestack.post.color_cal import _MAX_CAL_SCALE, _MIN_CAL_SCALE

    # med_r ≈ 1, med_g ≈ med_b ≈ 55 → raw scale_r ≈ 55 (well above the 20 cap).
    fluxes = np.empty((40, 3), dtype=np.float32)
    fluxes[:, 0] = 1.0
    fluxes[:, 1] = 55.0
    fluxes[:, 2] = 55.0
    scale, n, note = _solve_gray_star(fluxes)
    assert _MIN_CAL_SCALE <= scale[0] <= _MAX_CAL_SCALE
    assert scale[0] == _MAX_CAL_SCALE  # raw ≈55 clamped down to the 20 ceiling
    assert scale[1] == 1.0
    assert _MIN_CAL_SCALE <= scale[2] <= _MAX_CAL_SCALE
    assert "clamped" in note

    # And a normal near-neutral field is untouched (the clamp is a no-op there).
    neutral = np.array([[100, 105, 98]] * 40, dtype=np.float32)
    nscale, _, nnote = _solve_gray_star(neutral)
    assert abs(nscale[0] - 105 / 100) < 0.01
    assert "clamped" not in nnote
