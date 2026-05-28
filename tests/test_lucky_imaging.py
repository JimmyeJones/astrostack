"""Lucky imaging: keep only top X% of frames by FWHM."""

import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.io.project import FrameRow, Project
from seestack.stack.stacker import StackOptions, run_stack
from tests.synth import make_synth_wcs_text, write_seestar_fits


def test_lucky_filter_keeps_only_top_fraction(tmp_path):
    proj = Project.create(tmp_path / "p", name="lucky")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    # Build 10 frames with FWHMs from 2.0 (sharpest) to 4.7 (worst).
    fwhms = [2.0, 2.2, 2.5, 2.8, 3.0, 3.3, 3.7, 4.0, 4.3, 4.7]
    for i, fwhm in enumerate(fwhms):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True, seed=10 + i, n_stars=30)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            fwhm_px=fwhm,
        ))
    try:
        # Keep top 30% = 3 sharpest frames.
        result = run_stack(
            proj,
            StackOptions(
                sigma_clip=False,
                background_flatten=False,
                lucky_fraction=0.3,
                max_workers=2,
                output_name="lucky30",
            ),
        )
    finally:
        proj.close()
    assert result.n_frames_used == 3


def test_lucky_fraction_one_keeps_all(tmp_path):
    proj = Project.create(tmp_path / "p", name="all")
    wcs_text = make_synth_wcs_text()
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(4):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True, seed=20 + i, n_stars=20)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=83.6, dec_center_deg=-5.4,
            fwhm_px=3.0,
        ))
    try:
        result = run_stack(
            proj,
            StackOptions(
                sigma_clip=False, background_flatten=False, lucky_fraction=1.0,
                max_workers=2, output_name="all",
            ),
        )
    finally:
        proj.close()
    assert result.n_frames_used == 4
