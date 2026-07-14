"""Dark/flat master building and application."""

import numpy as np
import pytest
from astropy.io import fits

from seestack.calibrate import (
    CalibrationMasters,
    build_master,
    load_master,
    save_master,
)
from seestack.calibrate.masters import MasterMeta


def _write_raw(path, data, *, exptime=None, gain=None, temp=None, bayer="RGGB"):
    hdu = fits.PrimaryHDU(data=np.asarray(data, dtype=np.float32))
    if exptime is not None:
        hdu.header["EXPTIME"] = exptime
    if gain is not None:
        hdu.header["GAIN"] = gain
    if temp is not None:
        hdu.header["CCD-TEMP"] = temp
    if bayer is not None:
        hdu.header["BAYERPAT"] = bayer
    hdu.writeto(path, overwrite=True)


def test_build_master_median(tmp_path):
    # Three frames with a constant level plus one outlier pixel each → median
    # rejects the outliers, leaving the constant.
    paths = []
    for i in range(3):
        arr = np.full((4, 4), 100.0, dtype=np.float32)
        arr[i, i] = 9000.0  # different hot pixel per frame
        p = tmp_path / f"dark_{i}.fits"
        _write_raw(p, arr, exptime=30.0, gain=80.0, temp=-5.0)
        paths.append(p)
    master, meta = build_master(paths, kind="dark", method="median")
    assert master.shape == (4, 4)
    np.testing.assert_allclose(master, 100.0)  # outliers rejected
    assert meta.kind == "dark"
    assert meta.n_frames == 3
    assert meta.exposure_s == 30.0
    assert meta.gain == 80.0
    assert meta.bayer_pattern == "RGGB"


def test_build_master_mean(tmp_path):
    paths = []
    for i, level in enumerate((10.0, 20.0, 30.0)):
        p = tmp_path / f"f_{i}.fits"
        _write_raw(p, np.full((2, 2), level, dtype=np.float32))
        paths.append(p)
    master, _ = build_master(paths, kind="flat", method="mean")
    np.testing.assert_allclose(master, 20.0)


def test_sigma_clip_mean_rejects_outlier_when_mad_is_zero():
    # Regression: a per-pixel MAD of 0 means a *majority* of frames sit exactly
    # at the median, NOT that there are no outliers. A minority cosmic-ray/hot-
    # pixel spike must still be rejected. Previously tol was set to +inf when
    # mad==0, so the spike was kept and averaged in (→ 680 below).
    from seestack.calibrate.masters import _sigma_clip_mean

    stack = np.array(
        [200, 200, 200, 200, 200, 200, 200, 200, 200, 5000], dtype=np.float32
    ).reshape(10, 1, 1)
    out = _sigma_clip_mean(stack, 3.0)
    assert float(out[0, 0]) == pytest.approx(200.0)  # spike rejected (was ~680)

    # A genuine spread (mad>0) still clips the outlier and means the rest.
    spread = np.array(
        [100, 101, 99, 102, 98, 100, 101, 9000], dtype=np.float32
    ).reshape(8, 1, 1)
    assert float(_sigma_clip_mean(spread, 3.0)[0, 0]) == pytest.approx(100.0, abs=0.5)

    # Truly-identical frames (real zero spread) keep every sample → their value.
    flat = np.full((5, 1, 1), 300.0, dtype=np.float32)
    assert float(_sigma_clip_mean(flat, 3.0)[0, 0]) == pytest.approx(300.0)


def test_sigma_clip_mean_iterates_to_convergence():
    # A moderate outlier (+6) survives the *first* clip round because a stronger
    # outlier (+10) inflates the first-round MAD enough to keep it under tol; only
    # after the strong outlier is removed does the recomputed (tighter) scale
    # reject the moderate one. A single round leaves the +6 in and pulls the mean
    # above the true core (100.86); iterating recovers the exact core mean (100.0).
    from seestack.calibrate.masters import _sigma_clip_mean

    stack = np.array(
        [98, 99, 100, 100, 101, 102, 106, 110], dtype=np.float32
    ).reshape(8, 1, 1)
    out = float(_sigma_clip_mean(stack, 3.0)[0, 0])
    assert out == pytest.approx(100.0)  # was ~100.86 with a single clip round

    # Guardrail: iterating never empties a pixel — a pathological all-different
    # column still returns the (finite) full-stack median fallback, not NaN.
    weird = np.array([1, 2, 3, 4], dtype=np.float32).reshape(4, 1, 1)
    assert np.isfinite(_sigma_clip_mean(weird, 3.0)[0, 0])


