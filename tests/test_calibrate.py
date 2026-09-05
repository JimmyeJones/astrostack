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


@pytest.mark.parametrize("method", ["median", "mean", "sigma_mean"])
def test_build_master_is_nan_aware(tmp_path, method):
    # A user-supplied float FITS calibration frame carrying a NaN/inf pixel must
    # not poison the whole master at that pixel — NaN = "no data", so the combine
    # ignores it and averages the finite samples (engine invariant). Before the
    # NaN-aware fix, plain np.median/np.mean propagated the NaN into the master
    # (and thence every calibrated light) for the median/mean methods.
    paths = []
    for i in range(4):
        arr = np.full((2, 2), 100.0, dtype=np.float32)
        if i == 0:
            arr[0, 0] = np.nan  # one bad pixel in one frame
            arr[0, 1] = np.inf  # ...and a non-finite spike
        p = tmp_path / f"dark_{i}.fits"
        _write_raw(p, arr, exptime=30.0)
        paths.append(p)
    master, _ = build_master(paths, kind="dark", method=method, sigma=3.0)
    # The affected pixels fall back to the finite samples (all 100.0), and every
    # other pixel is untouched — no NaN/inf anywhere in the master.
    assert np.all(np.isfinite(master)), "non-finite input poisoned the master"
    np.testing.assert_allclose(master, 100.0)


@pytest.mark.parametrize("method", ["median", "mean", "sigma_mean"])
def test_build_master_all_inf_pixel_stays_nan(tmp_path, method):
    # Sibling of the all-NaN case, but with *inf*: the combine masks non-finite
    # samples in place (the memory-frugal path), so an inf must be treated as
    # "no data" exactly like a NaN — a pixel that is inf in every frame stays NaN
    # (never folded to a finite value or left as inf), and n_frames is unaffected.
    paths = []
    for i in range(4):
        arr = np.full((3, 3), 200.0, dtype=np.float32)
        arr[0, 0] = np.inf  # no finite sample at (0, 0) in any frame
        arr[1, 1] = np.inf if i == 0 else 200.0  # inf in one frame only → finite
        p = tmp_path / f"f_{i}.fits"
        _write_raw(p, arr, exptime=30.0)
        paths.append(p)
    master, meta = build_master(paths, kind="dark", method=method, sigma=3.0)
    assert meta.n_frames == 4
    assert np.isnan(master[0, 0]), "an all-inf pixel must stay NaN (no data)"
    # Every pixel with at least one finite sample resolves to the finite value.
    assert np.isfinite(master[1, 1]) and master[1, 1] == pytest.approx(200.0)
    finite = np.isfinite(master)
    np.testing.assert_allclose(master[finite], 200.0)


def test_build_master_all_nan_pixel_stays_nan(tmp_path):
    # If *no* frame has a finite sample at a pixel, that pixel is genuinely
    # "no data" and must stay NaN (not be folded to 0), per the coverage invariant.
    paths = []
    for i in range(3):
        arr = np.full((2, 2), 50.0, dtype=np.float32)
        arr[0, 0] = np.nan  # no finite sample at (0, 0) in any frame
        p = tmp_path / f"f_{i}.fits"
        _write_raw(p, arr)
        paths.append(p)
    master, _ = build_master(paths, kind="dark", method="mean")
    assert np.isnan(master[0, 0])
    np.testing.assert_allclose(master[1:, :], 50.0)
    np.testing.assert_allclose(master[0, 1], 50.0)


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


def test_build_master_follows_the_majority_shape_not_the_first_frame(tmp_path):
    # Regression: the reference shape used to be whichever frame loaded *first*,
    # so a single stray file from another camera/binning mode sorted ahead of the
    # real set made every genuine frame "wrong size" — a one-frame master of the
    # wrong sensor, reported as a successful build and only failing much later
    # when a stack refused it on shape. The majority must win instead.
    stray = tmp_path / "a_stray.fits"
    _write_raw(stray, np.full((2, 2), 7.0, dtype=np.float32))
    paths = [stray]
    for i in range(5):
        p = tmp_path / f"b_dark_{i}.fits"
        _write_raw(p, np.full((4, 4), 100.0, dtype=np.float32), exptime=30.0)
        paths.append(p)

    skipped: list[tuple[str, str]] = []
    master, meta = build_master(paths, kind="dark", method="mean", skipped=skipped)

    assert master.shape == (4, 4)
    assert meta.n_frames == 5
    np.testing.assert_allclose(master, 100.0)
    # ...and the odd one out is the one reported as set aside.
    assert skipped == [("a_stray.fits", "wrong size")]
    # The metadata comes from the frames actually combined, not the stray.
    assert meta.exposure_s == 30.0


