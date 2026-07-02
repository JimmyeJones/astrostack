"""Drizzle path — accumulator construction, single-frame and multi-frame stacking."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("drizzle")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.io.wcs_io import wcs_from_text  # noqa: E402
from seestack.stack.drizzle_path import DrizzleParams, DrizzleStacker  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def test_drizzle_canvas_scaling():
    """Drizzle output canvas should be ``ref_shape * scale``."""
    wcs = wcs_from_text(make_synth_wcs_text(width=480, height=320))
    drz = DrizzleStacker(wcs, (320, 480), DrizzleParams(scale=2.0, pixfrac=1.0))
    assert drz.output_canvas_shape == (640, 960)


def test_drizzle_single_frame_round_trip():
    """Adding one frame at scale=1, pixfrac=1: output should match input data."""
    wcs = wcs_from_text(make_synth_wcs_text(width=120, height=80))
    drz = DrizzleStacker(wcs, (80, 120), DrizzleParams(scale=1.0, pixfrac=1.0))
    rng = np.random.default_rng(0)
    rgb = rng.random((80, 120, 3), dtype=np.float32) * 1000 + 500
    drz.add_frame(rgb, wcs)
    result = drz.result()
    assert result.shape == (80, 120, 3)
    # Interior pixels should approximate the input (drizzle averages the
    # contributions; with one frame at unit weight, output ≈ input).
    interior = result[5:-5, 5:-5, :]
    in_interior = rgb[5:-5, 5:-5, :]
    np.testing.assert_allclose(interior, in_interior, rtol=0.1, atol=20.0)


def test_drizzle_conserves_surface_brightness_multiframe():
    """Stacking N identical frames at scale=1, pixfrac=1 must return the input
    brightness, not N× dimmer.

    Regression guard for the flux-scale bug: ``result()`` used to divide the
    already-averaged ``out_img`` by ``out_wht`` (≈ N), so the mean of N frames
    came out ~N× too faint. With N=6 that was a 6× error.
    """
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    rgb = np.full((80, 100, 3), 500.0, dtype=np.float32)
    n = 6
    for _ in range(n):
        drz.add_frame(rgb, wcs)
    result = drz.result()
    interior = result[5:-5, 5:-5, :]
    # Mean of N identical frames is still ~500, regardless of N.
    assert np.nanmedian(interior) == pytest.approx(500.0, rel=0.02)
    # Coverage (accumulated weight) grows with frame count — it is *not* the
    # image normaliser.
    cov = drz.coverage[5:-5, 5:-5, :]
    assert np.nanmedian(cov) == pytest.approx(float(n), rel=0.05)


def _build_project(tmp_path, n: int = 4) -> Project:
    proj = Project.create(tmp_path / "p", name="drizzle_test")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n):
        path = write_seestar_fits(
            raws / f"f{i}.fit",
            add_wcs=True, seed=20 + i, n_stars=20,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text,
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def test_drizzle_pipeline_e2e(tmp_path):
    proj = _build_project(tmp_path, n=4)
    try:
        result = run_stack(
            proj,
            StackOptions(
                drizzle=True,
                drizzle_pixfrac=0.8,
                drizzle_scale=1.5,
                background_flatten=False,  # cleaner numerical comparison
                max_workers=2,
                output_name="driz",
            ),
        )
    finally:
        proj.close()

    assert result.fits_path.exists()
    assert result.tiff_path.exists()
    assert result.preview_path.exists()
    # Drizzle output canvas is ref * scale.
    expected_h = int(round(320 * 1.5))
    expected_w = int(round(480 * 1.5))
    assert result.canvas_shape == (expected_h, expected_w)


def test_drizzle_super_resolution_increases_canvas(tmp_path):
    proj = _build_project(tmp_path, n=3)
    try:
        result = run_stack(
            proj,
            StackOptions(
                drizzle=True, drizzle_scale=2.0, drizzle_pixfrac=0.7,
                background_flatten=False, max_workers=1,
                output_name="superres",
            ),
        )
    finally:
        proj.close()
    # 2× scale: canvas is 2× per side.
    assert result.canvas_shape == (640, 960)


def test_drizzle_context_array_disabled():
    """The context bitmask must stay off — it costs a full-canvas int32 plane
    per 32 frames (re-copied on every growth), which is tens of GB and
    quadratic copying on a multi-thousand-frame stack."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    rgb = np.full((80, 100, 3), 500.0, dtype=np.float32)
    for _ in range(3):
        drz.add_frame(rgb, wcs)
    for d in drz._drizzlers:
        assert d.out_ctx is None


