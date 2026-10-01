"""The badge against ground truth through the **real drizzle kernel**.

``tests/test_noise_ratio_correlated.py`` pushes both sides through a real
debayer and a real registration warp, and stands a 2× **bilinear upsample** in
for the drizzle kernel. That stand-in is wrong about the one thing these tests
are for, and wrongly in the *reassuring* direction: a bilinear upsample is an
interpolation, so it blurs, and blur makes a master's per-pixel σ **fall**.
Drizzle does not interpolate — it deposits each input pixel as a shrunken drop
(``pixfrac``) onto a finer grid — so a drizzled master's pixels are noisier than
a native stack's, each one gathering a smaller share of every frame's light.

Measured here through :class:`seestack.stack.drizzle_path.DrizzleStacker` itself,
against the σ that is actually in the picture (the noiseless scene rides the
identical kernel, so ``noisy − clean`` *is* the noise):

    scale   master σ    badge      badge, area-matched
    ×1      0.001308    6.33       —
    ×1.5    0.001434    5.89       6.45
    ×2      0.001504    5.61       6.34
    ×3      0.001601    5.34       6.34

So the uncorrected badge tells the owner his drizzled stack cut 5.3–5.9× of the
noise where the same 36 frames cut 6.3× — and the *direction* is what makes it
worth fixing, because ``stackhealth.noise_vs_expected`` only ever acts on this
number when it comes in **low**. Averaging the master down to the sub's pixel
area puts every scale back within ~3 % of the native reading.

The owner drizzles mosaics (``seestack.stack.stacker.rejection_reach``'s own
note), and he is a heavy mosaic user, so this is his path and not a corner.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.io.fits_loader import bilinear_debayer
from seestack.qc.noise_ratio import (
    _background_sigma,
    area_match_block,
    noise_ratio,
)
from seestack.stack.drizzle_path import DrizzleParams, DrizzleStacker

SIGMA = 0.02
SIDE = 384
N_FRAMES = 36
MARGIN = 64          # crop off the kernel's edge roll-off before measuring


def _scene(h: int, w: int) -> np.ndarray:
    """A linear sky frame: gradient, a bright extended object, stars."""
    yy, xx = np.mgrid[0:h, 0:w]
    img = 0.10 + 0.004 * (xx / w) + 0.003 * (yy / h)
    img = img + 0.08 * np.exp(-(((xx - w // 2) ** 2 + (yy - h // 2) ** 2)
                                / (2 * (min(h, w) / 8.0) ** 2)))
    rng = np.random.default_rng(1)
    for _ in range(60):
        y, x = int(rng.integers(0, h)), int(rng.integers(0, w))
        img[max(0, y - 2):y + 3, max(0, x - 2):x + 3] += rng.uniform(0.05, 0.5)
    return img.astype(np.float32)


def _wcs(h: int, w: int, dx: float = 0.0, dy: float = 0.0):
    """A plain TAN WCS at the Seestar's own ~3.99″/px, offset by a dither."""
    from astropy.wcs import WCS

    k = WCS(naxis=2)
    k.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    k.wcs.crval = [180.0, 0.0]
    k.wcs.crpix = [w / 2.0 + dx, h / 2.0 + dy]
    k.wcs.cdelt = [-3.99 / 3600.0, 3.99 / 3600.0]
    k.pixel_shape = (w, h)
    return k


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return np.asarray(rgb, dtype=np.float32).mean(axis=-1)


def _drizzled(scale: float, *, seed: int = 7):
    """One sub and an ``N_FRAMES`` master drizzled at ``scale``, plus their truth.

    Every frame is a raw Bayer mosaic → the real
    :func:`~seestack.io.fits_loader.bilinear_debayer` → the real
    :class:`~seestack.stack.drizzle_path.DrizzleStacker` at the app's own default
    ``pixfrac`` and kernel, dithered by up to ±1.5 px the way a Seestar's subs
    are. The noiseless scene is drizzled through the identical geometry, so the
    difference is exactly the noise that ended up in each picture.

    The rng stream does not depend on ``scale``, so two calls at two scales are
    the *same* 36 frames with the *same* dithers — which is what makes "the badge
    must not depend on the canvas" a testable statement.
    """
    base = _scene(SIDE, SIDE)
    rng = np.random.default_rng(seed)
    ref = _wcs(SIDE, SIDE)
    params = DrizzleParams(pixfrac=0.8, scale=scale, kernel="square")
    noisy = DrizzleStacker(ref, (SIDE, SIDE), params)
    clean = DrizzleStacker(ref, (SIDE, SIDE), params)

    def debayer(arr: np.ndarray) -> np.ndarray:
        return bilinear_debayer(arr.astype(np.float32), pattern="RGGB")

    sub = debayer(base + rng.normal(0.0, SIGMA, base.shape))
    sub_clean = debayer(base)
    for _ in range(N_FRAMES):
        frame = debayer(base + rng.normal(0.0, SIGMA, base.shape))
        dx, dy = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        wcs = _wcs(SIDE, SIDE, dx, dy)
        noisy.add_frame(frame, wcs)
        clean.add_frame(sub_clean, wcs)

    cut, cut_m = MARGIN, int(round(MARGIN * scale))
    sub_l = _luminance(sub)[cut:-cut, cut:-cut]
    sub_cl = _luminance(sub_clean)[cut:-cut, cut:-cut]
    mas_l = _luminance(noisy.result())[cut_m:-cut_m, cut_m:-cut_m]
    mas_cl = _luminance(clean.result())[cut_m:-cut_m, cut_m:-cut_m]
    return (np.stack([sub_l] * 3, axis=-1), np.stack([mas_l] * 3, axis=-1),
            float(np.std(sub_l - sub_cl)), float(np.std(mas_l - mas_cl)))


