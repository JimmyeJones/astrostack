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


def test_drizzle_frame_coverage_counts_frames_not_weight_sum():
    """``frame_coverage`` must be an integer *frame count*, independent of the
    per-frame quality weight — unlike ``coverage`` (out_wht), which is Σ of the
    weighted footprint overlap and understates the count once weights ≠ 1."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    rgb = np.full((80, 100, 3), 500.0, dtype=np.float32)
    n = 4
    for _ in range(n):
        drz.add_frame(rgb, wcs, weight=0.25)  # heavily down-weighted frames
    # coverage (Σ weights) collapses to ~n×0.25 = 1.0 — it is *not* a frame count.
    cov = drz.coverage[5:-5, 5:-5, :]
    assert np.nanmedian(cov) == pytest.approx(float(n) * 0.25, rel=0.05)
    # frame_coverage counts the frames honestly: 4 per interior pixel.
    fc = drz.frame_coverage
    assert fc is not None
    assert fc.dtype == np.uint32
    assert fc.shape == (80, 100)
    assert int(fc[5:-5, 5:-5].max()) == n
    assert int(np.median(fc[5:-5, 5:-5])) == n


def test_drizzle_frame_coverage_unweighted_matches_coverage():
    """At unit weight (the default), the interior frame count equals both N and
    the integer coverage — so an unweighted drizzle stack is unaffected by the
    frame-count switch (parity with the standard weighted-sum path)."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    rgb = np.full((80, 100, 3), 500.0, dtype=np.float32)
    n = 5
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    for _ in range(n):
        drz.add_frame(rgb, wcs)
    fc = drz.frame_coverage
    cov0 = drz.coverage[..., 0]
    assert int(fc[10:-10, 10:-10].max()) == n
    # Byte-for-byte with the rounded coverage where every weight is 1.0.
    np.testing.assert_array_equal(fc[10:-10, 10:-10], np.rint(cov0[10:-10, 10:-10]))


def test_drizzle_frame_coverage_skips_uncovered_and_nan_pixels():
    """A frame must only bump the count where it actually deposited signal — not
    a NaN (no-data) block, and not where it never landed."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    a = np.full((80, 100, 3), 500.0, dtype=np.float32)
    a[30:40, 40:50, :] = np.nan  # this frame has a hole here
    b = np.full((80, 100, 3), 500.0, dtype=np.float32)  # this one is full
    drz.add_frame(a, wcs)
    drz.add_frame(b, wcs)
    fc = drz.frame_coverage
    # The hole in frame ``a`` means those pixels only got frame ``b`` → count 1.
    assert int(fc[32:38, 42:48].max()) == 1
    # A pixel both frames covered counts 2.
    assert int(fc[5:25, 5:35].min()) == 2


def test_add_frame_reports_off_canvas_frames_as_not_aligned():
    """``add_frame`` must return True when the frame's footprint intersects the
    canvas and False when it lies entirely off-canvas — the drizzle analogue of
    ``align_one`` returning ``None``. Without this the drizzle path counts a
    stray sub from a different pointing (which deposits nothing) as a *used*
    frame, inflating ``n_frames_used`` / hiding the align failure, and lets a
    wholly off-canvas batch slip past the ``n_used == 0`` guard and write an
    all-NaN image to disk."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    drz = DrizzleStacker(wcs, (80, 100), DrizzleParams(scale=1.0, pixfrac=1.0))
    on = np.full((80, 100, 3), 500.0, dtype=np.float32)
    # Same WCS → the frame lands fully on the canvas.
    assert drz.add_frame(on, wcs) is True

    # A WCS pointing ~10° away reprojects entirely off this ~0.14°-wide canvas.
    far = wcs_from_text(make_synth_wcs_text(width=100, height=80, ra_center_deg=93.6))
    off = np.full((80, 100, 3), 500.0, dtype=np.float32)
    assert drz.add_frame(off, far) is False
    # The off-canvas frame deposited nothing: only the on-canvas frame counted.
    fc = drz.frame_coverage
    assert fc is not None
    assert int(fc.max()) == 1


