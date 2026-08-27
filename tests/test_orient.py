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


# ---- pixel-grid geometry (what the Sky map has to follow) -----------------

@pytest.mark.parametrize("angle", [0.0, 90.0, 180.0, 270.0, -90.0, 90.4])
def test_pixel_transform_is_exact_for_the_lossless_snap(angle):
    """For a snapped (``np.rot90``) rotation the described mapping is *exact*:
    every rotated pixel maps back to the original pixel it was copied from.

    The Sky map derives a rotated preview's WCS from this mapping, so a
    half-pixel — or a flipped-axis — error there would place the picture wrong on
    the sky. Pinned against the rotation itself rather than re-derived."""
    from seestack.render.orient import north_up_pixel_transform

    h, w = 27, 41
    idx = np.arange(h * w, dtype=np.float32).reshape(h, w)
    img = np.repeat(idx[:, :, None], 3, axis=2)
    out = rotate_image_north_up(img, angle)

    m, t, new_w, new_h = north_up_pixel_transform(w, h, angle)
    assert (new_h, new_w) == out.shape[:2]
    for oy in range(new_h):
        for ox in range(new_w):
            src = m @ np.array([ox, oy]) + t
            py, px = divmod(int(round(float(out[oy, ox, 0]))), w)
            assert abs(src[0] - px) < 1e-6
            assert abs(src[1] - py) < 1e-6


@pytest.mark.parametrize("angle", [30.0, 47.0, 123.0, -37.0])
def test_pixel_transform_follows_the_resampled_rotation(angle):
    """For an off-axis (PIL, ``expand=True``) rotation the mapping is exact to
    within the nearest-neighbour rounding — i.e. no systematic offset. The
    half-pixel corner/centre convention PIL rotates on is the trap here."""
    from seestack.render.orient import north_up_pixel_transform

    h, w = 27, 41
    idx = np.arange(h * w, dtype=np.float32).reshape(h, w)
    from PIL import Image
    out = np.asarray(Image.fromarray(idx, mode="F").rotate(
        angle, resample=Image.NEAREST, expand=True, fillcolor=-1.0))

    m, t, new_w, new_h = north_up_pixel_transform(w, h, angle)
    assert (new_h, new_w) == out.shape
    errs = []
    for oy in range(new_h):
        for ox in range(new_w):
            if out[oy, ox] < 0:
                continue                      # exposed corner, no source pixel
            src = m @ np.array([ox, oy]) + t
            py, px = divmod(int(round(float(out[oy, ox]))), w)
            errs.append((src[0] - px, src[1] - py))
    err = np.asarray(errs)
    assert len(err) > 100
    assert np.abs(err).max() <= 0.5 + 1e-9    # pure rounding, no bias
    assert abs(err[:, 0].mean()) < 0.05
    assert abs(err[:, 1].mean()) < 0.05


def test_pixel_transform_rejects_a_degenerate_size():
    from seestack.render.orient import north_up_pixel_transform

    assert north_up_pixel_transform(0, 10, 90.0) is None
    assert north_up_pixel_transform(10, -1, 90.0) is None


@pytest.mark.parametrize("angle", [90.0, 180.0, 270.0, 30.0, -37.0])
def test_rotate_mask_follows_the_picture_it_belongs_to(angle):
    """A coverage mask rotated by :func:`rotate_mask_north_up` lands on exactly
    the pixels the same rotation of the *picture* puts the covered region on.

    This is the Sky-map overlay bug in one assertion: the alpha footprint comes
    off the un-rotated FITS, so it has to make the same journey as the preview or
    an irregular mosaic's transparency ends up somewhere the picture isn't."""
    from seestack.render.orient import rotate_mask_north_up

    h, w = 30, 20
    mask = np.zeros((h, w), dtype=bool)       # an L-shaped (irregular) footprint
    mask[:20, :12] = True
    mask[20:, :6] = True

    img = np.zeros((h, w, 3), np.float32)
    img[mask] = 1.0
    rotated_img = rotate_image_north_up(img, angle)
    rotated_mask = rotate_mask_north_up(mask, angle)

    assert rotated_mask.shape == rotated_img.shape[:2]
    disagree = rotated_mask != (rotated_img[:, :, 0] > 0.5)
    # Off-axis rotations resample, so allow a thin boundary discrepancy; the
    # bug this guards against misplaces ~half the pixels.
    assert disagree.mean() < 0.03


def test_rotate_mask_is_a_hard_bit_mask_and_fills_corners_uncovered():
    from seestack.render.orient import rotate_mask_north_up

    mask = np.ones((24, 24), dtype=bool)
    out = rotate_mask_north_up(mask, 30.0)
    assert out.dtype == np.bool_
    assert out.shape[0] > 24 and out.shape[1] > 24
    assert not out[0, 0]                       # exposed corner = uncovered
    assert out[out.shape[0] // 2, out.shape[1] // 2]


def test_rotate_mask_rejects_a_non_2d_mask():
    from seestack.render.orient import rotate_mask_north_up

    with pytest.raises(ValueError, match="2-D"):
        rotate_mask_north_up(np.ones((4, 4, 3), dtype=bool), 90.0)


def test_applied_north_up_deg_matches_what_the_render_does(tmp_path):
    """The one answer to "how much did the North-up render actually turn this?" —
    0.0 for no WCS / a sub-threshold tilt, the snapped angle otherwise. Anything
    that records the rotation reads it here so it can't drift from the renderer."""
    from astropy.io import fits

    from seestack.render.thumbnail import applied_north_up_deg

    h, w = 40, 60
    cube = np.zeros((3, h, w), dtype=np.float32)
    plain = tmp_path / "plain.fits"
    fits.PrimaryHDU(data=cube).writeto(plain, overwrite=True)
    assert applied_north_up_deg(plain) == 0.0          # no WCS → no rotation

    # ``_make_wcs(180)`` is the already-North-up canvas for this convention, so
    # 179.0 is the "close enough, don't resample" case and the rest are real tilts.
    for rot, expect in ((179.0, 0.0), (30.0, None), (89.6, None)):
        wcs = _make_wcs(rot, w, h)
        hdr = wcs.to_header()
        p = tmp_path / f"r{rot}.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(p, overwrite=True)
        applied = applied_north_up_deg(p)
        raw = north_up_rotation_deg(wcs, w, h)
        if expect is not None:
            assert applied == expect
        else:
            # Whatever the renderer applies, the recorded angle rotates the
            # picture to the identical pixels.
            img = np.zeros((h, w, 3), np.float32)
            img[7, 11] = 1.0
            assert np.array_equal(rotate_image_north_up(img, raw),
                                  rotate_image_north_up(img, applied))