def test_build_master_keeps_the_first_shape_when_the_split_is_even(tmp_path):
    # With no majority there is nothing better to go on than the order given, so
    # the first-seen shape wins — exactly what this did before.
    a1 = tmp_path / "a1.fits"
    a2 = tmp_path / "a2.fits"
    b1 = tmp_path / "b1.fits"
    b2 = tmp_path / "b2.fits"
    for p in (a1, a2):
        _write_raw(p, np.full((4, 4), 100.0, dtype=np.float32))
    for p in (b1, b2):
        _write_raw(p, np.full((2, 2), 5.0, dtype=np.float32))
    master, meta = build_master([a1, a2, b1, b2], kind="dark", method="mean")
    assert master.shape == (4, 4)
    assert meta.n_frames == 2


def test_build_master_collects_skipped_frames(tmp_path):
    # The optional `skipped` out-param lets the caller tell the user how many of
    # their frames were set aside (and why) — a wrong-size frame and an unreadable
    # one are recorded with plain-language reasons; the master uses only the good ones.
    good1 = tmp_path / "good1.fits"
    good2 = tmp_path / "good2.fits"
    wrong = tmp_path / "wrong.fits"
    bad = tmp_path / "bad.fits"
    _write_raw(good1, np.full((4, 4), 100.0, dtype=np.float32))
    _write_raw(good2, np.full((4, 4), 100.0, dtype=np.float32))
    _write_raw(wrong, np.full((2, 2), 100.0, dtype=np.float32))  # mismatched shape
    bad.write_bytes(b"not a fits file at all")               # fails to load
    skipped: list[tuple[str, str]] = []
    master, meta = build_master(
        [good1, good2, wrong, bad], kind="dark", method="mean", skipped=skipped,
    )
    assert master.shape == (4, 4)
    assert meta.n_frames == 2                       # only the two good frames combined
    reasons = {name: reason for name, reason in skipped}
    assert reasons == {"wrong.fits": "wrong size", "bad.fits": "unreadable"}


def test_build_master_skipped_stays_empty_on_a_clean_set(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"f_{i}.fits"
        _write_raw(p, np.full((4, 4), 50.0, dtype=np.float32))
        paths.append(p)
    skipped: list[tuple[str, str]] = []
    build_master(paths, kind="flat", method="median", skipped=skipped)
    assert skipped == []


def test_build_master_cancel_mid_load_returns_none_and_writes_nothing(tmp_path):
    # A long dark/flat build must honour a mid-build cancel: build_master returns
    # None (no partial master) as soon as should_stop() trips, and it stops
    # promptly rather than loading every remaining frame.
    paths = []
    for i in range(6):
        p = tmp_path / f"dark_{i}.fits"
        _write_raw(p, np.full((4, 4), 100.0, dtype=np.float32))
        paths.append(p)

    calls = {"n": 0}

    def should_stop():
        # Allow the first two per-frame checkpoints, then request cancel.
        calls["n"] += 1
        return calls["n"] > 2

    # Track how many frames were actually touched via the progress callback.
    seen = []

    def progress(stage, i, total):
        seen.append((stage, i))

    result = build_master(
        paths, kind="dark", method="median",
        progress=progress, should_stop=should_stop,
    )
    assert result is None  # cancelled → no master, no meta
    # Stopped promptly: it never reached the later frames or the combine stage.
    assert not any(stage == "Combining" for stage, _ in seen)
    assert max((i for _, i in seen), default=0) <= 2


def test_build_master_should_stop_never_true_builds_normally(tmp_path):
    # A should_stop that never fires leaves behaviour identical to the default.
    paths = []
    for i in range(3):
        p = tmp_path / f"dark_{i}.fits"
        _write_raw(p, np.full((4, 4), 100.0, dtype=np.float32), exptime=30.0)
        paths.append(p)
    result = build_master(
        paths, kind="dark", method="median", should_stop=lambda: False,
    )
    assert result is not None
    master, meta = result
    np.testing.assert_allclose(master, 100.0)
    assert meta.n_frames == 3


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


def test_apply_dark_nonfinite_pixel_does_not_poison_the_light(tmp_path):
    # A master dark legitimately carries a NaN "no-data" pixel (build_master
    # produces one where no input frame was finite there) and can carry an inf
    # from an imported master. Subtracting it verbatim would turn real signal
    # into NaN/inf at that pixel of *every* calibrated light — a permanent hole
    # / a reduction-poisoning value. A no-data pedestal pixel means "no
    # correction", so it must leave the light unchanged there (subtract 0).
    dark = np.full((4, 4), 50.0, dtype=np.float32)
    dark[1, 2] = np.nan  # genuinely no data
    dark[3, 0] = np.inf  # e.g. a broken third-party master
    save_master(tmp_path / "dark.fits", dark,
                MasterMeta("dark", 10, 4, 4, "median"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "dark.fits"))
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert np.isfinite(out).all()  # fails before: NaN + -inf present
    assert out[1, 2] == 200.0  # no-data → uncorrected real signal, not NaN
    assert out[3, 0] == 200.0  # inf → uncorrected, not -inf
    np.testing.assert_allclose(out[0, 0], 150.0)  # ordinary pixel still 200-50


def test_apply_bias_nonfinite_pixel_does_not_poison_the_light(tmp_path):
    # Same guard on the bias-only pedestal path (light - bias, no dark).
    bias = np.full((4, 4), 30.0, dtype=np.float32)
    bias[2, 1] = np.nan
    save_master(tmp_path / "bias.fits", bias, MasterMeta("bias", 0, 4, 4, "median"))
    cal = CalibrationMasters.load(bias_path=str(tmp_path / "bias.fits"))
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert np.isfinite(out).all()
    assert out[2, 1] == 200.0  # no-data → uncorrected, not NaN
    np.testing.assert_allclose(out[0, 0], 170.0)  # 200 - 30


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


def _vignetted_flat_masters(tmp_path, *, pedestal=500.0, flat_dark_shape=None):
    """A vignetted flat riding on ``pedestal``, plus a flat-dark of that pedestal.

    ``flat_dark_shape`` defaults to the flat's own shape; pass a different one to
    build the mismatched flat-dark the guard below is about.
    """
    h, w = 40, 60
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h / 2, xx - w / 2) / np.hypot(h / 2, w / 2)
    illum = (1.0 - 0.4 * r ** 2).astype(np.float32)  # 40% corner vignette
    flat = (illum * 2000.0 + pedestal).astype(np.float32)
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, w, h, "median"))
    fdh, fdw = flat_dark_shape or (h, w)
    flat_dark = np.full((fdh, fdw), pedestal, dtype=np.float32)
    save_master(tmp_path / "fd.fits", flat_dark,
                MasterMeta("dark", 10, fdw, fdh, "median"))
    return illum, str(tmp_path / "flat.fits"), str(tmp_path / "fd.fits")


