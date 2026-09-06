"""Sensor defect map: find the broken photosites, repair only those.

The point of the feature is *precision* — a hot pixel is fixed, a star is not
touched — so most of these tests are about what the map must NOT flag.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.calibrate.apply import CalibrationMasters
from seestack.calibrate.defects import (
    DefectMap,
    build_defect_map,
    census_sensor_defects,
    find_sensor_defects,
)
from seestack.calibrate.masters import MasterMeta, save_master


def _synthetic_dark(h: int = 120, w: int = 160, seed: int = 7) -> np.ndarray:
    """A believable master dark: bias pedestal + corner amp glow + read noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    dark = 500.0 + 60.0 * np.exp(-((yy - h) ** 2 + xx ** 2) / (2 * 40.0 ** 2))
    dark += rng.normal(0.0, 3.0, dark.shape)
    return dark.astype(np.float32)


# ---- find_sensor_defects -------------------------------------------------


def test_finds_hot_and_dead_pixels_and_nothing_else():
    dark = _synthetic_dark()
    hot = [(10, 20), (11, 21), (55, 90)]
    dead = (100, 5)
    for y, x in hot:
        dark[y, x] += 900.0
    dark[dead] = 0.0

    mask = find_sensor_defects(dark)

    assert mask.shape == dark.shape and mask.dtype == bool
    for y, x in [*hot, dead]:
        assert mask[y, x], f"missed the defect at {(y, x)}"
    assert int(mask.sum()) == 4, (
        f"flagged {int(mask.sum())} pixels, expected exactly the 4 planted ones "
        f"at {sorted(zip(*np.nonzero(mask), strict=True))}"
    )


def test_amp_glow_and_read_noise_alone_flag_nothing():
    """The whole risk is a threshold that latches onto structure."""
    assert int(find_sensor_defects(_synthetic_dark()).sum()) == 0


