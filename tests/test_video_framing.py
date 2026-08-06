"""Finding the Moon/Sun disk in a finished still, so the empty sky can go.

A Seestar frames its lunar/solar captures generously, so the stacked still is
mostly black sky with a small bright disk in it. These tests pin that
``measure_framing`` finds that disk on realistic synthetic stills, that it keeps
the whole disk (never clips the limb), that cropping changes framing and nothing
else, and — the part that protects a live install — that it *declines* on every
frame where cropping would be wrong: a disk that already fills the field, a blank
or blown-out frame, and a lone hot pixel.
"""

import numpy as np
import pytest

from seestack.video.framing import (
    DEFAULT_MARGIN,
    crop_to_disk,
    measure_framing,
)


def _still(
    h=540, w=960, *, radius=90, cy=None, cx=None, sky=0.02, disk=0.85, noise=0.005,
    seed=7,
):
    """A display-rendered Moon still: a soft-edged bright disk on a dark sky."""
    rng = np.random.default_rng(seed)
    cy = h // 2 if cy is None else cy
    cx = w // 2 if cx is None else cx
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - cy, xx - cx)
    # A limb that fades over ~2 px, like a real (slightly blurred) disk edge.
    profile = np.clip((radius - r) / 2.0, 0.0, 1.0)
    lum = sky + (disk - sky) * profile
    lum = lum + rng.normal(0.0, noise, size=lum.shape)
    img = np.repeat(np.clip(lum, 0.0, 1.0)[:, :, None], 3, axis=2)
    return img.astype(np.float32)


def test_finds_the_disk_and_says_cropping_is_worth_it():
    """The headline case: a Moon adrift in a big black rectangle."""
    img = _still()
    f = measure_framing(img)
    assert f is not None
    assert f.worthwhile
    y0, x0, y1, x1 = f.disk_box
    # The detected disk is the disk: centred, and ~2*radius across.
    assert (y0 + y1) / 2 == pytest.approx(270, abs=4)
    assert (x0 + x1) / 2 == pytest.approx(480, abs=4)
    assert (y1 - y0) == pytest.approx(180, abs=6)
    assert (x1 - x0) == pytest.approx(180, abs=6)
    # And the crop throws away most of the frame — that is the whole point.
    assert f.keep_fraction < 0.1
    assert f.trim_fraction > 0.9


def test_the_crop_keeps_the_whole_disk_with_room_to_spare():
    """Clipping the limb would be worse than not cropping at all."""
    img = _still()
    f = measure_framing(img)
    assert f is not None
    cropped = crop_to_disk(img, f)
    # Every pixel that was clearly disk in the original survives the crop.
    lum = img[..., 1]
    bright = lum > 0.5
    y, x = np.nonzero(bright)
    cy0, cx0, cy1, cx1 = f.box
    assert y.min() > cy0 and y.max() < cy1 - 1
    assert x.min() > cx0 and x.max() < cx1 - 1
    # The margin is real breathing room, not a rounding artefact.
    assert (cy1 - cy0) - (f.disk_box[2] - f.disk_box[0]) >= 2 * int(180 * DEFAULT_MARGIN) - 2
    assert cropped.shape == (cy1 - cy0, cx1 - cx0, 3)


def test_cropping_changes_framing_and_nothing_else():
    """The cropped still must be the same picture, minus the sky."""
    img = _still()
    f = measure_framing(img)
    assert f is not None
    cropped = crop_to_disk(img, f)
    y0, x0, y1, x1 = f.box
    assert np.array_equal(cropped, img[y0:y1, x0:x1])


def test_an_off_centre_disk_is_followed():
    """The Seestar does not centre the Moon for you."""
    img = _still(radius=70, cy=140, cx=250)
    f = measure_framing(img)
    assert f is not None
    y0, x0, y1, x1 = f.disk_box
    assert (y0 + y1) / 2 == pytest.approx(140, abs=4)
    assert (x0 + x1) / 2 == pytest.approx(250, abs=4)


def test_a_disk_that_already_fills_the_frame_is_left_alone():
    """A close-up solar disk has no sky to trim — cropping it is pure churn."""
    f = measure_framing(_still(radius=400))
    assert f is not None
    assert not f.worthwhile


def test_a_blank_frame_is_declined():
    """No sky/subject contrast at all — nothing to crop to."""
    assert measure_framing(np.full((200, 300, 3), 0.5, dtype=np.float32)) is None


def test_a_blown_out_frame_is_declined():
    """Everything at white reads as no disk, not as a frame-filling one."""
    assert measure_framing(np.ones((200, 300, 3), dtype=np.float32)) is None


def test_a_lone_hot_pixel_is_not_mistaken_for_a_moon():
    """Cropping to a single bright pixel would destroy the picture."""
    img = np.full((300, 400, 3), 0.02, dtype=np.float32)
    img[150, 200, :] = 1.0
    assert measure_framing(img) is None


def test_a_hot_pixel_does_not_stretch_the_box_around_a_real_disk():
    """The row/column floor exists so one stuck pixel can't undo the crop."""
    img = _still()
    img[10, 940, :] = 1.0
    f = measure_framing(img)
    assert f is not None
    assert f.worthwhile
    y0, x0, y1, x1 = f.disk_box
    assert y0 > 100 and x1 < 700


def test_uncovered_pixels_read_as_sky():
    """NaN is 'no coverage' engine-wide; it must never read as subject."""
    img = _still()
    img[:20, :, :] = np.nan
    f = measure_framing(img)
    assert f is not None
    assert f.disk_box[0] > 100


def test_a_greyscale_still_works_too():
    """The measure is on luma, so a 2-D image is a valid input."""
    img = _still()[..., 1]
    f = measure_framing(img)
    assert f is not None
    assert f.worthwhile


def test_a_tiny_image_is_declined_rather_than_cropped():
    assert measure_framing(np.zeros((2, 2, 3), dtype=np.float32)) is None