def test_build_master_sigma_mean_rejects_cosmic_ray_on_quiet_pixel(tmp_path):
    # End-to-end: a bias/dark set where every frame reads the same quiet level
    # except one frame with a cosmic-ray spike on one pixel (so that pixel's MAD
    # is 0). sigma_mean must reject the spike, not bake it into the master.
    paths = []
    for i in range(10):
        arr = np.full((4, 4), 200.0, dtype=np.float32)
        if i == 0:
            arr[2, 3] = 5000.0  # lone cosmic-ray hit on an otherwise-quiet pixel
        p = tmp_path / f"bias_{i}.fits"
        _write_raw(p, arr, exptime=0.0, gain=80.0, temp=-5.0)
        paths.append(p)
    master, meta = build_master(paths, kind="bias", method="sigma_mean", sigma=3.0)
    assert master.shape == (4, 4)
    # The spiked pixel is rejected back to the quiet level, not ~680.
    assert float(master[2, 3]) == pytest.approx(200.0, abs=1.0)
    np.testing.assert_allclose(master, 200.0, atol=1.0)
    assert meta.method == "sigma_mean"


def test_build_master_rejects_mismatched_shape(tmp_path):
    p1 = tmp_path / "a.fits"
    p2 = tmp_path / "b.fits"
    _write_raw(p1, np.full((4, 4), 5.0, dtype=np.float32))
    _write_raw(p2, np.full((2, 2), 5.0, dtype=np.float32))  # wrong shape, skipped
    master, meta = build_master([p1, p2], kind="dark", method="mean")
    assert master.shape == (4, 4)
    assert meta.n_frames == 1


def test_build_master_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        build_master([], kind="dark")


def test_build_master_bad_kind(tmp_path):
    p = tmp_path / "a.fits"
    _write_raw(p, np.ones((2, 2), dtype=np.float32))
    with pytest.raises(ValueError):
        build_master([p], kind="superdark")


def test_save_load_roundtrip(tmp_path):
    arr = np.arange(16, dtype=np.float32).reshape(4, 4)
    meta = MasterMeta(kind="flat", n_frames=12, width_px=4, height_px=4,
                      method="median", exposure_s=2.5, gain=80.0,
                      sensor_temp_c=-3.0, bayer_pattern="RGGB")
    path = tmp_path / "master_flat.fits"
    save_master(path, arr, meta)
    assert path.exists()
    loaded, lmeta = load_master(path)
    np.testing.assert_allclose(loaded, arr)
    assert lmeta.kind == "flat"
    assert lmeta.n_frames == 12
    assert lmeta.exposure_s == 2.5
    assert lmeta.bayer_pattern == "RGGB"


def test_apply_dark_subtraction(tmp_path):
    dark = np.full((4, 4), 50.0, dtype=np.float32)
    save_master(tmp_path / "dark.fits", dark,
                MasterMeta("dark", 10, 4, 4, "median"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "dark.fits"))
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    np.testing.assert_allclose(out, 150.0)
    # Input not mutated.
    np.testing.assert_allclose(raw, 200.0)


def test_apply_flat_division_normalizes(tmp_path):
    # A flat with a 2x brighter half divides that half down to match.
    flat = np.ones((4, 4), dtype=np.float32)
    flat[:, 2:] = 2.0  # right half twice as sensitive
    save_master(tmp_path / "flat.fits", flat,
                MasterMeta("flat", 10, 4, 4, "median"))
    cal = CalibrationMasters.load(flat_path=str(tmp_path / "flat.fits"))
    # mean(flat) = 1.5; flat_norm = flat/1.5 → left 0.667, right 1.333.
    raw = np.full((4, 4), 300.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    # left = 300 / (1/1.5) = 450; right = 300 / (2/1.5) = 225
    np.testing.assert_allclose(out[:, :2], 450.0, rtol=1e-5)
    np.testing.assert_allclose(out[:, 2:], 225.0, rtol=1e-5)


def test_apply_dark_then_flat(tmp_path):
    dark = np.full((2, 2), 10.0, dtype=np.float32)
    flat = np.full((2, 2), 4.0, dtype=np.float32)  # uniform → flat_norm == 1
    save_master(tmp_path / "d.fits", dark, MasterMeta("dark", 5, 2, 2, "mean"))
    save_master(tmp_path / "f.fits", flat, MasterMeta("flat", 5, 2, 2, "mean"))
    cal = CalibrationMasters.load(str(tmp_path / "d.fits"), str(tmp_path / "f.fits"))
    raw = np.full((2, 2), 110.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    np.testing.assert_allclose(out, 100.0)  # (110-10)/1


def test_apply_bias_subtraction_when_no_dark(tmp_path):
    # (light - bias) / flat with no dark: bias is the readout pedestal.
    bias = np.full((4, 4), 30.0, dtype=np.float32)
    save_master(tmp_path / "bias.fits", bias, MasterMeta("bias", 0, 4, 4, "median"))
    cal = CalibrationMasters.load(bias_path=str(tmp_path / "bias.fits"))
    assert cal.describe() == "bias"
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    np.testing.assert_allclose(out, 170.0)  # 200 - 30
    np.testing.assert_allclose(raw, 200.0)  # input untouched


def test_apply_bias_then_flat_no_dark(tmp_path):
    bias = np.full((2, 2), 20.0, dtype=np.float32)
    flat = np.full((2, 2), 4.0, dtype=np.float32)  # uniform → flat_norm == 1
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 0, 2, 2, "median"))
    save_master(tmp_path / "f.fits", flat, MasterMeta("flat", 5, 2, 2, "mean"))
    cal = CalibrationMasters.load(
        flat_path=str(tmp_path / "f.fits"), bias_path=str(tmp_path / "b.fits"))
    assert cal.describe() == "bias+flat"
    raw = np.full((2, 2), 120.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw), 100.0)  # (120-20)/1