def test_mismatched_flat_dark_is_reported_and_measurably_worsens_the_flat(tmp_path):
    # The one calibration pick that is neither refused nor applied: the stack
    # succeeds and the flat is normalised with its own pedestal still in it, so
    # part of the vignetting survives. Before this warning the only trace was a
    # server-log line the walk-away user never reads.
    illum, flat_path, fd_path = _vignetted_flat_masters(
        tmp_path, flat_dark_shape=(42, 60))
    cal = CalibrationMasters.load(flat_path=flat_path, flat_dark_path=fd_path)
    assert cal.flat_dark_shape_mismatch == ((42, 60), (40, 60))
    warns = cal.calibration_warnings(10.0)
    assert len(warns) == 1
    # Both sizes named, w×h like every sibling warning, and it must NOT claim the
    # stack fails — that was the untruth on the Stack form.
    assert "60×42" in warns[0] and "60×40" in warns[0]
    assert "vignetting" in warns[0]
    # Measured: dividing a perfectly-flat-illuminated light by this flat leaves a
    # real residual, where a matching flat-dark leaves none.
    light = (illum * 1000.0).astype(np.float32)
    bad = cal.apply_raw(light)
    assert bad.max() / bad.min() > 1.1  # ~13% residual vignette

    _, flat_ok, fd_ok = _vignetted_flat_masters(tmp_path)
    good = CalibrationMasters.load(flat_path=flat_ok, flat_dark_path=fd_ok)
    assert good.flat_dark_shape_mismatch is None
    assert good.calibration_warnings(10.0) == []
    corrected = good.apply_raw(light)
    assert corrected.max() / corrected.min() == pytest.approx(1.0, abs=1e-3)


def test_flat_dark_mismatch_warning_is_silent_without_a_usable_flat(tmp_path):
    # A flat whose mean is non-positive is ignored entirely, so the flat-dark
    # that couldn't be subtracted from it changes nothing worth mentioning.
    flat = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, 4, 4, "median"))
    flat_dark = np.full((2, 2), 1.0, dtype=np.float32)
    save_master(tmp_path / "fd.fits", flat_dark, MasterMeta("dark", 10, 2, 2, "median"))
    cal = CalibrationMasters.load(
        flat_path=str(tmp_path / "flat.fits"),
        flat_dark_path=str(tmp_path / "fd.fits"),
    )
    assert cal.flat_norm is None
    assert cal.calibration_warnings(10.0) == []


def test_flat_dark_mismatch_warning_rides_alongside_the_dark_warnings(tmp_path):
    # The flat-dark note is emitted before the `dark is None` early return, so it
    # must survive both with and without a master dark in the bundle.
    _, flat_path, fd_path = _vignetted_flat_masters(tmp_path, flat_dark_shape=(42, 60))
    dark = np.full((40, 60), 5.0, dtype=np.float32)
    save_master(tmp_path / "dark.fits", dark,
                MasterMeta("dark", 10, 60, 40, "median", exposure_s=30.0))
    warns = CalibrationMasters.load(
        dark_path=str(tmp_path / "dark.fits"),
        flat_path=flat_path, flat_dark_path=fd_path,
    ).calibration_warnings(10.0)
    assert len(warns) == 2
    assert any("flat-dark" in w for w in warns)
    assert any("Master dark is 30s" in w for w in warns)


