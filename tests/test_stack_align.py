"""Per-frame align: load → debayer → windowed reproject."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")

from seestack.stack.align import align_one  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def test_align_identity_returns_data(tmp_path):
    """Aligning a frame to its own WCS should return ~the same image, and the
    window should cover essentially the whole canvas."""
    p = write_seestar_fits(tmp_path / "x.fit", add_wcs=True, n_stars=20, seed=1)
    wcs_text = make_synth_wcs_text()
    result = align_one(
        str(p), bayer_pattern="RGGB",
        src_wcs_text=wcs_text, dst_wcs_text=wcs_text,
        dst_shape=(320, 480),
    )
    assert result is not None
    win_rgb, win_valid, y0, x0 = result
    # Identity reproject onto a same-size canvas → window ≈ whole canvas
    # minus the ~8 px frame-edge inset we now apply on every side.
    assert win_rgb.shape[2] == 3
    assert win_rgb.shape[0] >= 290 and win_rgb.shape[1] >= 450
    assert y0 <= 12 and x0 <= 12
    # Most window pixels valid.
    assert win_valid.mean() > 0.9
    # Interior is finite.
    interior = win_rgb[20:-20, 20:-20, :]
    assert np.isfinite(interior).all()


def test_align_offset_canvas_returns_none_or_tiny_overlap(tmp_path):
    """Aligning to a WCS far-shifted in RA → footprint barely (or never)
    intersects the canvas. The windowed path returns either None (no overlap)
    or a tiny window with almost no valid pixels."""
    p = write_seestar_fits(tmp_path / "x.fit", add_wcs=True, n_stars=10, seed=2)
    src_wcs = make_synth_wcs_text()
    # 5"/px × 480px ≈ 0.67° wide, so a 2° offset is well outside the frame.
    dst_wcs = make_synth_wcs_text(ra_center_deg=83.6 + 2.0)
    result = align_one(
        str(p), bayer_pattern="RGGB",
        src_wcs_text=src_wcs, dst_wcs_text=dst_wcs,
        dst_shape=(320, 480),
    )
    if result is None:
        return  # no intersection at all — the expected common case here
    win_rgb, win_valid, y0, x0 = result
    assert win_valid.mean() < 0.05


def test_align_returns_none_when_footprint_off_canvas(tmp_path):
    """A wildly offset destination → frame doesn't touch the canvas → None."""
    p = write_seestar_fits(tmp_path / "x.fit", add_wcs=True, n_stars=10, seed=3)
    src_wcs = make_synth_wcs_text()
    dst_wcs = make_synth_wcs_text(ra_center_deg=83.6 + 20.0)  # 20° away
    result = align_one(
        str(p), bayer_pattern="RGGB",
        src_wcs_text=src_wcs, dst_wcs_text=dst_wcs,
        dst_shape=(320, 480),
    )
    assert result is None
