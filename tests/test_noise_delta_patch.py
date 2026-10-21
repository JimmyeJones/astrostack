"""The matched-crop "did it get better?" picture (engine side).

Covers the three honesty rules in :mod:`seestack.render.noisedelta`: one stretch
solved on the newer crop and replayed on the older (so a brightness step can
never masquerade as a quality difference), native-resolution pixels with no
resampling when the two canvases agree, and the σ ratio withheld the moment that
sampling rule stops holding.
"""

from __future__ import annotations

import io

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.render.noisedelta import (
    MIN_PATCH_PX,
    build_noise_delta,
    choose_patch_centre,
)
from seestack.stack.output import DISPLAY_SPACE_CARD


def _scene(h: int, w: int, *, noise: float, seed: int,
           glow: float = 0.12, pedestal: float = 0.10) -> np.ndarray:
    """A 3-channel ``(C, H, W)`` linear master of one target: the same extended
    glow every time, with the per-pixel noise (and optionally the sky ``pedestal``)
    the caller asks for — the "same object, one week deeper" case this picture
    exists to show."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = (xx - w / 2) ** 2 + (yy - h / 2) ** 2
    signal = pedestal + glow * np.exp(-r2 / (0.06 * h * w))
    chan = (signal + noise * rng.standard_normal((h, w))).astype(np.float32)
    return np.stack([chan, chan * 0.8, chan * 0.6]).astype(np.float32)


def _write(path, cube, *, display_space: bool = False) -> str:
    hdu = fits.PrimaryHDU(data=cube)
    if display_space:
        hdu.header[DISPLAY_SPACE_CARD] = True
    hdu.writeto(path, overwrite=True)
    return str(path)


def _halves(patch) -> tuple[np.ndarray, np.ndarray]:
    """The two crops back out of the composed PNG, as float arrays."""
    im = np.asarray(Image.open(io.BytesIO(patch.png)).convert("RGB"))
    side = patch.patch_px
    assert im.shape[1] > 2 * side          # the hairline divider is in there
    return im[:, :side].astype(np.float32), im[:, -side:].astype(np.float32)


def test_one_shared_stretch_not_two_independent_ones(tmp_path):
    # THE contract, and it needs the right fixture to show. Two masters with the
    # *same* pixels except a constant sky pedestal: a level difference, not a
    # quality difference.
    #
    # Under one shared stretch that offset survives into the picture, because the
    # same curve was applied to both — 48 display levels apart, measured. Under
    # two independent autostretches (which is what the stored `_preview.png`s are)
    # it is erased to **exactly zero**: an STF pins whatever sky it is given to its
    # own `target_bg`, and in erasing the offset it also re-slopes everything above
    # the sky, so the noisier half's structure comes out ~30 % flatter. That is the
    # black-point jump `seestack.render.deepening` exists to avoid, and the reason
    # this asserts the halves may legitimately DIFFER in brightness rather than
    # agree: a test that demanded matching medians would pass just as happily on
    # two independent stretches, which is the thing it is meant to forbid.
    older = _write(tmp_path / "old.fits",
                   _scene(600, 600, noise=0.010, seed=1, pedestal=0.14))
    newer = _write(tmp_path / "new.fits",
                   _scene(600, 600, noise=0.010, seed=1, pedestal=0.10))

    patch = build_noise_delta(older, newer)
    assert patch is not None
    left, right = _halves(patch)
    assert float(np.median(left)) - float(np.median(right)) > 20.0


def test_the_picture_carries_the_grain_difference_it_is_about(tmp_path):
    # The other half of the point: the crop is native-resolution, so the grain a
    # deeper stack removed is actually on screen. (A whole-canvas A/B at card size
    # is shrunk 5-10x, and decimation averages exactly this away before it is
    # drawn — which is why the card shows a crop at all.)
    older = _write(tmp_path / "old.fits", _scene(600, 600, noise=0.030, seed=1))
    newer = _write(tmp_path / "new.fits", _scene(600, 600, noise=0.005, seed=2))

    patch = build_noise_delta(older, newer)
    assert patch is not None
    left, right = _halves(patch)
    assert left.shape == right.shape
    grain = lambda a: float(np.median(np.abs(np.diff(a[..., 0], axis=1))))  # noqa: E731
    assert grain(left) > 2.0 * grain(right)


def test_identical_canvases_are_pixel_exact_and_carry_the_ratio(tmp_path):
    # Same canvas shape → the same pixel rectangle out of both, no resize on
    # either side, so the σ ratio's "identical sampling" precondition holds and
    # the number is offered. It must also point the right way (the newer, cleaner
    # master has the smaller σ) and land in the neighbourhood of the 6× the
    # fixture built in.
    older = _write(tmp_path / "old.fits", _scene(600, 600, noise=0.030, seed=3))
    newer = _write(tmp_path / "new.fits", _scene(600, 600, noise=0.005, seed=4))

    patch = build_noise_delta(older, newer)
    assert patch is not None
    assert patch.pixel_exact is True
    assert patch.patch_px >= MIN_PATCH_PX
    assert patch.noise_ratio is not None
    assert 3.0 < patch.noise_ratio < 12.0


def test_a_different_shape_without_a_wcs_withholds_the_picture(tmp_path):
    # Different canvas shapes (a mosaic that grew, or a drizzled restack) with no
    # WCS on either master: the patch used to be taken at the same canvas
    # *fraction* and resized, which on a grown mosaic is a different piece of sky
    # drawn at a different scale. Without a WCS there is nothing honest to show.
    # (The WCS-carried cases are at the bottom of this file.)
    older = _write(tmp_path / "old.fits", _scene(600, 600, noise=0.030, seed=5))
    newer = _write(tmp_path / "new.fits", _scene(900, 900, noise=0.005, seed=6))

    assert build_noise_delta(older, newer) is None


def test_a_display_space_export_gets_no_picture(tmp_path):
    # An editor export is already tone-mapped by a bespoke recipe; replaying a
    # linear master's STF onto it would double-process it, and there is no honest
    # way to match the two. The same gate the one-frame reveal uses.
    older = _write(tmp_path / "old.fits", _scene(600, 600, noise=0.03, seed=7))
    baked = _write(tmp_path / "new.fits", _scene(600, 600, noise=0.005, seed=8),
                   display_space=True)

    assert build_noise_delta(older, baked) is None
    assert build_noise_delta(baked, older) is None


def test_a_canvas_too_small_for_a_patch_gets_no_picture(tmp_path):
    # Below MIN_PATCH_PX there is neither enough sky for the estimator nor enough
    # pixels for the eye, so nothing is offered rather than a smudge.
    older = _write(tmp_path / "old.fits", _scene(80, 80, noise=0.03, seed=9))
    newer = _write(tmp_path / "new.fits", _scene(80, 80, noise=0.005, seed=10))

    assert build_noise_delta(older, newer) is None


def test_the_patch_avoids_a_ragged_mosaic_corner(tmp_path):
    # NaN is "no coverage". A crop that is half an uncovered corner on one side is
    # not a comparison of anything, so the chooser must land on a rectangle that
    # is covered in *both* masters — here the older one has a big NaN corner.
    old_cube = _scene(600, 600, noise=0.030, seed=11)
    old_cube[:, :300, :300] = np.nan
    older = _write(tmp_path / "old.fits", old_cube)
    newer = _write(tmp_path / "new.fits", _scene(600, 600, noise=0.005, seed=12))

    patch = build_noise_delta(older, newer)
    assert patch is not None
    left, _right = _halves(patch)
    # No part of the older half may come from the uncovered corner. An all-NaN
    # region packs to a flat black block, so a fully-covered crop has real spread.
    assert float(left.std()) > 1.0


def test_nothing_covered_in_both_gets_no_picture(tmp_path):
    # The degenerate version of the above: the two masters' covered areas do not
    # overlap anywhere a patch fits, so there is no "same patch of sky" to show.
    old_cube = _scene(600, 600, noise=0.030, seed=13)
    old_cube[:, :, 300:] = np.nan
    new_cube = _scene(600, 600, noise=0.005, seed=14)
    new_cube[:, :, :300] = np.nan
    older = _write(tmp_path / "old.fits", old_cube)
    newer = _write(tmp_path / "new.fits", new_cube)

    assert build_noise_delta(older, newer) is None


def test_the_chooser_prefers_faint_structure_over_bare_sky():
    # The chooser's whole job: pick the patch where the grain AND the faint detail
    # a deeper stack pulls out are both visible. A frame that is bare sky except
    # for one faint patch in the top-left must yield a centre in that quadrant,
    # not the canvas middle.
    rng = np.random.default_rng(15)
    h = w = 400
    lum = 0.10 + 0.01 * rng.standard_normal((h, w)).astype(np.float32)
    lum[40:160, 40:160] += 0.04          # faint, a few σ above the sky
    rgb = np.stack([lum, lum, lum], axis=-1)

    cx, cy = choose_patch_centre(rgb, 0.25)
    assert cx < 0.5 and cy < 0.5


# --- A grown canvas: the patch is carried through both masters' WCS ----------
#
# A mosaic that gained a row or column is restacked onto a bigger canvas, so the
# same canvas *fraction* is a different piece of sky. These fixtures paint one
# fixed sky (a smooth glow plus a field of stars) on a tangent plane and cut each
# master out of it with its own TAN WCS, so "the same patch of sky" can be
# checked against the stars rather than assumed.

_SKY_SCALE = 3.0e-4          # deg / px — a Seestar-ish ~1.1"/px


def _sky(h: int, w: int, *, y_off: int = 0, x_off: int = 0,
         step: float = 1.0) -> np.ndarray:
    """Noise-free luminance of the shared sky on an ``h×w`` canvas whose pixel
    ``(0, 0)`` sits at sky-grid ``(y_off, x_off)``, ``step`` grid units per pixel."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    gy, gx = y_off + (yy + 0.5) * step - 0.5, x_off + (xx + 0.5) * step - 0.5
    lum = 0.10 + 0.05 * np.exp(-((gx - 1500) ** 2 + (gy - 800) ** 2) / 8.0e5)
    rng = np.random.default_rng(99)
    r = int(np.ceil(4 * 2.5 / step))           # paint each star only near itself
    for sy, sx in rng.uniform(0, 3000, size=(6000, 2)):
        py, px = (sy - y_off + 0.5) / step - 0.5, (sx - x_off + 0.5) / step - 0.5
        y0, y1 = max(0, int(py) - r), min(h, int(py) + r + 1)
        x0, x1 = max(0, int(px) - r), min(w, int(px) + r + 1)
        if y0 >= y1 or x0 >= x1:
            continue
        win = (gx[y0:y1, x0:x1] - sx) ** 2 + (gy[y0:y1, x0:x1] - sy) ** 2
        lum[y0:y1, x0:x1] += 0.25 * np.exp(-win / (2 * 2.5 ** 2))
    return lum.astype(np.float32)