def test_drizzle_does_not_count_an_off_canvas_stray_frame(tmp_path):
    """End-to-end: a stray sub from a different pointing reprojects entirely off
    the reference canvas and deposits nothing, so the drizzle path must report it
    as an align failure (``n_align_failed``), not inflate ``n_frames_used``.

    Regression for the drizzle-only frame-accounting bug: the standard path skips
    a non-intersecting frame via ``align_one`` → ``None``, but the drizzle path
    did ``used += 1`` whenever ``add_frame`` didn't raise — and an off-canvas
    frame builds an all-zero weight map and returns cleanly, so it was counted."""
    proj = _build_project(tmp_path, n=5)
    # A sixth frame ~10° away — a different target accidentally dropped in the
    # same incoming folder. Its centre is far from the on-target median, so it is
    # never picked as the reference; it reprojects off the reference-frame canvas.
    raws = tmp_path / "raws"
    stray = write_seestar_fits(
        raws / "stray.fit", add_wcs=True, seed=99, n_stars=20,
        ra_center_deg=93.6, dec_center_deg=-5.4,
    )
    proj.add_frame(FrameRow(
        source_path=str(stray), cached_path=str(stray),
        width_px=480, height_px=320, bayer_pattern="RGGB",
        wcs_json=make_synth_wcs_text(ra_center_deg=93.6, dec_center_deg=-5.4),
        ra_center_deg=93.6, dec_center_deg=-5.4,
    ))
    try:
        result = run_stack(
            proj,
            StackOptions(
                drizzle=True, drizzle_scale=1.5, drizzle_pixfrac=0.8,
                background_flatten=False, max_workers=1,
                # Force the reference-frame canvas so the stray is genuinely
                # off-canvas (a union canvas would just grow to include it).
                mosaic_canvas="reference",
                output_name="stray",
            ),
        )
    finally:
        proj.close()
    # Only the 5 on-target subs aligned; the stray is an honest align failure.
    assert result.n_offered == 6
    assert result.n_frames_used == 5
    assert result.n_align_failed == 1


def test_drizzle_stats_accumulator_tracks_frame_count_to_gate_rejection():
    """The statistics accumulator (rejection pass 1) tracks the unweighted frame
    count: the reject gate keys on the true frame count, not the pixfrac-deflated
    weight sum, so it must be available in stats mode (see
    ``drizzle_path.clip_reference``)."""
    wcs = wcs_from_text(make_synth_wcs_text(width=60, height=40))
    stats = DrizzleStacker(
        wcs, (40, 60), DrizzleParams(scale=1.0, pixfrac=1.0), compute_stats=True
    )
    stats.add_frame(np.full((40, 60, 3), 100.0, dtype=np.float32), wcs)
    assert stats.frame_coverage is not None
    assert stats.frame_coverage[20, 30] == 1


def test_drizzle_quality_weighted_reports_frame_count_not_weight_sum(tmp_path):
    """End-to-end: a quality-weighted drizzle run must persist coverage_max as
    the true frame count, not the (smaller) sum of per-frame weights."""
    proj = Project.create(tmp_path / "p", name="driz_qw")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    n = 4
    for i in range(n):
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=30 + i, n_stars=20,
        )
        # Spread the FWHM so quality weighting demotes the softer frames well
        # below 1.0 (so Σweights < n, which is what used to understate coverage).
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            fwhm_px=2.0 + 1.5 * i, star_count=200 - 20 * i,
        ))
    try:
        result = run_stack(
            proj,
            StackOptions(
                drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
                quality_weighted=True,
                background_flatten=False, max_workers=1,
                output_name="driz_qw",
            ),
        )
    finally:
        proj.close()
    # All four frames fully overlap, so the honest peak coverage is n; the old
    # Σweights peak would be < n (the down-weighted frames contribute < 1 each).
    assert result.coverage_max == n


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