def test_flat_dark_nonfinite_pixel_does_not_drop_the_whole_flat(tmp_path):
    # An imported third-party flat-dark carrying an inf pixel used to make the
    # flat's nanmean non-finite, silently dropping the *entire* flat (so the
    # flat correction vanished everywhere). Sanitizing the flat-dark to 0 at
    # that pixel (= no subtraction there, mirroring the master dark/bias) keeps
    # the flat usable; only the one no-data pixel is left uncorrected.
    flat = np.empty((4, 4), dtype=np.float32)
    flat[:, :2] = 200.0  # left  = 100 pedestal + 100 signal
    flat[:, 2:] = 300.0  # right = 100 pedestal + 200 signal
    flat_dark = np.full((4, 4), 100.0, dtype=np.float32)
    flat_dark[0, 0] = np.inf  # broken third-party pixel
    flat_dark[3, 3] = np.nan  # genuinely no data
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, 4, 4, "median"))
    save_master(tmp_path / "fd.fits", flat_dark, MasterMeta("dark", 10, 4, 4, "median"))

    cal = CalibrationMasters.load(
        flat_path=str(tmp_path / "flat.fits"),
        flat_dark_path=str(tmp_path / "fd.fits"),
    )
    # Fails before: the inf propagated into the flat → nanmean inf → flat dropped
    # → flat_norm is None → no flat correction at all.
    assert cal.flat_norm is not None
    raw = np.full((4, 4), 300.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert np.isfinite(out).all()
    # The bulk of the flat still corrects (left/right differ), unlike a dropped flat.
    assert not np.allclose(out, 300.0)


def test_flat_nonfinite_pixel_does_not_drop_the_whole_flat(tmp_path):
    # An imported/third-party master *flat* carrying an inf pixel used to make
    # the flat's nanmean non-finite, silently dropping the *entire* flat (so all
    # vignetting/dust correction vanished). A NaN pixel was already tolerated
    # (nanmean ignores it, floored to 1.0), but inf was not — this completes the
    # non-finite sanitisation the master dark/bias (v0.135.1) and flat-dark
    # (v0.136.5) already have. Mapping non-finite flat pixels to NaN keeps the
    # flat usable; only the one no-data pixel is left uncorrected.
    flat = np.empty((4, 4), dtype=np.float32)
    flat[:, :2] = 1000.0  # left  half
    flat[:, 2:] = 2000.0  # right half — a real vignetting gradient to correct
    flat[0, 0] = np.inf   # broken imported pixel
    flat[3, 3] = np.nan   # genuinely no data (already handled; kept as a control)
    save_master(tmp_path / "flat.fits", flat, MasterMeta("flat", 10, 4, 4, "median"))

    cal = CalibrationMasters.load(flat_path=str(tmp_path / "flat.fits"))
    # Fails before: the inf made nanmean(flat) inf → flat dropped → flat_norm None
    # → no flat correction anywhere.
    assert cal.flat_norm is not None
    # The two no-data pixels are left uncorrected (floored to 1.0), everything
    # else normalises around the (finite) mean.
    assert cal.flat_norm[0, 0] == 1.0  # the former inf pixel
    assert cal.flat_norm[3, 3] == 1.0  # the NaN pixel
    assert np.isfinite(cal.flat_norm).all()
    raw = np.full((4, 4), 1500.0, dtype=np.float32)
    out = cal.apply_raw(raw)
    assert np.isfinite(out).all()
    # The bulk of the flat still corrects (left/right differ), unlike a dropped flat.
    assert not np.allclose(out, out.flat[0])


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


def test_validate_ignores_a_wrong_shaped_bias_that_is_never_applied(tmp_path):
    # A leftover wrong-binning master bias, loaded alongside a good dark+flat,
    # is never applied to the lights (the dark carries the pedestal), so it must
    # NOT abort an otherwise-valid stack. Before the fix, validate() checked the
    # bias unconditionally and raised.
    dark = np.zeros((4, 4), dtype=np.float32)
    flat = np.full((4, 4), 100.0, dtype=np.float32)
    bias = np.zeros((2, 2), dtype=np.float32)  # wrong shape; inert (dark present)
    save_master(tmp_path / "d.fits", dark, MasterMeta("dark", 5, 4, 4, "mean"))
    save_master(tmp_path / "f.fits", flat, MasterMeta("flat", 5, 4, 4, "mean"))
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 0, 2, 2, "mean"))
    cal = CalibrationMasters.load(
        dark_path=str(tmp_path / "d.fits"),
        flat_path=str(tmp_path / "f.fits"),
        bias_path=str(tmp_path / "b.fits"))
    assert not cal._bias_applies  # dark present → bias inert
    cal.validate((4, 4))  # must not raise over the inert mismatched bias