def test_bias_not_applied_to_lights_when_dark_present(tmp_path):
    # A master dark already contains the bias pedestal — the bias must NOT be
    # subtracted from the lights again (no double-subtraction).
    dark = np.full((4, 4), 50.0, dtype=np.float32)
    bias = np.full((4, 4), 30.0, dtype=np.float32)
    save_master(tmp_path / "dark.fits", dark, MasterMeta("dark", 10, 4, 4, "median"))
    save_master(tmp_path / "bias.fits", bias, MasterMeta("bias", 0, 4, 4, "median"))
    cal = CalibrationMasters.load(
        dark_path=str(tmp_path / "dark.fits"), bias_path=str(tmp_path / "bias.fits"))
    # Dark wins; describe() shows only the dark (bias is loaded but inert here).
    assert cal.describe() == "dark"
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw), 150.0)  # 200 - 50, not 200-50-30


def test_bias_shape_mismatch_is_skipped(tmp_path):
    bias = np.full((2, 2), 30.0, dtype=np.float32)  # wrong shape vs 4×4 raw
    save_master(tmp_path / "bias.fits", bias, MasterMeta("bias", 0, 2, 2, "median"))
    cal = CalibrationMasters.load(bias_path=str(tmp_path / "bias.fits"))
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    # No matching master applies → raw passes through unchanged.
    np.testing.assert_allclose(cal.apply_raw(raw), 200.0)


def test_flat_dark_subtracted_before_normalising(tmp_path):
    # Flat = dark pedestal (100) + illumination signal (left 100, right 200).
    flat = np.empty((4, 4), dtype=np.float32)
    flat[:, :2] = 200.0  # left  = 100 pedestal + 100 signal
    flat[:, 2:] = 300.0  # right = 100 pedestal + 200 signal
    flat_dark = np.full((4, 4), 100.0, dtype=np.float32)
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, 4, 4, "median"))
    save_master(tmp_path / "fd.fits", flat_dark, MasterMeta("dark", 10, 4, 4, "median"))

    cal = CalibrationMasters.load(
        flat_path=str(tmp_path / "flat.fits"),
        flat_dark_path=str(tmp_path / "fd.fits"),
    )
    # After flat-dark: signal = [100, 200], mean = 150,
    # flat_norm = [0.667, 1.333]. A uniform raw of 300 divides to 450 / 225.
    raw = np.full((4, 4), 300.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    np.testing.assert_allclose(out[:, :2], 450.0, rtol=1e-5)
    np.testing.assert_allclose(out[:, 2:], 225.0, rtol=1e-5)


def test_flat_dark_changes_result_vs_no_flat_dark(tmp_path):
    flat = np.empty((4, 4), dtype=np.float32)
    flat[:, :2] = 200.0
    flat[:, 2:] = 300.0
    flat_dark = np.full((4, 4), 100.0, dtype=np.float32)
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, 4, 4, "median"))
    save_master(tmp_path / "fd.fits", flat_dark, MasterMeta("dark", 10, 4, 4, "median"))
    raw = np.full((4, 4), 300.0, dtype=np.float32)

    without = CalibrationMasters.load(flat_path=str(tmp_path / "flat.fits")).apply_raw(raw)
    with_fd = CalibrationMasters.load(
        flat_path=str(tmp_path / "flat.fits"),
        flat_dark_path=str(tmp_path / "fd.fits"),
    ).apply_raw(raw)
    # The pedestal makes a real difference to the flat correction.
    assert not np.allclose(without, with_fd)