def _shot_noise_dark(glow_e: float, *, h: int = 480, w: int = 640,
                     n_darks: int = 20, read_e: float = 6.0,
                     seed: int = 3) -> np.ndarray:
    """A master dark whose **noise is not stationary**, which is the case
    ``_synthetic_dark`` above cannot make.

    That one adds read noise of one fixed sigma everywhere, so its amp glow is a
    change of *level* only. A real master dark's glow is dark **current**, and
    dark current carries shot noise — so the glow corner is genuinely grainier
    than the rest of the sensor, by √(dark current). This builds the master the
    way the camera does: mean of ``n_darks`` frames, each Poisson in the dark
    current plus Gaussian read noise. Nothing here is broken; every photosite is
    healthy by construction.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    dc = 20.0 + glow_e * np.exp(-(yy ** 2 + xx ** 2) / (2 * 60.0 ** 2))
    frames = [500.0 + rng.poisson(dc).astype(np.float64)
              + rng.normal(0.0, read_e, dc.shape) for _ in range(n_darks)]
    return np.mean(frames, axis=0).astype(np.float32)


_GLOW_SPOTS = [(3, 5), (9, 11), (21, 33), (45, 7), (15, 25), (31, 19),
               (200, 300), (210, 310), (250, 350), (260, 360), (300, 400), (310, 410)]
#: Half of ``_GLOW_SPOTS`` sit inside the glow corner, half out on the quiet bulk.


@pytest.mark.parametrize("glow_e", [0.0, 200.0, 2000.0])
def test_a_healthy_sensor_under_amp_glow_shot_noise_flags_nothing(glow_e):
    """The v0.371.1 bug, and the reason the scale is now measured locally.

    The threshold was ``DEFECT_SIGMA`` × the MAD of the residual over the
    **whole** plane. A glow corner is a small fraction of the sensor, so that
    number is set by the quiet bulk — and the bar it sets sits below the glow's
    own grain. **Fails before at 2,000 e⁻: 133 healthy photosites flagged**,
    every one of them inside the glow, each then overwritten from its neighbours on
    *every* sub of *every* stack, and reported to the owner as broken pixels in
    their camera. There is nothing broken in this sensor, so the only correct
    answer is zero."""
    assert int(find_sensor_defects(_shot_noise_dark(glow_e)).sum()) == 0


@pytest.mark.parametrize("glow_e", [0.0, 200.0, 2000.0])
def test_real_defects_inside_the_glow_are_still_found(glow_e):
    """The other half: raising the bar where the sensor is noisy must not blind
    the map where the sensor is genuinely *broken*."""
    dark = _shot_noise_dark(glow_e)
    for y, x in _GLOW_SPOTS:
        dark[y, x] += 400.0

    mask = find_sensor_defects(dark)

    missed = [p for p in _GLOW_SPOTS if not mask[p]]
    assert not missed, f"missed {len(missed)} planted defects: {missed}"
    assert int(mask.sum()) == len(_GLOW_SPOTS), (
        f"flagged {int(mask.sum())} pixels, expected exactly the "
        f"{len(_GLOW_SPOTS)} planted ones")


def test_a_glow_that_nearly_saturates_the_well_is_much_better_but_not_perfect():
    """Stated rather than hidden: 20,000 e⁻ of dark current in the corner means
    amp glow alone is filling most of the sensor's well in one sub, which is a
    master (and a night) nobody can use — well outside the regime this feature
    is for. The fix is a large improvement there rather than a cure: **1,576
    pixels flagged before — 1,564 of them healthy — against ~121 after**, with
    every planted defect still found either way.

    It is not pushed further because the residual at that slope is dominated by
    the local median *lagging the curvature*, not by noise, and the only knob
    that would absorb it — a higher percentile in ``_local_robust_scale`` — is
    the one that breaks the ``MAX_DEFECT_FRACTION`` refusal above (at P90 a
    master with a tenth of the sensor spiked stops being refused and starts
    being repaired). Losing that guard to chase an unusable master is the wrong
    trade, so this pins the improvement instead of pretending it is a cure."""
    dark = _shot_noise_dark(20_000.0)
    for y, x in _GLOW_SPOTS:
        dark[y, x] += 400.0

    mask = find_sensor_defects(dark)

    missed = [p for p in _GLOW_SPOTS if not mask[p]]
    assert not missed, f"missed {len(missed)} planted defects: {missed}"
    # Was 1,576 (12 real + 1,564 healthy) before the local scale; an order of
    # magnitude is the guarantee, not an exact count.
    assert int(mask.sum()) < 200, (
        f"flagged {int(mask.sum())} pixels — the local-scale fix has regressed")


def test_the_local_scale_never_lowers_the_bar_a_clean_master_is_judged_against():
    """The upgrade guarantee, stated as an invariant rather than a diff: the
    threshold is the *larger* of the plane-wide spread and the local one, so the
    map this version returns is a subset of what the previous one returned. No
    photosite that used to be left alone can start being repaired — which is
    what makes this safe to ship onto a live install mid-library.

    Checked on an ordinary stationary master, where the two agree: the local
    term must not perturb today's answer either way."""
    from seestack.calibrate.defects import _local_robust_scale, _robust_scale

    rng = np.random.default_rng(19)
    plane = rng.normal(0.0, 4.0, (200, 240)).astype(np.float32)
    glob = _robust_scale(plane)
    local = _local_robust_scale(plane)

    assert glob == pytest.approx(4.0, rel=0.05)
    # The block estimator is calibrated to the same sigma on stationary noise —
    # if it drifted, every clean master's threshold would quietly move.
    assert float(np.median(local)) == pytest.approx(glob, rel=0.10)
    # And it is a *floor* raised, never lowered: max() is what the caller takes.
    assert float(np.maximum(glob, local).min()) >= glob


def test_a_cfa_pattern_in_the_dark_is_not_read_as_defects():
    """Each phase is measured against its own plane, so a per-phase offset — a
    real thing on some sensors — must not flag every pixel of two phases."""
    dark = _synthetic_dark()
    dark[0::2, 1::2] += 25.0  # one CFA phase sits higher than the others
    dark[1::2, 0::2] += 25.0
    assert int(find_sensor_defects(dark).sum()) == 0


def test_a_gradient_is_not_read_as_defects():
    h, w = 100, 100
    yy, xx = np.mgrid[0:h, 0:w]
    dark = (400.0 + 2.0 * yy + 1.0 * xx).astype(np.float32)
    dark += np.random.default_rng(3).normal(0.0, 2.0, dark.shape)
    assert int(find_sensor_defects(dark).sum()) == 0