def test_validate_still_catches_a_wrong_shaped_bias_that_is_applied(tmp_path):
    # With no dark, the bias IS applied — a shape mismatch must still fail fast.
    bias = np.zeros((2, 2), dtype=np.float32)
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 0, 2, 2, "mean"))
    cal = CalibrationMasters.load(bias_path=str(tmp_path / "b.fits"))
    assert cal._bias_applies
    with pytest.raises(ValueError, match="must match"):
        cal.validate((4, 4))


def test_calibration_warns_on_a_mismatched_dark_exposure(tmp_path):
    # A 30 s master dark applied (unscaled) to 10 s subs over-subtracts its
    # pedestal ~3× on every frame — validate() (shape only) can't catch it, so
    # calibration_warnings() must flag it.
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=30.0))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    warns = cal.calibration_warnings(light_exposure_s=10.0)
    assert len(warns) == 1
    assert "30" in warns[0] and "10" in warns[0]
    assert "over-subtracted" in warns[0]


def test_calibration_no_exposure_warning_when_matched(tmp_path):
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=10.0))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    # Exactly matched, and a tiny rounding difference, both stay silent.
    assert cal.calibration_warnings(light_exposure_s=10.0) == []
    assert cal.calibration_warnings(light_exposure_s=10.5) == []


def test_calibration_exposure_warning_suppressed_when_scaling_is_on(tmp_path):
    # With exposure-scaling on and a bias present, the exposure gap is corrected
    # by _effective_dark itself, so there's nothing to warn about.
    dark = np.zeros((4, 4), dtype=np.float32)
    bias = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=30.0))
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 5, 4, 4, "mean", exposure_s=0.0))
    cal = CalibrationMasters.load(
        dark_path=str(tmp_path / "d.fits"),
        bias_path=str(tmp_path / "b.fits"),
        scale_dark_to_light=True)
    assert cal.calibration_warnings(light_exposure_s=10.0) == []


def test_calibration_exposure_warning_fires_when_bias_shape_mismatch_disables_scaling(tmp_path):
    # Regression: scaling only takes effect when the master bias matches the
    # dark's shape (_effective_dark). A loaded but *wrong-shaped* bias makes
    # _effective_dark fall back to the unscaled dark — so the exposure-mismatch
    # advisory must still fire. Previously calibration_warnings() checked only
    # "bias present" and silenced the warning exactly when the unscaled fallback
    # over/under-subtracts a mismatched-exposure pedestal on every frame.
    dark = np.full((4, 4), 300.0, dtype=np.float32)   # 100 pedestal + 200 dark current
    bias = np.full((2, 2), 100.0, dtype=np.float32)   # wrong shape → scaling disabled
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=30.0))
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 5, 2, 2, "mean", exposure_s=0.0))
    cal = CalibrationMasters.load(
        dark_path=str(tmp_path / "d.fits"),
        bias_path=str(tmp_path / "b.fits"),
        scale_dark_to_light=True)
    # Scaling did NOT take effect: the dark is subtracted unscaled at 300 ADU
    # (a matched-shape bias would have scaled it to 100 + 200·(10/30) = 166.67).
    eff = cal._effective_dark(10.0)
    assert eff is not None and float(eff[0, 0]) == 300.0
    # …so the exposure-mismatch advisory must fire (fail-before: it was silenced).
    warns = cal.calibration_warnings(light_exposure_s=10.0)
    assert len(warns) == 1
    assert "30" in warns[0] and "10" in warns[0]
    assert "over-subtracted" in warns[0]


def test_the_exposure_warning_says_the_bias_shape_is_why_scaling_did_nothing(tmp_path):
    """Telling someone who has already turned scaling on to "turn on dark
    exposure-scaling" is advice they can't act on — and leaves them with no idea
    why the option they enabled changed nothing."""
    dark = np.full((4, 4), 300.0, dtype=np.float32)
    bias = np.full((2, 2), 100.0, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=30.0))
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 5, 2, 2, "mean", exposure_s=0.0))
    cal = CalibrationMasters.load(
        dark_path=str(tmp_path / "d.fits"),
        bias_path=str(tmp_path / "b.fits"),
        scale_dark_to_light=True)

    (warn,) = cal.calibration_warnings(light_exposure_s=10.0)
    # Names both sizes (width×height, as ``validate`` phrases them) …
    assert "2×2" in warn and "4×4" in warn
    # …says the dark went in unscaled, and does not ask for something already done.
    assert "unscaled" in warn
    assert "turn on dark" not in warn