def test_flat_dark_shape_mismatch_is_skipped(tmp_path):
    flat = np.full((4, 4), 2.0, dtype=np.float32)
    flat_dark = np.full((2, 2), 1.0, dtype=np.float32)  # wrong shape
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, 4, 4, "median"))
    save_master(tmp_path / "fd.fits", flat_dark, MasterMeta("dark", 10, 2, 2, "median"))
    # A mismatched flat-dark is ignored (not applied) → flat_norm is all 1.0.
    cal = CalibrationMasters.load(
        flat_path=str(tmp_path / "flat.fits"),
        flat_dark_path=str(tmp_path / "fd.fits"),
    )
    raw = np.full((4, 4), 300.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw), 300.0, rtol=1e-5)


def test_empty_calibration():
    cal = CalibrationMasters()
    assert cal.is_empty
    assert cal.describe() == "none"


def test_validate_shape_mismatch(tmp_path):
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark, MasterMeta("dark", 5, 4, 4, "mean"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    cal.validate((4, 4))  # ok
    with pytest.raises(ValueError, match="must match"):
        cal.validate((8, 8))


def test_calibration_flows_through_align_one(tmp_path):
    """A constant dark subtracted at load time lowers the aligned output by
    that constant (debayer + identity reproject are linear, so a uniform
    offset passes straight through)."""
    pytest.importorskip("scipy")
    from seestack.io.fits_loader import load_seestar_raw
    from seestack.stack.align import align_one
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    p = write_seestar_fits(tmp_path / "light.fit", add_wcs=True, n_stars=15, seed=7)
    raw, _ = load_seestar_raw(p, debayer=False)
    offset = 25.0
    dark = np.full(raw.shape, offset, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark, MasterMeta("dark", 5, raw.shape[1], raw.shape[0], "mean"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))

    wcs_text = make_synth_wcs_text()
    common = dict(bayer_pattern="RGGB", src_wcs_text=wcs_text, dst_wcs_text=wcs_text,
                  dst_shape=(320, 480), suppress_hot_pixels=False)
    base = align_one(str(p), **common)
    calib = align_one(str(p), calibration=cal, **common)
    assert base is not None and calib is not None
    bi = base[0][30:-30, 30:-30, :]
    ci = calib[0][30:-30, 30:-30, :]
    finite = np.isfinite(bi) & np.isfinite(ci)
    diff = (bi - ci)[finite]
    np.testing.assert_allclose(np.mean(diff), offset, atol=1.0)


def _save_dark_and_bias(tmp_path, *, dark_level, bias_level, dark_exp, shape=(4, 4)):
    dark = np.full(shape, dark_level, dtype=np.float32)
    bias = np.full(shape, bias_level, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, shape[1], shape[0], "median", exposure_s=dark_exp))
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 5, shape[1], shape[0], "median"))
    return str(tmp_path / "d.fits"), str(tmp_path / "b.fits")


def test_dark_exposure_scaling_scales_dark_current(tmp_path):
    # Dark = bias(20) + dark-current(90) shot at 30s; subs are 10s → the dark
    # current scales by 10/30 while the bias pedestal stays fixed:
    # scaled dark = 20 + 90×(1/3) = 50.
    d, b = _save_dark_and_bias(tmp_path, dark_level=110.0, bias_level=20.0, dark_exp=30.0)
    cal = CalibrationMasters.load(dark_path=d, bias_path=b, scale_dark_to_light=True)
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw, light_exposure_s=10.0), 150.0)  # 200-50
    # A matched exposure (ratio ~1) subtracts the full 110, same as no scaling.
    np.testing.assert_allclose(cal.apply_raw(raw, light_exposure_s=30.0), 90.0)


def test_dark_scaling_off_by_default(tmp_path):
    # The flag defaults off, so a mismatched dark is subtracted unscaled (today's
    # behaviour) — an upgrade doesn't change any existing stack.
    d, b = _save_dark_and_bias(tmp_path, dark_level=110.0, bias_level=20.0, dark_exp=30.0)
    cal = CalibrationMasters.load(dark_path=d, bias_path=b)
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw, light_exposure_s=10.0), 90.0)


def test_dark_scaling_neutral_without_bias(tmp_path):
    # Scaling needs the bias to hold the pedestal fixed; without one the dark is
    # used unscaled even with the flag on.
    dark = np.full((4, 4), 110.0, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                  scale_dark_to_light=True)
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw, light_exposure_s=10.0), 90.0)