def _write_on_sky(path, h: int, w: int, *, y_off: int, x_off: int, noise: float,
                  seed: int, step: float = 1.0, rot_deg: float = 0.0,
                  with_wcs: bool = True) -> str:
    rng = np.random.default_rng(seed)
    chan = _sky(h, w, y_off=y_off, x_off=x_off, step=step) \
        + noise * rng.standard_normal((h, w)).astype(np.float32)
    hdu = fits.PrimaryHDU(data=np.stack([chan, chan * 0.8, chan * 0.6]))
    if with_wcs:
        # One tangent point at sky-grid (2000, 2000) for every master, so a
        # master's own pixel (x, y) is grid (x_off + x·step, y_off + y·step).
        hd = hdu.header
        hd["CTYPE1"], hd["CTYPE2"] = "RA---TAN", "DEC--TAN"
        hd["CRVAL1"], hd["CRVAL2"] = 83.8, 22.0
        hd["CRPIX1"] = (2000.0 - x_off + 0.5) / step + 0.5
        hd["CRPIX2"] = (2000.0 - y_off + 0.5) / step + 0.5
        t = np.radians(rot_deg)
        s = _SKY_SCALE * step
        hd["CD1_1"], hd["CD1_2"] = -s * np.cos(t), s * np.sin(t)
        hd["CD2_1"], hd["CD2_2"] = s * np.sin(t), s * np.cos(t)
    hdu.writeto(path, overwrite=True)
    return str(path)