def test_dark_scaling_provenance_matches_what_effective_dark_actually_did(tmp_path):
    """The provenance predicate is the run's only claim that the dark was
    matched to the subs, so it must agree with the pixels."""
    dark = np.full((4, 4), 300.0, dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=30.0))
    save_master(tmp_path / "good.fits", np.full((4, 4), 100.0, dtype=np.float32),
                MasterMeta("bias", 5, 4, 4, "mean", exposure_s=0.0))
    save_master(tmp_path / "bad.fits", np.full((2, 2), 100.0, dtype=np.float32),
                MasterMeta("bias", 5, 2, 2, "mean", exposure_s=0.0))

    good = CalibrationMasters.load(
        dark_path=str(tmp_path / "d.fits"), bias_path=str(tmp_path / "good.fits"),
        scale_dark_to_light=True)
    assert good.dark_scaling_provenance(10.0) == (30.0, 10.0)
    assert float(good._effective_dark(10.0)[0, 0]) == pytest.approx(166.667, abs=1e-2)
    # Matched exposures leave the dark alone, so there is nothing to claim.
    assert good.dark_scaling_provenance(30.0) is None
    assert good.dark_scaling_provenance(None) is None

    bad = CalibrationMasters.load(
        dark_path=str(tmp_path / "d.fits"), bias_path=str(tmp_path / "bad.fits"),
        scale_dark_to_light=True)
    assert float(bad._effective_dark(10.0)[0, 0]) == 300.0   # unscaled
    assert bad.dark_scaling_provenance(10.0) is None         # …so: no claim


def test_calibration_warns_on_a_mismatched_dark_temperature(tmp_path):
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=10.0,
                           sensor_temp_c=-10.0))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    # Matched exposure, but the dark is 15 °C colder than the subs.
    warns = cal.calibration_warnings(light_exposure_s=10.0, light_temp_c=5.0)
    assert len(warns) == 1
    assert "temperature" in warns[0]
    # A small temperature difference (within tolerance) stays silent.
    assert cal.calibration_warnings(light_exposure_s=10.0, light_temp_c=-8.0) == []


def test_calibration_warnings_empty_without_a_dark_or_unknown_headers(tmp_path):
    # No dark → nothing to warn about (a bias-only calibration is exposure-
    # independent).
    bias = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 5, 4, 4, "mean"))
    cal = CalibrationMasters.load(bias_path=str(tmp_path / "b.fits"))
    assert cal.calibration_warnings(light_exposure_s=10.0) == []
    # A dark whose header carried no exposure can't be compared → silent.
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark, MasterMeta("dark", 5, 4, 4, "mean"))
    cal2 = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    assert cal2.calibration_warnings(light_exposure_s=10.0) == []


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


def test_dark_scaling_keeps_no_data_dark_pixel_uncorrected(tmp_path):
    # A no-data dark pixel (NaN → sanitized to 0) must still mean "no correction"
    # on the exposure-scaling path, exactly as on the unscaled path. Without the
    # fix, _effective_dark scales the sanitized 0 into bias·(1 − ratio) and
    # apply_raw *adds* that spurious pedestal into every calibrated light there.
    dark = np.array([[np.nan, 100.0]], dtype=np.float32)  # pixel 0 = no data
    bias = np.array([[200.0, 50.0]], dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 2, 1, "median", exposure_s=10.0))
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 5, 2, 1, "median"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                  bias_path=str(tmp_path / "b.fits"),
                                  scale_dark_to_light=True)
    raw = np.full((1, 2), 1500.0, dtype=np.float32)
    out = cal.apply_raw(raw, light_exposure_s=20.0)  # ratio = 2
    assert np.isfinite(out).all()
    # No-data dark pixel → uncorrected (subtract 0), not raw + bias·(ratio−1).
    # Fail-before: 1500 − (200 + (0−200)·2) = 1500 − (−200) = 1700.
    np.testing.assert_allclose(out[0, 0], 1500.0)
    # Finite dark pixel still scales: dark = 50 + (100−50)·2 = 150 → 1500 − 150.
    np.testing.assert_allclose(out[0, 1], 1350.0)


def test_dark_scaling_falls_back_to_unscaled_dark_at_a_no_data_bias_pixel(tmp_path):
    # A no-data *bias* pixel (NaN → sanitized to 0) has no trustworthy pedestal to
    # hold fixed, so the scaled formula bias + (dark − bias)·ratio collapses to
    # dark·ratio — a scaled dark instead of the documented "subtract the dark
    # unscaled" fallback. The fix restores the plain dark at those pixels.
    dark = np.array([[100.0, 110.0]], dtype=np.float32)  # both finite
    bias = np.array([[np.nan, 20.0]], dtype=np.float32)  # pixel 0 = no data
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 2, 1, "median", exposure_s=30.0))
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 5, 2, 1, "median"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                  bias_path=str(tmp_path / "b.fits"),
                                  scale_dark_to_light=True)
    assert cal.bias_nodata_mask is not None
    raw = np.full((1, 2), 1000.0, dtype=np.float32)
    out = cal.apply_raw(raw, light_exposure_s=10.0)  # ratio = 1/3
    assert np.isfinite(out).all()
    # No-data bias pixel → unscaled dark subtracted: 1000 − 100 = 900.
    # Fail-before: 1000 − (0 + (100−0)/3) = 1000 − 33.33 = 966.67.
    np.testing.assert_allclose(out[0, 0], 900.0)
    # Finite bias pixel still scales: dark = 20 + (110−20)/3 = 50 → 1000 − 50.
    np.testing.assert_allclose(out[0, 1], 950.0, rtol=1e-5)


