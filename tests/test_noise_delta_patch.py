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


def test_a_resized_half_withholds_the_number_but_still_draws_the_picture(tmp_path):
    # Different canvas shapes (a mosaic that grew, or a drizzled restack) mean
    # one side has to be resampled to be shown beside the other. A resize lowers
    # the resampled side's per-pixel σ for reasons that have nothing to do with
    # stacking, so the ratio must be None — while the *picture*, which is a fair
    # comparison at a matched scale, is still composed.
    older = _write(tmp_path / "old.fits", _scene(600, 600, noise=0.030, seed=5))
    newer = _write(tmp_path / "new.fits", _scene(900, 900, noise=0.005, seed=6))

    patch = build_noise_delta(older, newer)
    assert patch is not None
    assert patch.pixel_exact is False
    assert patch.noise_ratio is None
    left, right = _halves(patch)
    assert left.shape == right.shape


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
