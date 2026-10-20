"""The editor's "From your stars" numbers and Auto's sharpen radius are sized to
the star *on the master they edit*, not to QC's half-resolution measurement.

QC measures every frame's ``fwhm_px`` on ``green_channel`` — one pixel per 2×2
Bayer cell — while ``detail.sharpen.radius``, ``detail.deconvolve.psf_sigma``
and ``stars.reduce.size`` are master pixels (finer again on a drizzle, which
``auto_drizzle`` turns on by default). Fed straight across, every suggestion was
about half the star it aimed at (Scout 2026-10-20, sweep (1)).

The regression is end to end: real subs, the real QC pass, a real ``run_stack``
master (plain and ×1.5 drizzle), and the star FWHM measured on that master's own
full-resolution green plane as the truth each offered value must land within one
slider step of.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from astropy.io import fits  # noqa: E402

from seestack.edit.registry import param_spec  # noqa: E402
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.qc.metrics import (  # noqa: E402
    GREEN_CHANNEL_DECIMATION,
    compute_frame_metrics,
    detect_stars,
    estimate_sky,
    frame_fwhm_to_master_px,
    median_fwhm,
)
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402
from webapp.routers.editor import (  # noqa: E402
    master_fwhm_for_run,
    psf_sigma_for_fwhm,
    sharpen_radius_for_fwhm,
    star_size_for_fwhm,
)

W, H = 480, 320
DITHERED = [(i * 0.37, i * 0.53) for i in range(6)]


def test_frame_fwhm_to_master_px_scales_by_decimation_and_drizzle():
    assert GREEN_CHANNEL_DECIMATION == 2
    assert frame_fwhm_to_master_px(2.0) == pytest.approx(4.0)
    assert frame_fwhm_to_master_px(2.0, 1.5) == pytest.approx(6.0)
    # A missing/garbage scale changes nothing beyond the decimation.
    assert frame_fwhm_to_master_px(2.0, 0.0) == pytest.approx(4.0)


def test_master_fwhm_for_run_reads_the_runs_own_drizzle():
    class _Run:
        def __init__(self, options_json):
            self.options_json = options_json

    assert master_fwhm_for_run(None, _Run(None)) is None
    assert master_fwhm_for_run(0.0, _Run(None)) is None
    assert master_fwhm_for_run(2.0, None) == pytest.approx(4.0)
    assert master_fwhm_for_run(2.0, _Run(None)) == pytest.approx(4.0)
    assert master_fwhm_for_run(
        2.0, _Run('{"drizzle": false, "drizzle_scale": 2.0}')) == pytest.approx(4.0)
    assert master_fwhm_for_run(
        2.0, _Run('{"drizzle": true, "drizzle_scale": 1.5}')) == pytest.approx(6.0)


def _project(tmp_path) -> Project:
    proj = Project.create(tmp_path / "p", name="M_42")
    raws = tmp_path / "raws"
    raws.mkdir()
    for i, shift in enumerate(DITHERED):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True, seed=11,
                                  noise_seed=200 + i, n_stars=40,
                                  star_shift=shift)
        fid = proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB",
            wcs_json=make_synth_wcs_text(width=W, height=H, crpix_shift=shift),
            ra_center_deg=83.6, dec_center_deg=-5.4, exposure_s=10.0,
        ))
        # The real QC measurement, in its own (half-resolution) units.
        m = compute_frame_metrics(path, bayer_pattern="RGGB", detect_streaks=False)
        assert m.fwhm_px is not None
        proj.update_frame(fid, fwhm_px=m.fwhm_px, accept=True)
    return proj


def _master_green_fwhm(fits_path) -> float:
    """The star FWHM measured on the finished master's own full-res pixels."""
    with fits.open(fits_path) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float32)
    green = data[1] if data.ndim == 3 else data
    finite = green[np.isfinite(green)]
    green = np.where(np.isfinite(green), green, float(np.median(finite)))
    sky_med, sky_std = estimate_sky(green)
    sources = detect_stars(green, fwhm_guess_px=4.0, sky_median=sky_med,
                           sky_std=sky_std)
    fwhm = median_fwhm(green, sources, box_size=21)
    assert fwhm is not None
    return float(fwhm)


@pytest.mark.parametrize("drizzle", [False, True], ids=["plain", "drizzle1.5"])
def test_from_your_stars_matches_the_star_on_the_master(tmp_path, drizzle):
    """Fails before the fix: QC's ~2.1 px fed straight across offered star size
    2 against a ~4 px master star, radius 1.0 against 1.5 (2.0 drizzled)."""
    proj = _project(tmp_path)
    try:
        opts = dict(background_flatten=False, suppress_hot_pixels=False,
                    max_workers=2, output_name="out", auto_drizzle=False)
        if drizzle:
            opts.update(drizzle=True, drizzle_scale=1.5)
        res = run_stack(proj, StackOptions(**opts))
        run = next(iter(proj.iter_stack_runs()))
        truth = _master_green_fwhm(res.fits_path)
        offered = master_fwhm_for_run(proj.median_fwhm(), run)
    finally:
        proj.close()
    assert offered is not None
    for op, param, fn in (
        ("stars.reduce", "size", star_size_for_fwhm),
        ("detail.sharpen", "radius", sharpen_radius_for_fwhm),
        ("detail.deconvolve", "psf_sigma", psf_sigma_for_fwhm),
    ):
        step = param_spec(op, param).step
        assert abs(fn(offered) - fn(truth)) <= step + 1e-9, (
            op, fn(offered), fn(truth), offered, truth)
