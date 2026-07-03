"""Mosaic output-canvas computation."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow
from seestack.io.wcs_io import wcs_from_text
from seestack.stack.mosaic import (
    _circ_mean_ra_deg,
    _footprint_outlier_indices,
    compute_mosaic_canvas,
)
from tests.synth import make_synth_wcs_text


def _fp(key, ra_c, dec_c=20.0, half=0.15):
    """A synthetic footprint (key, ra_corners, dec_corners) centred at (ra_c, dec_c)."""
    ra = np.array([ra_c - half, ra_c + half, ra_c + half, ra_c - half], float) % 360.0
    dec = np.array([dec_c - half, dec_c - half, dec_c + half, dec_c + half], float)
    return (key, ra, dec)


def test_circ_mean_ra_handles_the_zero_wrap():
    # Corners straddling 0° average to ~0°, not ~180° (the old median bug).
    m = _circ_mean_ra_deg(np.array([359.7, 0.3, 359.6, 0.4]))
    assert min(m, 360.0 - m) < 0.05
    # A normal (non-wrapping) footprint is unaffected.
    assert abs(_circ_mean_ra_deg(np.array([100.0, 100.5, 100.4, 100.1])) - 100.25) < 0.05


def test_ra_zero_straddling_frames_not_flagged_as_outliers():
    # A dithered cluster around RA≈0: frames whose footprints cross the 0°/360°
    # wrap must NOT be flagged as gross plate-solve outliers (they used to be,
    # via a median of corner RAs that sent them to ~180° → permanent rejection).
    foot = [_fp(i, ra_c) for i, ra_c in
            enumerate([359.6, 359.75, 359.9, 0.05, 0.2, 0.35])]
    outliers, _ = _footprint_outlier_indices(foot)
    assert outliers == set()


def test_genuine_far_solve_still_flagged_near_ra_zero():
    # The detector must still catch a real bad solve 90° from a near-RA=0 group.
    foot = [_fp(i, ra_c) for i, ra_c in enumerate([359.7, 359.85, 0.0, 0.15, 0.3])]
    foot.append(_fp(99, 90.0))
    outliers, _ = _footprint_outlier_indices(foot)
    assert 5 in outliers


def _frame(ra: float, dec: float, *, w: int = 480, h: int = 320,
           pixscale: float = 5.0) -> FrameRow:
    wcs_text = make_synth_wcs_text(
        width=w, height=h, ra_center_deg=ra, dec_center_deg=dec,
        pixscale_arcsec=pixscale,
    )
    return FrameRow(
        id=None, source_path=f"{ra}_{dec}.fit",
        width_px=w, height_px=h, bayer_pattern="RGGB",
        wcs_json=wcs_text, ra_center_deg=ra, dec_center_deg=dec,
        pixscale_arcsec=pixscale,
    )


def test_single_pointing_is_not_a_mosaic():
    """All frames at the same pointing → union ≈ reference, is_mosaic False."""
    frames = [_frame(83.6, -5.4) for _ in range(5)]
    canvas = compute_mosaic_canvas(frames, reference_shape=(320, 480))
    assert canvas is not None
    assert canvas.is_mosaic is False
    # Canvas should be within a few px of the reference frame.
    assert abs(canvas.shape[0] - 320) < 10
    assert abs(canvas.shape[1] - 480) < 10


def test_two_by_two_mosaic_canvas_covers_all_panels():
    """A 2×2 mosaic produces a canvas ~2× the reference in each dimension."""
    # Frame FOV at 5"/px, 480×320: width ≈ 480*5/3600 = 0.667°, height ≈ 0.444°.
    # Offset panels by ~0.5° so they tile with overlap.
    fov_w_deg = 480 * 5.0 / 3600.0
    fov_h_deg = 320 * 5.0 / 3600.0
    dx = fov_w_deg * 0.75  # 25% overlap
    dy = fov_h_deg * 0.75
    centers = [
        (100.0, 20.0),
        (100.0 + dx, 20.0),
        (100.0, 20.0 + dy),
        (100.0 + dx, 20.0 + dy),
    ]
    frames = []
    for ra, dec in centers:
        for _ in range(3):  # a few frames per panel
            frames.append(_frame(ra, dec))

    canvas = compute_mosaic_canvas(frames, reference_shape=(320, 480))
    assert canvas is not None
    assert canvas.is_mosaic is True
    assert canvas.n_footprints == 12
    # Canvas should be clearly bigger than one panel, but not more than ~2.2×.
    assert 480 * 1.4 < canvas.shape[1] < 480 * 2.3
    assert 320 * 1.4 < canvas.shape[0] < 320 * 2.3


def test_every_panel_corner_lands_inside_the_canvas():
    """The whole point: every frame's footprint must fit on the union canvas."""
    from seestack.io.wcs_io import footprint_radec_deg

    dx = 0.4
    centers = [(50.0, 10.0), (50.0 + dx, 10.0), (50.0 + 2 * dx, 10.0)]
    frames = [_frame(ra, dec) for ra, dec in centers]
    canvas = compute_mosaic_canvas(frames, reference_shape=(320, 480))
    assert canvas is not None

    canvas_wcs = wcs_from_text(canvas.wcs_text)
    h, w = canvas.shape
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    for f in frames:
        fwcs = wcs_from_text(f.wcs_json)
        corners = footprint_radec_deg(fwcs, f.width_px, f.height_px)
        sky = SkyCoord([c[0] for c in corners] * u.deg,
                       [c[1] for c in corners] * u.deg)
        xs, ys = canvas_wcs.world_to_pixel(sky)
        # Every corner must be inside [0, w) × [0, h) (with a small margin).
        assert np.all(xs >= -2) and np.all(xs <= w + 2)
        assert np.all(ys >= -2) and np.all(ys <= h + 2)


