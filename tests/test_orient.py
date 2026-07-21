"""North-up orientation: derive the rotation from an image's own WCS and apply it.

The rotation *sign* is the one thing that must be exactly right (a wrong sign
rotates the picture the wrong way). We pin it end-to-end using ``astropy`` itself
as ground truth: place a bright marker at the true-North sky position (via the
WCS, independent of our helper), rotate by the angle the helper returns, and
assert the marker lands at the top-centre of the output.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("PIL")

from astropy.wcs import WCS  # noqa: E402

from seestack.render.orient import (  # noqa: E402
    NORTH_UP_MIN_DEG,
    north_up_rotation_deg,
    rotate_image_north_up,
)


def _make_wcs(rot_deg: float, w: int, h: int, cdelt: float = 0.001) -> WCS:
    """A celestial TAN WCS rotated by ``rot_deg`` with RA increasing to the left
    (the celestial parity), so the tests exercise the real handedness."""
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(w - 1) / 2 + 1, (h - 1) / 2 + 1]  # 1-based CRPIX
    wcs.wcs.crval = [150.0, 20.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    th = np.radians(rot_deg)
    wcs.wcs.cd = np.array([[-cdelt * np.cos(th), cdelt * np.sin(th)],
                           [cdelt * np.sin(th), cdelt * np.cos(th)]])
    return wcs


@pytest.mark.parametrize("rot", [0, 10, 30, -30, 45, 90, 120, 170, -120])
def test_rotation_brings_true_north_to_the_top(rot):
    w = h = 101
    wcs = _make_wcs(rot, w, h)
    beta = north_up_rotation_deg(wcs, w, h)
    assert beta is not None

    # Ground truth (astropy, NOT our helper): the pixel of a point due North.
    cx, cy = (w - 1) / 2, (h - 1) / 2
    ra0, dec0 = (float(v) for v in wcs.all_pix2world(cx, cy, 0))
    nx, ny = (float(v) for v in wcs.all_world2pix(ra0, dec0 + 0.03, 0))
    img = np.zeros((h, w, 3), np.float32)
    img[int(round(ny)), int(round(nx))] = 1.0

    out = rotate_image_north_up(img, beta)
    oy, ox = np.unravel_index(int(np.argmax(out[..., 0])), out[..., 0].shape)
    H, W = out.shape[:2]
    # North marker now sits near the top edge, horizontally centred.
    assert oy < H * 0.35
    assert abs(ox - (W - 1) / 2) < W * 0.15


def test_no_wcs_or_degenerate_returns_none():
    assert north_up_rotation_deg(None, 100, 100) is None
    assert north_up_rotation_deg(_make_wcs(0, 100, 100), 0, 100) is None


def test_orthogonal_angle_is_lossless_rot90():
    # A 90° correction snaps to an exact np.rot90 — no resample, no black corners,
    # dimensions swapped, pixels preserved exactly.
    rng = np.random.default_rng(0)
    img = rng.uniform(0, 1, size=(20, 30, 3)).astype(np.float32)
    out = rotate_image_north_up(img, 90.0)
    assert out.shape == (30, 20, 3)
    assert np.array_equal(out, np.rot90(img, k=1))
    # And it stays lossless when the angle is within the snap tolerance of 90°.
    near = rotate_image_north_up(img, 90.4)
    assert np.array_equal(near, np.rot90(img, k=1))


def test_zero_angle_snaps_to_identity():
    rng = np.random.default_rng(1)
    img = rng.uniform(0, 1, size=(16, 16, 3)).astype(np.float32)
    assert np.array_equal(rotate_image_north_up(img, 0.0), img)


def test_off_axis_rotate_expands_and_fills_corners_black():
    # A 30° rotate expands the canvas and the freshly-exposed corners are black
    # (the same value uncovered/NaN pixels render as) — not white or garbage.
    img = np.ones((40, 40, 3), np.float32)
    out = rotate_image_north_up(img, 30.0)
    assert out.shape[0] > 40 and out.shape[1] > 40
    assert out[0, 0].max() < 0.05          # a corner is black
    assert out[out.shape[0] // 2, out.shape[1] // 2].min() > 0.9  # centre preserved


def test_min_deg_threshold_is_a_sensible_small_angle():
    # The "already close enough" floor is a couple of degrees — small enough to
    # still fix a visibly-tilted frame, large enough to skip pointless resampling.
    assert 1.0 <= NORTH_UP_MIN_DEG <= 5.0