def test_refuses_a_map_that_covers_too_much_of_the_sensor():
    """A master that isn't one (a light frame, a broken build) produces a huge
    candidate set — repairing that many pixels would be worse than the defects,
    so the whole map is dropped."""
    rng = np.random.default_rng(11)
    dark = _synthetic_dark()
    # 10% of the sensor spiked: way past any credible defect population.
    n = dark.size // 10
    ys = rng.integers(0, dark.shape[0], n)
    xs = rng.integers(0, dark.shape[1], n)
    dark[ys, xs] += 900.0
    assert int(find_sensor_defects(dark).sum()) == 0
    # …and the ceiling is what did it: raise it and the same master maps.
    assert find_sensor_defects(dark, max_fraction=0.5).any()


def test_a_no_data_master_pixel_is_never_a_defect():
    """A sanitized-to-0 master pixel means "no information", not "broken
    sensor" — repairing there would overwrite the light's own good sample."""
    dark = _synthetic_dark()
    nodata = np.zeros(dark.shape, dtype=bool)
    nodata[40, 40] = True
    dark[40, 40] = 0.0  # what _sanitize_pedestal leaves behind

    assert find_sensor_defects(dark)[40, 40], "precondition: reads as stuck-low"
    assert not find_sensor_defects(dark, exclude=nodata)[40, 40]
    assert int(find_sensor_defects(dark, exclude=nodata).sum()) == 0


def test_a_patch_of_no_data_inside_the_amp_glow_flags_nothing():
    """Regression (v0.369.4): the no-data guard held for one lone pixel in a flat
    part of the frame and leaked everywhere else.

    Every no-data sample used to be filled with the **whole plane's** median
    before the local median was taken. In the corner the amp glow lives in, that
    value is nothing like the local level, so the fill (a) read as a defect at
    its own sample and (b) dragged the 5×5 local median of the *real* photosites
    beside it, flagging a rosette of perfectly good pixels around the hole. Both
    halves overwrite the light frame's own good samples on every sub — the exact
    harm ``exclude`` exists to prevent."""
    h, w = 120, 160
    dark = _synthetic_dark(h, w)
    # A hole sitting in the glow, wide enough to fill part of a 5×5 phase window.
    nodata = np.zeros(dark.shape, dtype=bool)
    nodata[h - 12:h - 4, 4:12] = True
    dark[nodata] = 0.0  # what _sanitize_pedestal leaves behind

    leaked = find_sensor_defects(dark)          # precondition: the hole reads hot/dead
    assert leaked[nodata].any()
    mask = find_sensor_defects(dark, exclude=nodata)
    assert not mask[nodata].any(), "a no-data sample can never be a defect"
    assert int(mask.sum()) == 0, "and it must not drag its neighbours in either"


def test_a_no_data_hole_does_not_hide_a_real_defect_next_to_it():
    """The other direction: neutralising the hole must not blind the map. A hot
    pixel elsewhere in the frame is still found, and so is one right beside the
    hole — the fill is locally flat, so it neither raises nor lowers the bar."""
    h, w = 120, 160
    dark = _synthetic_dark(h, w)
    nodata = np.zeros(dark.shape, dtype=bool)
    nodata[h - 12:h - 4, 4:12] = True
    dark[nodata] = 0.0
    far, near = (30, 100), (h - 14, 6)   # same CFA phase as the hole's corner
    dark[far] += 900.0
    dark[near] += 900.0

    mask = find_sensor_defects(dark, exclude=nodata)
    assert mask[far] and mask[near]
    assert int(mask.sum()) == 2


def test_a_master_with_no_data_anywhere_is_measured_exactly_as_before():
    """The fill only runs when there is something to fill, so an ordinary master
    — every install's case — takes a bit-identical path."""
    dark = _synthetic_dark()
    dark[10, 20] += 900.0
    empty = np.zeros(dark.shape, dtype=bool)
    plain = find_sensor_defects(dark)
    assert np.array_equal(plain, find_sensor_defects(dark, exclude=empty))
    assert np.array_equal(plain, find_sensor_defects(dark, exclude=None))
    assert plain[10, 20] and int(plain.sum()) == 1