def test_no_usable_frames_returns_none():
    frames = [FrameRow(id=None, source_path="x.fit")]  # no WCS
    assert compute_mosaic_canvas(frames, reference_shape=(320, 480)) is None


def test_single_bad_solve_is_dropped():
    """One frame flung across the sky (bad solve) is dropped, not fatal.

    Four good frames + one 15° away (≈10 800 px at 5"/px). Rather than failing
    the whole stack, the outlier is excluded and the canvas covers the good
    cluster — well under the limit.
    """
    frames = [_frame(10.0, 10.0) for _ in range(4)] + [_frame(25.0, 10.0)]
    canvas = compute_mosaic_canvas(frames, reference_shape=(320, 480), max_canvas_px=4000)
    assert canvas is not None
    assert len(canvas.excluded_frame_ids) == 1   # the flung frame
    assert canvas.n_footprints == 4              # the good cluster
    assert canvas.shape[0] < 4000 and canvas.shape[1] < 4000


def test_scattered_bad_solves_dropped_before_sizing():
    """Many good frames + a few wildly-off solves → the bad ones are dropped up
    front (M_13 case: a tiny object whose canvas span was inflated to ~20°)."""
    frames = [_frame(50.0, 10.0) for _ in range(20)]
    frames.append(_frame(60.0, 10.0))   # ~10° off
    frames.append(_frame(50.0, 22.0))   # ~12° off
    canvas = compute_mosaic_canvas(frames, reference_shape=(320, 480))
    assert canvas is not None
    assert len(canvas.excluded_frame_ids) == 2     # only the two outliers
    assert canvas.n_footprints == 20
    assert canvas.span_deg < 1.0                    # back to ~one field


def test_legit_spread_mosaic_keeps_all_panels():
    """A real, evenly-spread mosaic isn't mistaken for outliers."""
    centers = [(100.0 + 0.4 * i, 20.0) for i in range(6)]  # 6 panels stepping in RA
    frames = [_frame(ra, dec) for ra, dec in centers for _ in range(3)]
    canvas = compute_mosaic_canvas(frames, reference_shape=(320, 480))
    assert canvas is not None
    assert canvas.excluded_frame_ids == []
    assert canvas.n_footprints == 18


def test_area_budget_raises_even_under_dimension_cap():
    """A canvas under the per-dimension cap but over the MP budget fails fast."""
    # Two clusters ~5° apart at 5"/px: ~3600 px each axis-ish but the product is
    # large; with a tiny MP budget it must raise (mentions the env var).
    frames = (
        [_frame(40.0, 10.0) for _ in range(6)]
        + [_frame(44.0, 14.0) for _ in range(6)]
    )
    with pytest.raises(ValueError, match="MEGAPIXELS|MP memory budget"):
        compute_mosaic_canvas(
            frames, reference_shape=(320, 480),
            max_canvas_px=100000, max_canvas_mp=0.5,
        )


def test_unsalvageable_canvas_raises():
    """If dropping outliers can't salvage it, raise — with web guidance.

    Three mutually-distant frames can't be brought under a 4000 px limit by
    dropping at most half, so it still raises. The message points at the web
    Frames table (there is no desktop "Footprints tab" here).
    """
    frames = [_frame(10.0, 10.0), _frame(25.0, 10.0), _frame(40.0, 10.0)]
    with pytest.raises(ValueError, match="Frames table"):
        compute_mosaic_canvas(frames, reference_shape=(320, 480), max_canvas_px=4000)
