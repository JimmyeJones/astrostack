"""Gentle sharpening of a finished Moon/Sun still.

Pure array work on an already display-rendered picture — no ffmpeg, no decode —
so unlike the rest of the video tests these run everywhere.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.video.detail import (
    SHARPEN_MAX,
    SHARPEN_PRESETS,
    sharpen_label,
    sharpen_still,
)


def _disk(w: int = 96, h: int = 72, *, detail: float = 0.06) -> np.ndarray:
    """A soft lunar-ish disk with fine surface texture, rendered 0–1."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xx - w / 2, yy - h / 2)
    disk = np.clip((min(w, h) * 0.35 - r) / 2.0 + 0.5, 0.0, 1.0)
    texture = np.sin(xx * 1.3) * np.cos(yy * 1.1)
    img = np.clip(0.6 * disk + detail * texture * disk, 0.0, 1.0)
    return np.repeat(img[..., None], 3, axis=2).astype(np.float32)


def _detail_energy(rgb: np.ndarray) -> float:
    """How much fine structure a picture carries (mean squared Laplacian)."""
    from scipy.ndimage import laplace

    lum = np.nan_to_num(rgb, nan=0.0).mean(axis=2)
    return float(np.mean(laplace(lum.astype(np.float32)) ** 2))


def test_off_returns_the_picture_untouched():
    """The default path must be free *and* byte-for-byte the old render."""
    img = _disk()
    for amount in (0.0, -1.0, float("nan")):
        out = sharpen_still(img, amount)
        assert np.array_equal(out, img)


def test_sharpening_lifts_fine_detail():
    img = _disk()
    before = _detail_energy(img)
    gentle = _detail_energy(sharpen_still(img, 0.6))
    strong = _detail_energy(sharpen_still(img, 2.0))
    assert gentle > before
    assert strong > gentle


def test_the_result_stays_a_writable_picture():
    """Clipped into 0–1, so it can still be saved as 8- or 16-bit."""
    out = sharpen_still(_disk(detail=0.3), SHARPEN_MAX)
    finite = out[np.isfinite(out)]
    assert finite.min() >= 0.0
    assert finite.max() <= 1.0
    assert out.dtype == np.float32


def test_sharpening_does_not_shift_colour_on_a_grey_picture():
    """One blur for all three channels, so a neutral picture stays neutral."""
    out = sharpen_still(_disk(), 1.2)
    assert np.allclose(out[..., 0], out[..., 1])
    assert np.allclose(out[..., 1], out[..., 2])


def test_an_amount_above_the_ceiling_is_capped_not_honoured():
    at_max = sharpen_still(_disk(), SHARPEN_MAX)
    beyond = sharpen_still(_disk(), SHARPEN_MAX * 5)
    assert np.array_equal(at_max, beyond)


def test_uncovered_pixels_stay_uncovered_and_do_not_bleed():
    """NaN = no coverage, everywhere in the engine — including here.

    A hole must come back a hole, and it must not eat a ring of real picture
    around itself the way blurring a NaN in place would.
    """
    img = _disk()
    img[10:16, 10:16, :] = np.nan
    out = sharpen_still(img, 1.2)

    hole = np.isnan(out[..., 0])
    assert hole[10:16, 10:16].all()
    assert hole.sum() == 6 * 6
    # The picture immediately around the hole is still real, and still close to
    # what it was — the hole did not drag it toward zero.
    ring = out[8:18, 8:18, 0]
    assert np.isfinite(ring[~np.isnan(ring)]).all()
    assert out[20, 20, 0] == pytest.approx(img[20, 20, 0], abs=0.15)


def test_presets_are_named_and_ordered_from_off_to_strong():
    names = [n for n, _ in SHARPEN_PRESETS]
    amounts = [a for _, a in SHARPEN_PRESETS]
    assert names[0] == "Off"
    assert amounts[0] == 0.0
    assert amounts == sorted(amounts)
    assert max(amounts) == SHARPEN_MAX


def test_a_result_can_say_in_words_how_hard_it_was_sharpened():
    for name, amount in SHARPEN_PRESETS:
        assert sharpen_label(amount) == name
    # An amount that didn't come from the list still reads as the nearest one.
    assert sharpen_label(0.65) == "Gentle"
    assert sharpen_label(99.0) == "Strong"
    assert sharpen_label(float("nan")) == "Off"