def test_drizzle_reject_keeps_a_bright_flat_region(tmp_path):
    """A bright, flat region (a near-saturated star core / smooth bright nebula)
    must survive the two-pass drizzle rejection — it must NOT be punched into a
    NaN coverage hole.

    Regression guard for the float32 catastrophic-cancellation bug in
    ``clip_reference``: the clip variance is ``m2 − m²`` of two large float32
    ~counts² operands. At ~5.5e4 counts, m² ≈ 3e9 where float32's ULP (~360)
    dwarfs a true per-frame variance of ~1e2, so the variance underflowed to 0,
    the tolerance collapsed to 0, and in pass 2 *every* real contribution failed
    ``|value − mean| > 0`` → zero weight → ``out_wht == 0`` → the fully-covered
    bright pixel came back NaN. The fix disables rejection where the variance is
    below the float32 resolution of m² (it's unrecoverable noise, not a real
    spread), so the region is kept instead of holed.
    """
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    params = DrizzleParams(scale=1.0, pixfrac=1.0)
    rng = np.random.default_rng(7)
    n = 8
    # A very bright, flat field with a small, genuine per-pixel frame-to-frame
    # spread (σ ≈ 10 counts) — well within noise, far below ULP(m²) at 5.5e4.
    frames = [
        (55000.0 + rng.normal(0.0, 10.0, (80, 100, 3))).astype(np.float32)
        for _ in range(n)
    ]

    # Mirror the stacker's two-pass reject flow: pass 1 builds the statistics,
    # pass 2 re-drizzles clipping against them.
    stats = DrizzleStacker(wcs, (80, 100), params, compute_stats=True)
    for f in frames:
        stats.add_frame(f, wcs)
    clip = stats.clip_reference(kappa=3.0)
    mean_ref, tol_ref = clip
    # The bright interior must be flagged unresolvable → tol = +inf (never
    # reject), not the collapsed-to-0 tolerance the bug produced.
    assert np.all(np.isinf(tol_ref[10:-10, 10:-10, :])), (
        "bright flat region should disable rejection, not clip against ~0 tol"
    )

    drz = DrizzleStacker(wcs, (80, 100), params)
    for f in frames:
        drz.add_frame(f, wcs, clip=clip)
    result = drz.result()
    interior = result[10:-10, 10:-10, :]
    # The bug made this entirely NaN (every contribution rejected). It must stay
    # covered and near the true brightness.
    assert np.isfinite(interior).all(), "bright flat region was punched into a NaN hole"
    assert np.nanmedian(interior) == pytest.approx(55000.0, rel=0.01)


def test_drizzle_reject_still_clips_a_real_outlier_at_normal_brightness(tmp_path):
    """The variance-reliability floor must not disable *legitimate* rejection on
    normal-brightness data: a genuine bright outlier in one frame is still clipped
    (the floor only trips where the spread is unresolvable float32 noise, which a
    real outlier at ~500 counts is not)."""
    wcs = wcs_from_text(make_synth_wcs_text(width=100, height=80))
    params = DrizzleParams(scale=1.0, pixfrac=1.0)
    # Enough frames that a single-pass κ=3 clip can actually fire — the largest
    # possible z-score of a point against statistics that include it is
    # (n−1)/√n, which only clears κ=3 for n ≳ 11.
    n = 16
    base = 500.0
    frames = [np.full((80, 100, 3), base, dtype=np.float32) for _ in range(n)]
    # One frame carries a big cosmic-ray-like spike over an interior block.
    frames[3][30:50, 30:50, :] = 8000.0

    stats = DrizzleStacker(wcs, (80, 100), params, compute_stats=True)
    for f in frames:
        stats.add_frame(f, wcs)
    clip = stats.clip_reference(kappa=3.0)

    drz = DrizzleStacker(wcs, (80, 100), params)
    for f in frames:
        drz.add_frame(f, wcs, clip=clip)
    result = drz.result()
    # The spike was rejected: the block reads ~500 (the good frames' value), not
    # pulled up toward 8000, and it stays covered (not NaN).
    block = result[32:48, 32:48, :]
    assert np.isfinite(block).all()
    assert np.nanmedian(block) == pytest.approx(base, abs=5.0)
    # And rejection actually fired (the tally saw non-zero drops).
    _, n_rej = drz.rejection_counts()
    assert n_rej > 0
