"""
No-coverage NaNs must not make the engine shout in the user's log.

``NaN = no coverage`` is a convention every background/QC pass lives with, and
``astropy.stats.sigma_clipped_stats`` warns once per call when it clips them
("Input data contains invalid values (NaNs or infs), which were automatically
clipped") — astropy routes that into the application log, where a real stack
emits dozens of them and buries anything genuine on the Logs page a beginner
reads.

Two things are pinned here, and the second is the one that matters: the passes
are *silent* on NaN-bearing input, and the silence did not change a single
number — masking the non-finite pixels returns bit-identical statistics to
letting astropy clip them.
"""

import warnings

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.utils.exceptions import AstropyUserWarning  # noqa: E402

from seestack.core.skystats import sigma_clipped_stats_finite  # noqa: E402


def _legacy_stats(data, **kwargs):
    """What the call sites used to do: hand astropy the NaNs and let it warn."""
    from astropy.stats import sigma_clipped_stats

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AstropyUserWarning)
        return sigma_clipped_stats(data, **kwargs)


def _scene(h=240, w=240, *, nan_corner=True, seed=0):
    """A sky-shaped RGB frame with stars and (by default) an uncovered corner."""
    rng = np.random.default_rng(seed)
    img = rng.normal(0.12, 0.004, (h, w, 3)).astype(np.float32)
    for _ in range(80):
        y = int(rng.integers(5, h - 5))
        x = int(rng.integers(5, w - 5))
        img[y - 1:y + 2, x - 1:x + 2] += 0.3
    if nan_corner:
        img[:h // 5, :w // 5] = np.nan
    return img


def _astropy_warnings(fn):
    """Run ``fn`` and return the ``AstropyUserWarning``s it emitted."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn()
    return [w for w in caught if issubclass(w.category, AstropyUserWarning)]


# --- the helper itself -------------------------------------------------------

def test_masking_the_nans_returns_bit_identical_statistics():
    """The silence is free: same pixels measured, same three numbers out."""
    rng = np.random.default_rng(7)
    data = rng.normal(0.1, 0.01, (120, 150)).astype(np.float32)
    data[:30, :40] = np.nan
    data[90, 100] = np.inf
    data[91, 100] = -np.inf

    quiet = sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5)
    legacy = _legacy_stats(data, sigma=3.0, maxiters=5)

    assert [np.float32(v) for v in quiet] == [np.float32(v) for v in legacy]


def test_no_astropy_warning_on_nan_bearing_input():
    data = np.random.default_rng(3).normal(0.1, 0.01, (80, 80)).astype(np.float32)
    data[:20, :20] = np.nan

    from astropy.stats import sigma_clipped_stats

    # The pre-fix call is the control: it *does* warn on this exact array, so a
    # future astropy that stops warning can't quietly turn this test green.
    assert _astropy_warnings(
        lambda: sigma_clipped_stats(data, sigma=3.0, maxiters=5))

    assert _astropy_warnings(
        lambda: sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5)) == []


def test_all_finite_input_takes_the_plain_path_unchanged():
    data = np.random.default_rng(4).normal(0.1, 0.01, (60, 60)).astype(np.float32)

    quiet = sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5)
    legacy = _legacy_stats(data, sigma=3.0, maxiters=5)

    assert [np.float32(v) for v in quiet] == [np.float32(v) for v in legacy]
    assert _astropy_warnings(
        lambda: sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5)) == []


def test_dtype_survives_so_downstream_thresholds_are_unchanged():
    """A float32 sky must not come back as float64: callers build thresholds
    (``med + k*std``) out of these, and the dtype decides the rounding."""
    data = np.random.default_rng(5).normal(0.1, 0.01, (40, 40)).astype(np.float32)
    data[:5, :5] = np.nan

    for value in sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5):
        assert isinstance(value, np.float32)


def test_an_array_with_nothing_finite_reads_as_nan_not_masked():
    """``np.ma.masked`` would trade one warning for another: ``float()`` of it
    warns, and every caller guards on ``np.isfinite`` then converts."""
    data = np.full((30, 30), np.nan, dtype=np.float32)

    mean, med, std = sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5)

    for value in (mean, med, std):
        assert value is not np.ma.masked
        assert not np.isfinite(value)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert np.isnan(float(med))          # would raise if it were masked


def test_integer_input_is_untouched():
    """An int array has no NaN to mask — it must not crash on the dtype path."""
    data = np.arange(400, dtype=np.int32).reshape(20, 20)

    quiet = sigma_clipped_stats_finite(data, sigma=3.0, maxiters=5)
    legacy = _legacy_stats(data, sigma=3.0, maxiters=5)

    assert [float(v) for v in quiet] == [float(v) for v in legacy]


def test_one_dimensional_sample_works():
    """``coverage_leveling`` measures a flat, strided sample, not a 2-D frame."""
    values = np.random.default_rng(6).normal(0.1, 0.01, 5000).astype(np.float32)
    values[::7] = np.nan

    quiet = sigma_clipped_stats_finite(values, sigma=3.0, maxiters=5)
    legacy = _legacy_stats(values, sigma=3.0, maxiters=5)

    assert [np.float32(v) for v in quiet] == [np.float32(v) for v in legacy]
    assert _astropy_warnings(
        lambda: sigma_clipped_stats_finite(values, sigma=3.0, maxiters=5)) == []


# --- the call sites, on the shapes the owner's data actually has -------------

def test_qc_sky_estimate_is_quiet_on_an_uncovered_frame():
    from seestack.qc.metrics import estimate_sky

    frame = _scene()[..., 1]

    assert _astropy_warnings(lambda: estimate_sky(frame)) == []
    median, std = estimate_sky(frame)
    assert 0.10 < median < 0.14 and std > 0


def test_final_gradient_removal_is_quiet_on_a_mosaic_shaped_canvas():
    from seestack.bg.final_gradient import FinalGradientOptions, remove_final_gradient

    rgb = _scene()
    options = FinalGradientOptions(enabled=True)

    assert _astropy_warnings(lambda: remove_final_gradient(rgb.copy(), options)) == []
    out = remove_final_gradient(rgb.copy(), options)
    assert np.isnan(out[:10, :10]).all()     # the uncovered corner stays uncovered
    assert np.isfinite(out[-10:, -10:]).all()


def test_per_frame_flatten_is_quiet_on_a_frame_with_uncovered_pixels():
    from seestack.bg.per_frame import BackgroundOptions, subtract_background

    rgb = _scene()

    assert _astropy_warnings(
        lambda: subtract_background(rgb.copy(), BackgroundOptions())) == []


def test_coverage_levelings_own_helpers_are_quiet_if_a_nan_ever_reaches_them():
    """Defensive, unlike the three above: today's callers hand these helpers a
    finite selection, so nothing warns on the live path. They are converted so a
    future caller that *does* pass an uncovered sample can't reopen the noise —
    and both keep answering exactly what they answered before."""
    from seestack.bg.coverage_leveling import _robust_stats, _sky_mode

    sample = np.random.default_rng(8).normal(0.1, 0.01, 4000).astype(np.float32)
    sample[::11] = np.nan

    assert _astropy_warnings(lambda: _robust_stats(sample)) == []
    assert _astropy_warnings(lambda: _sky_mode(sample)) == []

    legacy_mean, legacy_med, _ = _legacy_stats(sample, sigma=3.0, maxiters=5)
    med, _ = _robust_stats(sample)
    assert med == pytest.approx(float(legacy_med), abs=1e-9)
    assert _sky_mode(sample) == pytest.approx(
        float(2.5 * legacy_med - 1.5 * legacy_mean), abs=1e-6)


def test_coverage_leveling_is_quiet_on_a_mosaic_canvas():
    from seestack.bg.coverage_leveling import level_by_coverage

    rgb = _scene(h=240, w=300)
    coverage = np.full(rgb.shape[:2], 4, dtype=np.int32)
    coverage[:48, :60] = 0                   # the uncovered corner
    coverage[:, :150] = 2                    # a second, thinner panel
    coverage[:48, :60] = 0

    assert _astropy_warnings(lambda: level_by_coverage(rgb.copy(), coverage)) == []