def test_degenerate_inputs_return_an_empty_mask_rather_than_raising():
    assert find_sensor_defects(np.zeros((0, 0), dtype=np.float32)).size == 0
    assert not find_sensor_defects(np.zeros((4, 4, 3), dtype=np.float32)).any()
    assert not find_sensor_defects(_synthetic_dark(), sigma=0.0).any()
    # A 1-px-wide frame has no same-phase neighbourhood to be an outlier in.
    assert not find_sensor_defects(np.array([[1.0, 900.0]], dtype=np.float32)).any()


# ---- DefectMap.repair ----------------------------------------------------


def test_repair_replaces_only_the_defects_with_a_same_colour_median():
    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dmap = build_defect_map(dark)
    assert dmap is not None and dmap.n_defects == 1

    # A light whose CFA phases sit at very different levels, so a repair that
    # medianed across colours would land visibly wrong.
    light = np.zeros((120, 160), dtype=np.float32)
    light[0::2, 0::2] = 100.0
    light[0::2, 1::2] = 300.0
    light[1::2, 0::2] = 300.0
    light[1::2, 1::2] = 700.0
    light[30, 30] = 9999.0
    before = light.copy()

    n = dmap.repair(light)

    assert n == 1
    assert light[30, 30] == pytest.approx(100.0), "repaired across the CFA"
    untouched = np.ones(light.shape, dtype=bool)
    untouched[30, 30] = False
    assert np.array_equal(light[untouched], before[untouched])


def test_a_star_is_never_touched_however_bright_it_is():
    """The headline claim over the blind post-debayer filter: the map is measured
    on the *dark*, so a star peak — which exists only in the light — is not in it
    and cannot be repaired away, at any brightness."""
    dark = _synthetic_dark()
    dark[30, 30] += 900.0  # one genuine hot photosite
    dmap = build_defect_map(dark)
    assert dmap is not None

    light = np.full(dark.shape, 100.0, dtype=np.float32)
    # A tight, very bright star core — exactly what a 3×3 local-median outlier
    # filter mistakes for a hot pixel.
    light[70, 80] = 60000.0
    light[70, 81] = 30000.0
    light[71, 80] = 30000.0
    light[30, 30] = 9999.0
    dmap.repair(light)

    assert light[70, 80] == 60000.0
    assert light[70, 81] == 30000.0
    assert light[71, 80] == 30000.0
    assert light[30, 30] == pytest.approx(100.0)


def test_repair_ignores_neighbours_that_are_themselves_broken():
    mask = np.zeros((20, 20), dtype=bool)
    mask[10, 10] = True
    mask[10, 12] = True  # a same-phase neighbour, also broken
    dmap = DefectMap.from_mask(mask)
    assert dmap is not None

    light = np.full((20, 20), 50.0, dtype=np.float32)
    light[10, 10] = 9999.0
    light[10, 12] = 9999.0
    assert dmap.repair(light) == 2
    assert light[10, 10] == pytest.approx(50.0)
    assert light[10, 12] == pytest.approx(50.0)


def test_a_defect_with_no_usable_neighbour_is_left_alone():
    """Better a known-broken value than a made-up one."""
    mask = np.ones((2, 2), dtype=bool)  # every same-phase neighbour is broken
    dmap = DefectMap.from_mask(mask)
    assert dmap is not None
    light = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    assert dmap.repair(light) == 0
    assert np.array_equal(light, [[1.0, 2.0], [3.0, 4.0]])


def test_repair_is_a_no_op_on_a_mismatched_shape():
    dmap = DefectMap.from_mask(np.eye(8, dtype=bool))
    assert dmap is not None
    other = np.ones((4, 4), dtype=np.float32)
    assert dmap.repair(other) == 0
    assert np.array_equal(other, np.ones((4, 4)))


def test_build_defect_map_returns_none_when_there_is_nothing_to_do():
    assert build_defect_map(None) is None
    assert build_defect_map(_synthetic_dark()) is None
    assert DefectMap.from_mask(np.zeros((8, 8), dtype=bool)) is None