def test_dark_scaling_no_data_dark_pixel_wins_over_no_data_bias(tmp_path):
    # A pixel that is no-data in BOTH masters must land on "no correction" (the
    # dark-no-data rule), not on the unscaled-dark bias fallback.
    dark = np.array([[np.nan, 100.0]], dtype=np.float32)  # pixel 0 = no data
    bias = np.array([[np.nan, 20.0]], dtype=np.float32)   # pixel 0 = no data too
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 2, 1, "median", exposure_s=30.0))
    save_master(tmp_path / "b.fits", bias, MasterMeta("bias", 5, 2, 1, "median"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                  bias_path=str(tmp_path / "b.fits"),
                                  scale_dark_to_light=True)
    raw = np.full((1, 2), 1000.0, dtype=np.float32)
    out = cal.apply_raw(raw, light_exposure_s=10.0)  # ratio = 1/3
    assert np.isfinite(out).all()
    np.testing.assert_allclose(out[0, 0], 1000.0)  # no correction (subtract 0)


def test_dark_scaling_all_finite_bias_keeps_no_mask(tmp_path):
    # An all-finite bias retains no mask, so the common path is unchanged.
    d, b = _save_dark_and_bias(tmp_path, dark_level=110.0, bias_level=20.0, dark_exp=30.0)
    cal = CalibrationMasters.load(dark_path=d, bias_path=b, scale_dark_to_light=True)
    assert cal.bias_nodata_mask is None


def test_dark_scaling_all_finite_master_is_unchanged_by_the_mask(tmp_path):
    # The common real case (an all-finite integer Seestar dark) keeps no mask and
    # is byte-for-byte identical to before the no-data-mask fix.
    d, b = _save_dark_and_bias(tmp_path, dark_level=110.0, bias_level=20.0, dark_exp=30.0)
    cal = CalibrationMasters.load(dark_path=d, bias_path=b, scale_dark_to_light=True)
    assert cal.dark_nodata_mask is None
    raw = np.full((4, 4), 200.0, dtype=np.float32)
    np.testing.assert_allclose(cal.apply_raw(raw, light_exposure_s=10.0), 150.0)


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


def test_build_master_reports_how_many_frames_the_user_actually_gave(tmp_path):
    """A big dark set is evenly sampled down to the memory bound before
    combining — a sound default that used to live only in the log, so someone who
    dropped 200 darks read "built from 64 frames" and reasonably concluded 136
    had failed. The meta now carries the supplied count so the caller can say it.
    """
    paths = []
    for i in range(9):
        p = tmp_path / f"dark_{i:02d}.fits"
        _write_raw(p, np.full((4, 4), 100.0 + i))
        paths.append(p)

    # Sampled: more frames supplied than the bound allows.
    _, meta = build_master(paths, kind="dark", method="median", max_frames=4)
    assert meta.n_supplied == 9
    assert meta.n_frames == 4      # what was actually combined
    assert meta.n_supplied > meta.n_frames  # the case worth telling the user

    # Not sampled: the two agree, so a caller can tell "nothing was dropped"
    # from the numbers alone rather than needing a separate flag.
    _, small = build_master(paths[:3], kind="dark", method="median", max_frames=4)
    assert small.n_supplied == small.n_frames == 3


def test_master_meta_supplied_count_is_build_time_only(tmp_path):
    """It is not part of a master's identity, so it isn't written to the FITS
    header — a master loaded back reports None rather than a number it can't
    stand behind, and every existing header keeps exactly the cards it had."""
    from seestack.calibrate.masters import load_master, save_master

    path = tmp_path / "dark.fits"
    save_master(path, np.zeros((4, 4), dtype=np.float32),
                MasterMeta("dark", 4, 4, 4, "median", n_supplied=200))
    _, meta = load_master(path)
    assert meta.n_frames == 4
    assert meta.n_supplied is None


# --- Bayer-phase guards on the masters ------------------------------------
#
# Masters are applied to the *raw Bayer mosaic*, so a master built on a different
# CFA phase lines its red photosites up with the lights' green ones. Harmless for
# a pedestal (a dark/bias corrects each physical pixel), fatal for a flat (which
# divides per colour). Before these, ``validate`` compared only ``arr.shape`` and
# the phase was never read at all.


def _rggb_flat(tmp_path, name, pattern):
    """A 4×4 master flat whose two Bayer colours want different corrections.

    Columns alternate 200/100, i.e. exactly the pattern a CFA phase error swaps:
    apply the wrong phase and every "200" photosite gets the "100" correction.
    """
    flat = np.tile(np.array([200.0, 100.0, 200.0, 100.0], dtype=np.float32), (4, 1))
    save_master(tmp_path / name, flat,
                MasterMeta("flat", 10, 4, 4, "median", bayer_pattern=pattern))
    return str(tmp_path / name)


def test_validate_refuses_a_flat_from_a_different_bayer_phase(tmp_path):
    cal = CalibrationMasters.load(flat_path=_rggb_flat(tmp_path, "f.fits", "GRBG"))
    assert cal.flat_bayer_pattern == "GRBG"
    with pytest.raises(ValueError, match="colour-filter layout"):
        cal.validate((4, 4), "RGGB")


def test_validate_accepts_a_flat_on_the_same_bayer_phase(tmp_path):
    cal = CalibrationMasters.load(flat_path=_rggb_flat(tmp_path, "f.fits", "rggb "))
    # Case and whitespace are header noise, not a different sensor.
    cal.validate((4, 4), "RGGB")


def test_validate_bayer_guard_needs_both_sides_to_declare_a_phase(tmp_path):
    # The whole upgrade-safety of the guard: it can only fire on a *positive*
    # conflict. A master built before the phase was stamped, a target whose
    # frames never recorded one, a caller that doesn't pass it, and an
    # unrecognised card all keep working exactly as they did.
    unstamped = CalibrationMasters.load(
        flat_path=_rggb_flat(tmp_path, "plain.fits", None))
    assert unstamped.flat_bayer_pattern is None
    unstamped.validate((4, 4), "RGGB")

    stamped = CalibrationMasters.load(flat_path=_rggb_flat(tmp_path, "f.fits", "GRBG"))
    stamped.validate((4, 4))          # caller passes nothing — old signature
    stamped.validate((4, 4), None)    # target never recorded a phase
    stamped.validate((4, 4), "MONO")  # not one of the four real CFA phases


def test_validate_bayer_guard_ignores_a_dark_and_a_bias(tmp_path):
    # A pedestal corrects each physical pixel, so its phase is irrelevant — it
    # must not fail the stack (it earns an advisory instead, below).
    dark = np.zeros((4, 4), dtype=np.float32)
    bias = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", bayer_pattern="GRBG"))
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 0, 4, 4, "mean", bayer_pattern="BGGR"))
    CalibrationMasters.load(dark_path=str(tmp_path / "d.fits")).validate((4, 4), "RGGB")
    CalibrationMasters.load(bias_path=str(tmp_path / "b.fits")).validate((4, 4), "RGGB")


