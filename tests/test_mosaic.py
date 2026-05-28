"""Mosaic output-canvas computation."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow
from seestack.io.wcs_io import wcs_from_text
from seestack.stack.mosaic import compute_mosaic_canvas
from tests.synth import make_synth_wcs_text


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


def test_oversized_canvas_raises():
    """A frame flung across the sky (bad solve) should be caught, not OOM.

    15° away at 5"/px ≈ 10 800 px — still finite under TAN projection but well
    past a 4000 px limit.
    """
    frames = [_frame(10.0, 10.0), _frame(10.0, 10.0), _frame(25.0, 10.0)]
    with pytest.raises(ValueError, match="exceeding"):
        compute_mosaic_canvas(frames, reference_shape=(320, 480), max_canvas_px=4000)