def test_drizzle_nan_input_pixels_carry_zero_weight():
    """A NaN (no-data) input pixel must not be injected as a 0.0 sample — it
    should contribute nothing, leaving the output NaN when nothing else lands."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    rgb = np.full((80, 100, 3), 500.0, dtype=np.float32)
    rgb[30:40, 40:50, :] = np.nan
    drz.add_frame(rgb, wcs)
    result = drz.result()
    # The NaN block never received data: it must stay NaN, not become 0.
    assert np.all(np.isnan(result[32:38, 42:48, :]))
    # Covered interior pixels keep their value.
    assert np.nanmedian(result[5:25, 5:35, :]) == pytest.approx(500.0, rel=0.02)


def test_drizzle_honors_per_frame_weight():
    """Per-frame quality weights must scale contributions: mean of value 100 at
    weight 1 and value 200 at weight 3 is 175 (not the unweighted 150)."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    drz.add_frame(np.full((80, 100, 3), 100.0, dtype=np.float32), wcs, weight=1.0)
    drz.add_frame(np.full((80, 100, 3), 200.0, dtype=np.float32), wcs, weight=3.0)
    result = drz.result()
    assert np.nanmedian(result[5:-5, 5:-5, :]) == pytest.approx(175.0, rel=0.01)


def _poke_hot_pixel(path, x: int, y: int, value: int = 60000) -> None:
    """Write a static hot pixel into an on-disk synth FITS mosaic."""
    from astropy.io import fits

    with fits.open(path, mode="update") as hdul:
        hdul[0].data[y, x] = value
        hdul.flush()


def test_drizzle_suppresses_hot_pixels(tmp_path):
    """`suppress_hot_pixels` (default on) must apply on the drizzle path too —
    it used to be silently ignored, so static hot pixels survived into the
    drizzled output as bright speckles."""
    from astropy.io import fits

    hot_x, hot_y = 200, 150  # even/even → R site in RGGB, away from the edges
    results = {}
    for suppress in (True, False):
        proj = _build_project(tmp_path / f"sup_{suppress}", n=3)
        try:
            for f in proj.iter_frames():
                _poke_hot_pixel(f.cached_path, hot_x, hot_y)
            result = run_stack(
                proj,
                StackOptions(
                    drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
                    suppress_hot_pixels=suppress,
                    background_flatten=False, max_workers=1,
                    output_name="hot",
                ),
            )
            with fits.open(result.fits_path) as hdul:
                results[suppress] = np.asarray(hdul[0].data, dtype=np.float32)
        finally:
            proj.close()

    # FITS layout is (3, H, W); R channel is index 0. Bilinear debayer spreads
    # the 60000 ADU spike into a 3×3 halo before the 3×3 median filter runs, so
    # (exactly like the standard path) the spike is knocked down to halo level
    # rather than fully erased — assert the filter ran, not perfection.
    r_off = results[False][0]
    r_on = results[True][0]
    assert r_off[hot_y, hot_x] > 30000.0, "hot pixel should survive with suppression off"
    assert r_on[hot_y, hot_x] < 0.6 * r_off[hot_y, hot_x], (
        "hot pixel should be suppressed on the drizzle path too"
    )
