"""Pure crop/size maths for the "Make it your wallpaper" export."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

from seestack.render.orient import rotate_image_north_up
from seestack.wallpaper import (
    WALLPAPER_PRESETS,
    png_size,
    render_wallpaper_jpeg,
    rotate_point_north_up,
    wallpaper_crop_box,
    wallpaper_target_pixel,
)


def _aspect(box):
    x0, y0, x1, y1 = box
    return (x1 - x0) / (y1 - y0)


def test_crop_box_phone_from_square_is_tall_and_narrow():
    # A ~square image cropped to a tall phone aspect → the tallest phone-shaped
    # rectangle fits full-height and narrow, centred horizontally.
    box = wallpaper_crop_box(1000, 1000, 1170, 2532)
    x0, y0, x1, y1 = box
    assert (y1 - y0) == 1000                        # full height (height-limited)
    assert (x1 - x0) < 1000                          # narrowed
    assert abs(_aspect(box) - 1170 / 2532) < 0.01    # exact target shape
    assert abs((x0 + x1) / 2 - 500) <= 1             # centred horizontally


def test_crop_box_desktop_from_square_is_wide():
    box = wallpaper_crop_box(1000, 1000, 1920, 1080)
    x0, y0, x1, y1 = box
    assert (x1 - x0) == 1000                         # full width (width-limited)
    assert (y1 - y0) < 1000
    assert abs(_aspect(box) - 1920 / 1080) < 0.01
    assert abs((y0 + y1) / 2 - 500) <= 1             # centred vertically


def test_crop_box_square_of_wide_image():
    box = wallpaper_crop_box(2000, 1000, 1, 1)
    x0, y0, x1, y1 = box
    assert (x1 - x0) == (y1 - y0) == 1000            # biggest square that fits
    assert abs((x0 + x1) / 2 - 1000) <= 1            # centred horizontally


def test_crop_box_centres_on_target():
    # Target above centre pulls the (full-height) phone crop's *x* toward it.
    box = wallpaper_crop_box(1000, 1000, 1170, 2532, target_px=(200.0, 500.0))
    x0, y0, x1, y1 = box
    cw = x1 - x0
    expected_x0 = max(0, round(200 - cw / 2))
    assert x0 == expected_x0


def test_crop_box_clamps_target_near_edge():
    # Target hard against the right edge → box slid fully inside, never past it,
    # keeping its full crop width.
    box = wallpaper_crop_box(1000, 1000, 1170, 2532, target_px=(9999.0, 500.0))
    x0, y0, x1, y1 = box
    cw = round(1000 * 1170 / 2532)                   # width-narrowed phone crop
    assert x1 <= 1000 and x0 >= 0
    assert (x1 - x0) == cw
    assert x1 == 1000                                # flush against the edge


def test_crop_box_nonfinite_target_falls_back_to_centre():
    centred = wallpaper_crop_box(1000, 1000, 1, 1)
    nan_box = wallpaper_crop_box(1000, 1000, 1, 1, target_px=(float("nan"), 3.0))
    assert nan_box == centred


def test_crop_box_degenerate_inputs_return_whole_image():
    assert wallpaper_crop_box(0, 0, 1, 1) == (0, 0, 0, 0)
    assert wallpaper_crop_box(100, 100, 0, 5) == (0, 0, 100, 100)


def _wcs_fits(tmp_path, ra0=83.8, dec0=-5.4, w=400, h=300, scale_deg=0.001):
    """A tiny FITS cube with a clean TAN WCS whose reference pixel is the centre.

    Let astropy write the NAXISn cards from the data shape — a (3, h, w) cube
    gives NAXIS1=w, NAXIS2=h, exactly what ``celestial_wcs_from_fits`` reads.
    """
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]      # 1-based centre
    wcs.wcs.crval = [ra0, dec0]
    wcs.wcs.cd = [[-scale_deg, 0.0], [0.0, scale_deg]]
    hdr = wcs.to_header()
    cube = np.zeros((3, h, w), dtype=np.float32)
    fp = tmp_path / "wcs.fits"
    fits.PrimaryHDU(data=cube, header=hdr).writeto(fp, overwrite=True)
    return fp, ra0, dec0, w, h


def test_target_pixel_maps_centre_and_rescales(tmp_path):
    fp, ra0, dec0, w, h = _wcs_fits(tmp_path)
    # The reference RA/Dec is the canvas centre → preview centre after rescale.
    prev_w, prev_h = w // 2, h // 2
    px = wallpaper_target_pixel(fp, ra0, dec0, prev_w, prev_h)
    assert px is not None
    assert abs(px[0] - prev_w / 2) < 1.0
    assert abs(px[1] - prev_h / 2) < 1.0


def test_target_pixel_offset_target_is_off_centre(tmp_path):
    fp, ra0, dec0, w, h = _wcs_fits(tmp_path, scale_deg=0.001)
    # Shift Dec well off the reference → clearly off the centre row.
    px = wallpaper_target_pixel(fp, ra0, dec0 + 0.05, w, h)
    assert px is not None
    assert abs(px[1] - h / 2) > 5


def test_target_pixel_none_without_wcs_or_position(tmp_path):
    fp = tmp_path / "plain.fits"
    fits.PrimaryHDU(data=np.zeros((3, 20, 20), np.float32)).writeto(fp)
    assert wallpaper_target_pixel(fp, 10.0, 10.0, 20, 20) is None   # no WCS
    fp2, ra0, dec0, w, h = _wcs_fits(tmp_path)
    assert wallpaper_target_pixel(fp2, None, dec0, w, h) is None     # no RA


def _rotate_marker_argmax(px, py, w, h, angle):
    """Ground truth: mark one bright pixel, rotate the image with the *same*
    routine the wallpaper uses, and read back where the mark landed."""
    img = np.zeros((h, w, 3), dtype=np.float32)
    img[py, px, :] = 1.0
    rot = rotate_image_north_up(img, angle)
    lum = rot.sum(axis=2)
    ry, rx = np.unravel_index(int(np.argmax(lum)), lum.shape)
    return (float(rx), float(ry)), (rot.shape[1], rot.shape[0])  # (x,y), (w,h)


def test_rotate_point_matches_lossless_90_step():
    # A near-90° angle snaps to a lossless rot90 — the helper must track the same
    # 90° turn the image takes, including the swapped canvas size.
    w, h = 40, 24
    for angle in (90.0, 90.4, -90.0, 180.0, -179.7):
        (gx, gy), (gw, gh) = _rotate_marker_argmax(9, 5, w, h, angle)
        rx, ry = rotate_point_north_up(9, 5, w, h, angle)
        assert abs(rx - gx) <= 1.0 and abs(ry - gy) <= 1.0


def test_rotate_point_matches_bicubic_expand():
    # A general angle is a bicubic expand-rotate; the helper must land on the same
    # spot in the grown canvas (a pixel of drift is fine — the crop is centred).
    w, h = 50, 30
    for angle in (30.0, -20.0, 45.0, 12.5):
        (gx, gy), (gw, gh) = _rotate_marker_argmax(35, 8, w, h, angle)
        rx, ry = rotate_point_north_up(35, 8, w, h, angle)
        assert abs(rx - gx) <= 1.5 and abs(ry - gy) <= 1.5


def test_rotate_point_zero_angle_is_identity():
    assert rotate_point_north_up(12.0, 7.0, 40, 20, 0.0) == (12.0, 7.0)


def _png(w, h, colour=(40, 80, 160)):
    img = Image.new("RGB", (w, h), colour)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_png_size():
    assert png_size(_png(320, 200)) == (320, 200)
    assert png_size(b"not a png") is None


def test_render_wallpaper_downscales_to_preset_and_keeps_aspect():
    # A large square preview → phone wallpaper capped at the preset size.
    data = render_wallpaper_jpeg(_png(3000, 3000), WALLPAPER_PRESETS["phone"])
    out = Image.open(BytesIO(data))
    assert data[:3] == b"\xff\xd8\xff"                     # JPEG magic
    assert out.width <= WALLPAPER_PRESETS["phone"]["max_w"]
    assert out.height <= WALLPAPER_PRESETS["phone"]["max_h"]
    assert abs(out.width / out.height - 1170 / 2532) < 0.02


def test_render_wallpaper_never_upsamples_small_preview():
    # A preview smaller than the device keeps native pixels (correct shape, no
    # invented detail). Phone crop of a 300×300 preview is full-height, narrow.
    data = render_wallpaper_jpeg(_png(300, 300), WALLPAPER_PRESETS["phone"])
    out = Image.open(BytesIO(data))
    assert out.height == 300                               # full-height crop, no upsample
    assert out.width < 300                                 # narrowed to phone shape
    assert abs(out.width / out.height - 1170 / 2532) < 0.03
