"""The estimator against **ground truth**, on pixels this pipeline has correlated.

``tests/test_noise_ratio_expectation.py`` builds both sides with ``rng.normal``
on one grid — the sub is a raw frame and the "stack" a plain ``.mean(axis=0)`` —
so every pixel there is independent of its neighbours and the classic lag-1
estimator is unbiased on it. That is a regime the app never shows the badge in:
the sub reaches :func:`seestack.qc.noise_ratio.noise_ratio` through
:func:`~seestack.io.fits_loader.bilinear_debayer`, and the master through a
registration warp and, on most runs, a drizzle kernel.

These build that pipeline and check the measurement against the σ that is
**actually** in the picture — obtainable because the same scene is pushed through
the same warps with and without noise, so their difference *is* the noise. Each
one also measures the lag-1 adjacent-pixel estimator the module used to use, and
asserts it over-reads: a fixture that cannot exhibit the bug would be green for
the wrong reason.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import shift as nd_shift
from scipy.ndimage import zoom as nd_zoom

from seestack.io.fits_loader import bilinear_debayer
from seestack.qc.noise_ratio import _background_sigma, noise_ratio
from seestack.stackhealth import NOISE_EXPECTED_LOW_FRACTION, noise_vs_expected

SIGMA = 0.02
MARGIN = 48          # crop off the warped edges before measuring anything


def _scene(h: int, w: int, *, seed: int = 1) -> np.ndarray:
    """A linear sky frame: gradient, a bright extended object, stars."""
    yy, xx = np.mgrid[0:h, 0:w]
    img = 0.10 + 0.004 * (xx / w) + 0.003 * (yy / h)
    img = img + 0.08 * np.exp(-(((xx - w // 2) ** 2 + (yy - h // 2) ** 2)
                                / (2 * (min(h, w) / 8.0) ** 2)))
    rng = np.random.default_rng(seed)
    for _ in range(60):
        y = int(rng.integers(0, h))
        x = int(rng.integers(0, w))
        img[max(0, y - 2):y + 3, max(0, x - 2):x + 3] += rng.uniform(0.05, 0.5)
    return img.astype(np.float32)


def _lag1_sigma(lum: np.ndarray) -> float:
    """The estimator this module used before: σ from the MAD of *adjacent*-pixel
    differences, ``Var(Iᵢ₊₁ − Iᵢ) = 2σ²``. Kept here, and only here, so each test
    can show the fixture really does fool it."""
    def once(keep: np.ndarray) -> float:
        parts = []
        for a, b, ka, kb in ((lum[:, 1:], lum[:, :-1], keep[:, 1:], keep[:, :-1]),
                             (lum[1:, :], lum[:-1, :], keep[1:, :], keep[:-1, :])):
            valid = ka & kb
            d = (a - b)[valid]
            if d.size:
                parts.append(d)
        d = np.concatenate(parts)
        mad = float(np.median(np.abs(d - np.median(d))))
        return 1.4826 * mad / np.sqrt(2.0)

    finite = np.isfinite(lum)
    rough = once(finite)
    med = float(np.nanmedian(lum))
    return once(finite & (lum <= med + 4.0 * rough))


def _pipeline(h: int, w: int, n: int, *, drizzle: int = 1, seed: int = 7,
              shared_var: float = 0.0):
    """One sub and an ``n``-frame master, both carried through the real thing.

    Each frame is a raw Bayer mosaic → :func:`bilinear_debayer` → a sub-pixel
    bilinear shift (the registration warp) → optionally a 2× bilinear upsample
    (standing in for the drizzle kernel) → the mean. The noiseless scene rides
    the identical warps, so ``noisy − clean`` is exactly the noise that ended up
    in the picture and its std is the ground-truth σ.

    ``shared_var`` is the fraction of each frame's noise variance that lands in
    the *same place on the canvas* in every frame — a drifting gradient, a
    residual sky pattern, the same sub counted twice. Averaging cannot touch it,
    so it is how an underperforming stack is modelled, and it is added after the
    warp because that is where such a pattern lives (noise injected in the
    **sensor** frame is not shared once each frame is warped differently: the
    differing sub-pixel shifts average most of it away, measured at 0.79·√N for
    a 10 % sensor-frame share against 0.33·√N for the canvas-frame one).
    """
    base = _scene(h, w)
    rng = np.random.default_rng(seed)
    assert drizzle == 1 or not shared_var, "canvas-frame share needs one sampling"

    def debayered(arr: np.ndarray) -> np.ndarray:
        return bilinear_debayer(arr.astype(np.float32), pattern="RGGB").mean(axis=-1)

    shared = rng.normal(0.0, SIGMA * np.sqrt(shared_var),
                        base.shape).astype(np.float32)
    indep = SIGMA * np.sqrt(1.0 - shared_var)
    sub = debayered(base + rng.normal(0.0, indep, base.shape)) + shared
    sub_clean = debayered(base)

    oh, ow = h * drizzle, w * drizzle
    noisy = np.zeros((oh, ow), dtype=np.float64)
    clean = np.zeros((oh, ow), dtype=np.float64)
    for _ in range(n):
        frame = debayered(base + rng.normal(0.0, indep, base.shape))
        dy, dx = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        warped = nd_shift(frame, (dy, dx), order=1, mode="nearest")
        warped0 = nd_shift(sub_clean, (dy, dx), order=1, mode="nearest")
        if drizzle > 1:
            warped = nd_zoom(warped, drizzle, order=1)
            warped0 = nd_zoom(warped0, drizzle, order=1)
        noisy += warped
        clean += warped0
    master = (noisy / n).astype(np.float32)
    if shared_var:
        master = master + shared
    master_clean = (clean / n).astype(np.float32)

    c, cm = MARGIN, MARGIN * drizzle
    sub, sub_clean = sub[c:-c, c:-c], sub_clean[c:-c, c:-c]
    master, master_clean = master[cm:-cm, cm:-cm], master_clean[cm:-cm, cm:-cm]
    true_sub = float(np.std(sub - sub_clean))
    true_master = float(np.std(master - master_clean))
    return sub, master, true_sub, true_master


def _ratio(sub: np.ndarray, master: np.ndarray) -> float:
    value = noise_ratio(np.stack([sub] * 3, axis=-1), np.stack([master] * 3, axis=-1))
    assert value is not None
    return value


def test_native_master_reads_the_noise_that_is_really_there() -> None:
    sub, master, true_sub, true_master = _pipeline(384, 384, 36)
    truth = true_sub / true_master
    assert _ratio(sub, master) == pytest.approx(truth, rel=0.08)
    assert _lag1_sigma(sub) / _lag1_sigma(master) > truth * 1.05


def test_drizzled_master_reads_the_noise_that_is_really_there() -> None:
    sub, master, true_sub, true_master = _pipeline(256, 256, 36, drizzle=2)
    truth = true_sub / true_master
    assert _ratio(sub, master) == pytest.approx(truth, rel=0.10)
    assert _lag1_sigma(sub) / _lag1_sigma(master) > truth * 1.5


def test_each_side_is_measured_without_bias() -> None:
    sub, master, true_sub, true_master = _pipeline(384, 384, 36)
    assert _background_sigma(sub) == pytest.approx(true_sub, rel=0.06)
    assert _background_sigma(master) == pytest.approx(true_master, rel=0.08)
    assert _lag1_sigma(master) < true_master * 0.95


def test_the_low_nudge_still_separates_a_good_stack_from_a_correlated_one() -> None:
    """The 0.7·√N threshold is a claim about *this* estimator, so moving the
    estimator has to be re-checked against it — and on the real pipeline, not
    only on the independent-pixel sweep in
    ``tests/test_noise_ratio_expectation.py``. A healthy stack clears it with
    room to spare (resampling makes the per-pixel cut a little *better* than √N,
    so the share sits above 1.0); a stack whose subs share 10 % of their noise
    variance falls far below it, which is the case the nudge exists to catch."""
    n = 25
    sub, master, _, _ = _pipeline(256, 256, n)
    healthy = _ratio(sub, master) / np.sqrt(n)
    assert healthy > NOISE_EXPECTED_LOW_FRACTION + 0.2
    assert noise_vs_expected(_ratio(sub, master), n) == "expected"

    sub, master, _, _ = _pipeline(256, 256, n, shared_var=0.10)
    correlated = _ratio(sub, master) / np.sqrt(n)
    assert correlated < NOISE_EXPECTED_LOW_FRACTION
    assert noise_vs_expected(_ratio(sub, master), n) == "low"