def test_wrong_phase_flat_really_would_swap_the_corrections(tmp_path):
    # The measurement behind the guard: it is not a provenance nicety. With the
    # flat one phase out, the two Bayer colours get each other's correction, so a
    # uniform raw frame comes out with a 2× colour split instead of flat.
    path = _rggb_flat(tmp_path, "f.fits", "GRBG")
    cal = CalibrationMasters.load(flat_path=path)
    raw = np.full((4, 4), 1000.0, dtype=np.float32)
    right = cal.apply_raw(raw)
    # Simulate the phase error by rolling the flat one pixel across the mosaic.
    cal.flat_norm = np.roll(cal.flat_norm, 1, axis=1)
    wrong = cal.apply_raw(raw)
    assert not np.allclose(right, wrong)
    assert wrong[0, 0] / wrong[0, 1] == pytest.approx(right[0, 1] / right[0, 0])


def test_calibration_warns_but_does_not_fail_on_a_dark_phase_mismatch(tmp_path):
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=10.0,
                           bayer_pattern="BGGR"))
    cal = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"))
    (warn,) = cal.calibration_warnings(light_exposure_s=10.0,
                                       light_bayer_pattern="RGGB")
    assert "BGGR" in warn and "RGGB" in warn
    assert "still subtracted" in warn
    # Matching phases, and either side undeclared, stay silent.
    assert cal.calibration_warnings(10.0, None, "BGGR") == []
    assert cal.calibration_warnings(10.0, None, None) == []


def test_calibration_warns_on_a_bias_phase_mismatch_only_when_it_applies(tmp_path):
    # A bias is subtracted from the lights only when no dark is set; with a dark
    # present it never touches a pixel, so it must not earn a warning either.
    bias = np.zeros((4, 4), dtype=np.float32)
    dark = np.zeros((4, 4), dtype=np.float32)
    save_master(tmp_path / "b.fits", bias,
                MasterMeta("bias", 0, 4, 4, "mean", bayer_pattern="BGGR"))
    save_master(tmp_path / "d.fits", dark,
                MasterMeta("dark", 5, 4, 4, "mean", exposure_s=10.0))
    bias_only = CalibrationMasters.load(bias_path=str(tmp_path / "b.fits"))
    (warn,) = bias_only.calibration_warnings(None, None, "RGGB")
    assert "Master bias" in warn
    with_dark = CalibrationMasters.load(dark_path=str(tmp_path / "d.fits"),
                                        bias_path=str(tmp_path / "b.fits"))
    assert with_dark.calibration_warnings(10.0, None, "RGGB") == []