# ---- census_sensor_defects (the reporting answer) -------------------------


def test_the_census_counts_exactly_what_the_map_would_repair():
    dark = _synthetic_dark()
    for y, x in ((10, 20), (11, 21), (55, 90)):
        dark[y, x] += 900.0
    dark[100, 5] = 0.0

    census = census_sensor_defects(dark)

    assert census.measurable and not census.refused
    assert census.n_defects == int(find_sensor_defects(dark).sum()) == 4
    assert census.n_pixels == dark.size
    assert census.fraction == pytest.approx(4 / dark.size)


def test_a_clean_sensor_is_measurable_and_empty_not_silent():
    """"Nothing is broken" and "we couldn't look" are different answers — the
    whole reason this exists beside ``find_sensor_defects``, which collapses
    them."""
    census = census_sensor_defects(_synthetic_dark())
    assert census.measurable and census.n_defects == 0 and not census.refused


def test_a_refused_map_still_reports_how_many_candidates_there_were():
    """``find_sensor_defects`` returns an empty mask above the ceiling, which
    reads identically to a healthy sensor. The census keeps them apart, so a
    screen can say *why* no repair will happen."""
    rng = np.random.default_rng(3)
    dark = _synthetic_dark()
    idx = rng.choice(dark.size, size=int(0.05 * dark.size), replace=False)
    dark.flat[idx] += 900.0

    census = census_sensor_defects(dark)

    assert census.refused and census.measurable
    assert census.n_defects > 0.02 * dark.size
    # Fail-before for the distinction: the repair path still declines.
    assert not find_sensor_defects(dark).any()


def test_degenerate_censuses_say_nothing_was_measured_rather_than_raising():
    for bad in (None, np.zeros((0, 0), dtype=np.float32),
                np.zeros((4, 4, 3), dtype=np.float32)):
        census = census_sensor_defects(bad)
        assert not census.measurable
        assert census.n_defects == 0 and census.n_pixels == 0
        assert census.fraction == 0.0


def test_the_census_of_a_raw_master_equals_the_map_the_stack_builds(tmp_path):
    """One definition, not two. The stack sanitizes the master's non-finite
    pixels to 0 and passes their positions as ``exclude``; the census is handed
    the array *as loaded*, NaNs and all, and its own ``isfinite`` test selects
    the identical set. If those two ever diverge, the number on screen stops
    being the number a run repairs."""
    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dark[31, 33] += 900.0
    # A no-data patch, the case where the two paths could differ.
    dark[60:66, 60:66] = np.nan
    dark_path = _write_master(tmp_path, "dark.fits", dark)

    masters = CalibrationMasters.load(dark_path, repair_sensor_defects=True)
    census = census_sensor_defects(np.asarray(dark, dtype=np.float32))

    assert masters.n_sensor_defects == 2
    assert census.n_defects == masters.n_sensor_defects
    assert census.n_pixels == dark.size


# ---- CalibrationMasters wiring -------------------------------------------


def _write_master(tmp_path, name, data, kind="dark", **meta_kw):
    path = tmp_path / name
    h, w = data.shape
    save_master(path, data, MasterMeta(kind=kind, n_frames=10, width_px=w,
                                       height_px=h, method="median", **meta_kw))
    return str(path)


def test_off_by_default_nothing_is_measured_and_no_pixel_moves(tmp_path):
    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dark_path = _write_master(tmp_path, "dark.fits", dark)

    masters = CalibrationMasters.load(dark_path)
    assert masters.defects is None
    assert masters.n_sensor_defects == 0

    light = np.full(dark.shape, 1000.0, dtype=np.float32)
    light[30, 30] = 9999.0
    out = masters.apply_raw(light)
    # The dark subtraction still happens; the defect is *not* repaired, which is
    # exactly today's behaviour.
    assert out[30, 30] == pytest.approx(9999.0 - dark[30, 30], abs=1e-3)