@pytest.fixture(scope="module")
def native():
    return _drizzled(1.0)


@pytest.fixture(scope="module")
def drizzled_2x():
    return _drizzled(2.0)


def test_a_drizzled_master_really_is_noisier_per_pixel(native, drizzled_2x):
    """The fixture exhibits the bug, and in the direction the kernel dictates.

    Without this the two tests below could both pass on a fixture that had merely
    blurred the master — which is exactly how the bilinear stand-in in
    ``test_noise_ratio_correlated.py`` reads, and it points the other way.
    """
    _, _, _, truth_native = native
    _, _, _, truth_drizzled = drizzled_2x
    assert truth_drizzled > truth_native * 1.10
    # …and the estimator agrees with the truth on both, so what follows is about
    # the sampling and not about the σ estimate.
    _, master_n, _, _ = native
    _, master_d, _, _ = drizzled_2x
    assert _background_sigma(_luminance(master_n)) == pytest.approx(
        truth_native, rel=0.05)
    assert _background_sigma(_luminance(master_d)) == pytest.approx(
        truth_drizzled, rel=0.05)


def test_the_uncorrected_badge_reads_a_drizzled_stack_as_worse_than_it_is(
        native, drizzled_2x):
    """What shipped before: the same 36 frames, two different badges."""
    sub_n, master_n, _, _ = native
    sub_d, master_d, _, _ = drizzled_2x
    plain = noise_ratio(sub_n, master_n)
    unmatched = noise_ratio(sub_d, master_d, stack_supersampling=1.0)
    assert plain is not None and unmatched is not None
    # ~11 % low at ×2 — a badge the owner reads, and the one direction
    # ``noise_vs_expected`` acts on.
    assert unmatched < plain * 0.93


def test_matching_the_pixel_area_gives_one_number_for_one_stack(
        native, drizzled_2x):
    """The fix: the badge is a property of the frames, not of the canvas."""
    sub_n, master_n, _, _ = native
    sub_d, master_d, _, _ = drizzled_2x
    plain = noise_ratio(sub_n, master_n)
    matched = noise_ratio(sub_d, master_d, stack_supersampling=2.0)
    assert plain is not None and matched is not None
    assert matched == pytest.approx(plain, rel=0.04)


def test_a_native_run_is_measured_byte_for_byte_as_before(native):
    """Nothing about a non-drizzled library may move — it is every run the owner
    has (``StackOptions.drizzle`` defaults off) and every existing expectation in
    this suite."""
    sub, master, _, _ = native
    baseline = noise_ratio(sub, master)
    for scale in (1.0, None, 0.0, 0.5, float("nan")):
        assert noise_ratio(sub, master, stack_supersampling=scale) == baseline


@pytest.mark.parametrize(
    ("supersampling", "block"),
    [
        (1.0, 1), (None, 1), (0.0, 1), (0.9, 1), (float("nan"), 1),
        (float("inf"), 1), ("nonsense", 1),
        (1.25, 1), (1.5, 2), (1.75, 2), (2.0, 2), (2.4, 2), (3.0, 3),
        (8.0, 8), (99.0, 8),      # capped, so a nonsense scale can't bin it away
    ],
)
def test_area_match_block_is_a_whole_number_of_pixels(supersampling, block):
    assert area_match_block(supersampling) == block


def test_a_partly_uncovered_block_is_dropped_rather_than_part_averaged(
        drizzled_2x):
    """NaN = no coverage is engine-wide, and a block straddling the edge of the
    coverage is not a background sample. The measurement must survive one (a
    mosaic canvas is full of them) and must not fold it into a neighbour."""
    sub, master, _, _ = drizzled_2x
    holed = master.copy()
    holed[10:210, 10:210, :] = np.nan
    value = noise_ratio(holed[..., :1].repeat(3, axis=-1), holed,
                        stack_supersampling=2.0)
    assert value is not None and np.isfinite(value)
    intact = noise_ratio(sub, master, stack_supersampling=2.0)
    assert intact is not None
    assert noise_ratio(sub, holed, stack_supersampling=2.0) == pytest.approx(
        intact, rel=0.06)