def _same_sky(a: np.ndarray, b: np.ndarray) -> float:
    """Correlation of the two halves' smoothed luminance — near 1 for the same
    stars, near 0 for two different patches (the grain is smoothed out first,
    since it is independent between the masters by construction)."""
    from scipy.ndimage import gaussian_filter

    la = gaussian_filter(a.mean(axis=-1), 3).ravel()
    lb = gaussian_filter(b.mean(axis=-1), 3).ravel()
    return float(np.corrcoef(la, lb)[0, 1])


def _grain(half: np.ndarray) -> float:
    """Displayed grain: robust σ of row-to-row differences, stars and all."""
    d = np.diff(half.mean(axis=-1), axis=0).ravel()
    return float(1.4826 * np.median(np.abs(d - np.median(d))))


def test_a_grown_mosaic_shows_the_same_sky_at_the_same_scale(tmp_path):
    # The Scout's single-panel → 2×2 shape, at half size: the older canvas is a
    # piece of the newer one, offset into it, and both have the SAME noise. At
    # one pixel scale the older crop is the same native box, nothing is resized,
    # so the halves show the same stars and the same grain — and the σ ratio,
    # whose sampling rule now holds, is offered and reads "about the same".
    older = _write_on_sky(tmp_path / "old.fits", 540, 960, y_off=150, x_off=420,
                          noise=0.01, seed=21)
    newer = _write_on_sky(tmp_path / "new.fits", 1000, 1800, y_off=0, x_off=0,
                          noise=0.01, seed=22)

    patch = build_noise_delta(older, newer)
    assert patch is not None
    assert patch.pixel_exact is True
    assert patch.patch_px == 320
    left, right = _halves(patch)
    assert _same_sky(left, right) > 0.9
    g_old, g_new = _grain(left), _grain(right)
    assert abs(g_old / g_new - 1.0) < 0.1
    assert patch.noise_ratio is not None and 0.85 < patch.noise_ratio < 1.15