def test_opted_in_the_defect_is_repaired_in_the_raw_bayer_domain(tmp_path):
    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dark_path = _write_master(tmp_path, "dark.fits", dark)

    masters = CalibrationMasters.load(dark_path, repair_sensor_defects=True)
    assert masters.n_sensor_defects == 1
    assert masters.defects is not None and masters.defects.mask[30, 30]

    light = np.full(dark.shape, 1000.0, dtype=np.float32)
    light[30, 30] = 9999.0
    out = masters.apply_raw(light)

    neighbours = [out[30 + dy, 30 + dx]
                  for dy in (-2, 0, 2) for dx in (-2, 0, 2)
                  if (dy, dx) != (0, 0)]
    assert out[30, 30] == pytest.approx(float(np.median(neighbours)), abs=1e-3)
    # Fail-before check: without the repair the pixel keeps its 9000 ADU spike.
    unrepaired = CalibrationMasters.load(dark_path).apply_raw(light)
    assert unrepaired[30, 30] > 8000.0
    assert out[30, 30] < 600.0, "the spike survived the repair"


def test_the_light_frame_the_caller_passed_in_is_never_mutated(tmp_path):
    dark = _synthetic_dark()
    dark[30, 30] += 900.0
    dark_path = _write_master(tmp_path, "dark.fits", dark)
    masters = CalibrationMasters.load(dark_path, repair_sensor_defects=True)

    light = np.full(dark.shape, 1000.0, dtype=np.float32)
    light[30, 30] = 9999.0
    before = light.copy()
    masters.apply_raw(light)
    assert np.array_equal(light, before)


def test_a_bias_only_workflow_still_gets_a_map(tmp_path):
    bias = _synthetic_dark()
    bias[7, 9] += 900.0
    bias_path = _write_master(tmp_path, "bias.fits", bias, kind="bias")

    masters = CalibrationMasters.load(bias_path=bias_path,
                                      repair_sensor_defects=True)
    assert masters.n_sensor_defects == 1


def test_no_pedestal_master_means_no_map(tmp_path):
    """A flat says nothing about which photosites are broken."""
    flat = np.full((40, 40), 1000.0, dtype=np.float32)
    flat_path = _write_master(tmp_path, "flat.fits", flat, kind="flat")
    masters = CalibrationMasters.load(flat_path=flat_path,
                                      repair_sensor_defects=True)
    assert masters.defects is None


# ---- end to end through run_stack ----------------------------------------


def test_a_run_stamps_how_many_photosites_it_repaired(tmp_path):
    """The whole chain: StackOptions → CalibrationMasters → the master FITS's
    DEFECTPX card, which is what the run Info panel reads. Off by default, so a
    run that didn't ask stamps nothing."""
    pytest.importorskip("astropy")
    pytest.importorskip("photutils")
    from astropy.io import fits as _fits

    from seestack.io.project import FrameRow, Project
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    def _project(name):
        proj = Project.create(tmp_path / name, name=name)
        for tag in ("a", "b"):
            fp = write_seestar_fits(tmp_path / f"{name}-{tag}.fit", add_wcs=True,
                                    n_stars=25, seed=20, ra_center_deg=83.6)
            proj.add_frame(FrameRow(
                id=None, source_path=str(fp), cached_path=str(fp),
                wcs_json=make_synth_wcs_text(ra_center_deg=83.6),
                width_px=480, height_px=320, bayer_pattern="RGGB", accept=True,
                ra_center_deg=83.6, dec_center_deg=-5.4,
            ))
        return proj

    # A believable dark for the 320×480 raw mosaic, with three broken photosites.
    dark = _synthetic_dark(320, 480)
    for y, x in ((100, 200), (101, 201), (7, 9)):
        dark[y, x] += 900.0
    dark_path = tmp_path / "dark.fit"
    hdu = _fits.PrimaryHDU(data=dark)
    hdu.header["EXPTIME"] = 30.0
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.writeto(dark_path, overwrite=True)

    def _header(repair):
        proj = _project(f"repair-{repair}")
        try:
            result = run_stack(proj, StackOptions(
                sigma_clip=False, background_flatten=False,
                dark_path=str(dark_path), repair_sensor_defects=repair))
        finally:
            proj.close()
        with _fits.open(result.fits_path) as hdul:
            return dict(hdul[0].header)

    assert _header(True)["DEFECTPX"] == 3
    # Fail-before: today's default run stamps no such card at all.
    assert "DEFECTPX" not in _header(False)
