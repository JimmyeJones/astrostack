"""Reference frame selection."""

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.reference import pick_reference_frame  # noqa: E402


def test_no_solved_frames_returns_none(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(FrameRow(source_path="a.fit"))  # no wcs
        assert pick_reference_frame(proj) is None
    finally:
        proj.close()


def test_picks_frame_near_median(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Three frames, two clustered at (10, 20), one outlier at (15, 25).
        proj.add_frame(FrameRow(
            source_path="a.fit", wcs_json="x",
            ra_center_deg=10.0, dec_center_deg=20.0, fwhm_px=3.0,
        ))
        proj.add_frame(FrameRow(
            source_path="b.fit", wcs_json="x",
            ra_center_deg=10.05, dec_center_deg=20.05, fwhm_px=2.5,
        ))
        proj.add_frame(FrameRow(
            source_path="c.fit", wcs_json="x",
            ra_center_deg=15.0, dec_center_deg=25.0, fwhm_px=2.0,
        ))
        choice = pick_reference_frame(proj)
        assert choice is not None
        # Should pick one of the clustered ones (median is between 10 and 10.05),
        # not the outlier — outlier is far from the median.
        assert choice.frame.ra_center_deg < 12
        assert choice.n_candidates == 3
    finally:
        proj.close()


def test_tiebreak_by_fwhm(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Three frames at the same position but different FWHM. Should pick
        # the sharpest.
        ids = []
        for fwhm in (3.0, 2.0, 4.0):
            ids.append(proj.add_frame(FrameRow(
                source_path=f"f{fwhm}.fit", wcs_json="x",
                ra_center_deg=10.0, dec_center_deg=20.0, fwhm_px=fwhm,
            )))
        choice = pick_reference_frame(proj)
        assert choice is not None
        assert choice.frame.fwhm_px == 2.0
    finally:
        proj.close()


def test_skips_rejected_frames(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(FrameRow(
            source_path="bad.fit", wcs_json="x",
            ra_center_deg=10.0, dec_center_deg=20.0,
            accept=False,
        ))
        proj.add_frame(FrameRow(
            source_path="good.fit", wcs_json="x",
            ra_center_deg=11.0, dec_center_deg=21.0,
        ))
        choice = pick_reference_frame(proj)
        assert choice is not None
        assert choice.frame.source_path == "good.fit"
    finally:
        proj.close()