def test_a_grown_mosaic_with_a_wider_strip_is_still_the_same_sky(tmp_path):
    # 2×1 → 2×2: the two canvases are nearly the same width, which is where the
    # fraction mapping drifted ~500 px while *looking* plausible.
    older = _write_on_sky(tmp_path / "old.fits", 600, 1800, y_off=400, x_off=0,
                          noise=0.01, seed=23)
    newer = _write_on_sky(tmp_path / "new.fits", 1000, 1800, y_off=0, x_off=0,
                          noise=0.01, seed=24)

    patch = build_noise_delta(older, newer)
    assert patch is not None and patch.pixel_exact is True
    left, right = _halves(patch)
    assert _same_sky(left, right) > 0.9


def test_a_drizzled_restack_is_the_same_sky_resized_and_withholds_the_number(tmp_path):
    # Newer drizzled 2× (half the pixel scale): the older crop covers the same sky
    # in half the pixels, so one side is resampled — the picture is still the
    # same patch, but the σ ratio's sampling rule fails and it must be None.
    older = _write_on_sky(tmp_path / "old.fits", 700, 700, y_off=0, x_off=0,
                          noise=0.01, seed=25)
    newer = _write_on_sky(tmp_path / "new.fits", 1200, 1200, y_off=50, x_off=50,
                          noise=0.01, seed=26, step=0.5)

    patch = build_noise_delta(older, newer)
    assert patch is not None
    assert patch.pixel_exact is False
    assert patch.noise_ratio is None
    left, right = _halves(patch)
    assert left.shape == right.shape
    assert _same_sky(left, right) > 0.8


def test_a_different_canvas_without_a_wcs_gets_no_picture(tmp_path):
    # No WCS on a different-shaped pair: nothing can say where the patch went, and
    # a canvas fraction of a grown mosaic is a different piece of sky.
    older = _write_on_sky(tmp_path / "old.fits", 540, 960, y_off=150, x_off=420,
                          noise=0.01, seed=27, with_wcs=False)
    newer = _write_on_sky(tmp_path / "new.fits", 1000, 1800, y_off=0, x_off=0,
                          noise=0.01, seed=28)

    assert build_noise_delta(older, newer) is None
    assert build_noise_delta(newer, older) is None


def test_a_restack_turned_against_the_older_one_gets_no_picture(tmp_path):
    # An axis-aligned crop of a canvas turned 10° is a turned picture of the
    # patch; laid beside the newer one it reads as a different field.
    older = _write_on_sky(tmp_path / "old.fits", 700, 900, y_off=100, x_off=100,
                          noise=0.01, seed=29, rot_deg=10.0)
    newer = _write_on_sky(tmp_path / "new.fits", 1000, 1200, y_off=0, x_off=0,
                          noise=0.01, seed=30)

    assert build_noise_delta(older, newer) is None


def test_identical_canvases_ignore_the_wcs_and_take_the_same_rectangle(tmp_path):
    # The ordinary case is unchanged byte-for-byte: one canvas shape is the same
    # pixel rectangle out of both, WCS or not.
    a = _write_on_sky(tmp_path / "a.fits", 600, 800, y_off=0, x_off=0,
                      noise=0.02, seed=31)
    b = _write_on_sky(tmp_path / "b.fits", 600, 800, y_off=0, x_off=0,
                      noise=0.005, seed=32)
    a2 = _write_on_sky(tmp_path / "a2.fits", 600, 800, y_off=0, x_off=0,
                       noise=0.02, seed=31, with_wcs=False)
    b2 = _write_on_sky(tmp_path / "b2.fits", 600, 800, y_off=0, x_off=0,
                       noise=0.005, seed=32, with_wcs=False)

    with_wcs, without = build_noise_delta(a, b), build_noise_delta(a2, b2)
    assert with_wcs is not None and without is not None
    assert with_wcs.png == without.png
    assert with_wcs.pixel_exact is True