def test_dark_scaling_neutral_when_exposure_unknown(tmp_path):
    # Missing light exposure (direct callers) OR missing dark exposure → no ratio,
    # so the dark is used unscaled in both cases.
    d, b = _save_dark_and_bias(tmp_path, dark_level=110.0, bias_level=20.0, dark_exp=30.0)
    cal = CalibrationMasters.load(dark_path=d, bias_path=b, scale_dark_to_light=True)
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw), 90.0)  # no light exposure passed

    dark = np.full((4, 4), 110.0, dtype=np.float32)
    bias = np.full((4, 4), 20.0, dtype=np.float32)
    save_master(tmp_path / "dn.fits", dark, MasterMeta("dark", 5, 4, 4, "median"))  # no EXPTIME
    save_master(tmp_path / "bn.fits", bias, MasterMeta("bias", 5, 4, 4, "median"))
    cal2 = CalibrationMasters.load(dark_path=str(tmp_path / "dn.fits"),
                                   bias_path=str(tmp_path / "bn.fits"),
                                   scale_dark_to_light=True)
    np.testing.assert_allclose(cal2.apply_raw(raw, light_exposure_s=10.0), 90.0)


def test_dark_exposure_scaling_flows_through_align_one(tmp_path):
    """The light frame's own exposure reaches apply_raw, so a 30s dark is scaled
    to the synth sub's 10s: scaling subtracts less pedestal than the unscaled
    dark, leaving the aligned output higher by the difference (50 vs 110 → +60)."""
    pytest.importorskip("scipy")
    from seestack.io.fits_loader import load_seestar_raw
    from seestack.stack.align import align_one
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    p = write_seestar_fits(tmp_path / "light.fit", add_wcs=True, n_stars=15, seed=7)  # 10s
    raw, _ = load_seestar_raw(p, debayer=False)
    shape = raw.shape
    dark = np.full(shape, 110.0, dtype=np.float32)  # bias(20) + 90 dark-current @30s
    bias = np.full(shape, 20.0, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, shape[1], shape[0], "median", exposure_s=30.0))
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 5, shape[1], shape[0], "median"))
    scaled = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                     bias_path=str(tmp_path / "b.fits"),
                                     scale_dark_to_light=True)
    unscaled = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                       bias_path=str(tmp_path / "b.fits"))
    wcs_text = make_synth_wcs_text()
    common = dict(bayer_pattern="RGGB", src_wcs_text=wcs_text, dst_wcs_text=wcs_text,
                  dst_shape=(320, 480), suppress_hot_pixels=False)
    a = align_one(str(p), calibration=scaled, **common)
    b_ = align_one(str(p), calibration=unscaled, **common)
    assert a is not None and b_ is not None
    ai = a[0][30:-30, 30:-30, :]
    bi = b_[0][30:-30, 30:-30, :]
    finite = np.isfinite(ai) & np.isfinite(bi)
    np.testing.assert_allclose(np.mean((ai - bi)[finite]), 60.0, atol=1.0)


def test_apply_raw_empty_bundle_returns_a_fresh_array():
    # apply_raw documents "returns a new array — the input is not modified", but
    # an empty bundle applied to an already-float32 input used to alias ``raw``
    # (np.asarray + astype(copy=False) are both no-ops), so a consumer mutating
    # the result in place would silently corrupt the shared source frame.
    cal = CalibrationMasters()
    assert cal.is_empty
    raw = np.full((3, 3), 500.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert out is not raw  # fails before the fix (aliases raw)
    np.testing.assert_array_equal(out, raw)  # same values, different buffer
    out[0, 0] = -1.0
    assert raw[0, 0] == 500.0  # mutating the result never touches the input


def test_apply_raw_with_masters_does_not_double_copy(tmp_path):
    # The empty-path copy must not add a hot-path copy when a master applies: a
    # dark subtraction already yields a fresh array, so the result is never the
    # input and no extra copy is taken.
    dark = np.full((3, 3), 50.0, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark, MasterMeta("dark", 5, 3, 3, "mean"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    raw = np.full((3, 3), 200.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert out is not raw
    np.testing.assert_allclose(out, 150.0)


def test_flat_floor_guards_divide(tmp_path):
    # A flat with a near-zero pixel must not explode the calibrated output.
    flat = np.full((3, 3), 100.0, dtype=np.float32)
    flat[0, 0] = 0.0  # dead pixel
    save_master(tmp_path / "f.fits", flat, MasterMeta("flat", 5, 3, 3, "mean"))
    cal = CalibrationMasters.load(flat_path=str(tmp_path / "f.fits"))
    raw = np.full((3, 3), 500.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert np.isfinite(out).all()
    # The dead pixel is floored to flat_norm=1.0 → output stays at the raw value.
    assert out[0, 0] == 500.0
