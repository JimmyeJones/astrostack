"""Reference frame selection."""

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.reference import (  # noqa: E402
    pick_central_frame,
    pick_reference_frame,
)


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


def test_picks_central_frame_across_ra_zero_wrap(tmp_path):
    """A target imaged near RA=0h has frames straddling the 0°/360° boundary.
    The reference pick must not be fooled by the wrap: it should still choose the
    most-central, sharpest frame (RA 0.0, the lowest FWHM) — not an edge frame —
    and report a small span, not ~360°."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # True centre RA 0.0 (sharpest); edge frames on both sides of the wrap.
        frames = [
            ("center", 0.0, 2.0),
            ("e1", 359.85, 3.0),
            ("e2", 359.9, 3.0),
            ("e3", 0.1, 3.0),
            ("e4", 0.15, 3.0),
        ]
        for name, ra, fwhm in frames:
            proj.add_frame(FrameRow(
                source_path=f"{name}.fit", wcs_json="x",
                ra_center_deg=ra, dec_center_deg=20.0, fwhm_px=fwhm,
            ))
        choice = pick_reference_frame(proj)
        assert choice is not None
        # Before the wrap fix this picked an edge frame (RA 0.15, FWHM 3.0) and
        # reported span ~338°.
        assert choice.frame.source_path == "center.fit"
        assert choice.frame.ra_center_deg == 0.0
        assert choice.span_deg < 1.0
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


# --- pick_central_frame: the same rule, over an arbitrary subset ------------
# A mosaic panel picks its own sub-pixel-refine reference this way, so the rule
# has to hold on a list of frames rather than a whole project.


def test_central_frame_of_an_empty_list_is_none():
    assert pick_central_frame([]) is None


def test_central_frame_is_the_one_nearest_the_median_pointing():
    frames = [
        FrameRow(id=1, source_path="a.fit", ra_center_deg=10.0, dec_center_deg=20.0),
        FrameRow(id=2, source_path="b.fit", ra_center_deg=10.1, dec_center_deg=20.1),
        FrameRow(id=3, source_path="c.fit", ra_center_deg=10.2, dec_center_deg=20.2),
    ]
    assert pick_central_frame(frames).id == 2


def test_central_frame_breaks_ties_on_the_sharpest_frame():
    # Same pointing for all three — distance can't separate them, so the FWHM
    # tie-break decides (a frame with no measured FWHM goes last).
    frames = [
        FrameRow(id=1, source_path="a.fit", ra_center_deg=10.0, dec_center_deg=20.0),
        FrameRow(id=2, source_path="b.fit", ra_center_deg=10.0, dec_center_deg=20.0,
                 fwhm_px=4.0),
        FrameRow(id=3, source_path="c.fit", ra_center_deg=10.0, dec_center_deg=20.0,
                 fwhm_px=2.5),
    ]
    assert pick_central_frame(frames).id == 3


def test_central_frame_ignores_frames_with_no_pointing():
    # An unsolved frame has no centre to score, so it is skipped rather than
    # crashing the panel's reference choice.
    frames = [
        FrameRow(id=1, source_path="a.fit"),
        FrameRow(id=2, source_path="b.fit", ra_center_deg=10.0, dec_center_deg=20.0),
    ]
    assert pick_central_frame(frames).id == 2
    assert pick_central_frame([FrameRow(id=1, source_path="a.fit")]) is None


def test_central_frame_is_wrap_safe_across_ra_zero():
    # Frames straddling RA 0h: unwrapped, the median is ~359.95°, so the frame at
    # 0.0° is central. Without unwrapping the 359.9° frames read as ~360° away.
    frames = [
        FrameRow(id=1, source_path="a.fit", ra_center_deg=359.8, dec_center_deg=20.0),
        FrameRow(id=2, source_path="b.fit", ra_center_deg=359.9, dec_center_deg=20.0),
        FrameRow(id=3, source_path="c.fit", ra_center_deg=0.1, dec_center_deg=20.0),
    ]
    assert pick_central_frame(frames).id == 2
