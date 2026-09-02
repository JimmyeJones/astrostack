"""What anchoring the asinh curve to the preview grid does and does *not* fix.

The v0.324.0 fix pins one tone curve to a run's saved 1024 px preview so the same
sliders mean one picture at every size the app renders at. The bug report behind
it also claimed a preview-vs-download 8-bit mean-abs difference of 12–18 that a
control "collapses to ~0" once the statistics are shared. That second claim does
not reproduce, and these tests pin why: most of that difference is the
non-linearity of rendering the same data at two resolutions — averaging stretched
pixels is not the same as stretching averaged ones — which no anchor can remove
and which the full-size render is on the *right* side of.

Recorded as tests, not just a comment, so a future run measuring that residual
finds it already explained instead of re-opening a fixed bug.
"""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from seestack.render.thumbnail import (
    PREVIEW_MAX_WIDTH,
    asinh_stretch,
    load_stack_rgb,
    measure_asinh_stats,
)

STRETCH, BLACK = 0.5, 0.35


@pytest.fixture
def master(tmp_path):
    """A realistic linear OSC master: flat sky with grain, a faint glow, small
    stars. The grain is the whole story — σ on the decimated preview grid is
    genuinely smaller than σ at native resolution, and it is also what makes the
    stretch's non-linearity bite on the way back down."""
    w, h = 1920, 1080
    rng = np.random.default_rng(11)
    ys, xs = np.mgrid[0:h, 0:w]
    glow = 0.02 * np.exp(-(((ys - h / 2) ** 2 / (2 * 260.0 ** 2))
                           + ((xs - w / 2) ** 2 / (2 * 420.0 ** 2))))
    cube = np.empty((3, h, w), dtype="float32")
    for c in range(3):
        cube[c] = (0.02 + glow + rng.normal(0, 0.004, (h, w))).astype("float32")
    for _ in range(40):
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        amp = float(rng.uniform(0.01, 0.05))
        cube += (amp * np.exp(-(((ys - cy) ** 2 + (xs - cx) ** 2)
                                / (2 * 1.5 ** 2)))).astype("float32")
    path = tmp_path / "master.fits"
    fits.PrimaryHDU(data=cube).writeto(path, overwrite=True)
    return path


def _u8(arr: np.ndarray) -> np.ndarray:
    return (np.clip(np.nan_to_num(arr), 0.0, 1.0) * 255).astype(np.uint8)


def _onto(arr8: np.ndarray, shape) -> np.ndarray:
    """Resample a rendered picture onto another render's pixel grid."""
    img = Image.fromarray(arr8, mode="RGB").resize((shape[1], shape[0]), Image.BOX)
    return np.asarray(img)


def _mean_abs(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(int) - b.astype(int)).mean())


def test_anchoring_the_curve_helps_but_a_residual_survives_it(master):
    """The measurement the bug report got wrong.

    Anchoring cuts the preview-vs-download difference, but nowhere near to zero —
    and the part it cuts is a minority of the whole.
    """
    preview_rgb, _ = load_stack_rgb(master, max_width=PREVIEW_MAX_WIDTH)
    native_rgb, _ = load_stack_rgb(master, max_width=8000)
    preview_stats = measure_asinh_stats(preview_rgb)

    preview = _u8(asinh_stretch(preview_rgb, stretch=STRETCH, black=BLACK))
    unanchored = _onto(
        _u8(asinh_stretch(native_rgb, stretch=STRETCH, black=BLACK)), preview.shape)
    anchored = _onto(
        _u8(asinh_stretch(native_rgb, stretch=STRETCH, black=BLACK,
                          stats=preview_stats)), preview.shape)

    before = _mean_abs(unanchored, preview)
    after = _mean_abs(anchored, preview)
    assert after < before                     # the fix genuinely helps…
    assert after > 5.0                        # …and does not come close to zero
    # Most of the reported difference was never the curve.
    assert after > 0.5 * before


def test_forcing_one_shared_curve_on_both_sides_does_not_collapse_the_difference(
    master,
):
    """The report's own control, run: give the preview render and the full-res
    render *identical* statistics, so the tone curve is provably the same
    function, and compare. If the difference were the curve it would vanish. It
    does not — what is left is the resampling non-linearity, and it is the bulk
    of the number."""
    preview_rgb, _ = load_stack_rgb(master, max_width=PREVIEW_MAX_WIDTH)
    native_rgb, _ = load_stack_rgb(master, max_width=8000)
    shared = measure_asinh_stats(native_rgb)

    preview = _u8(asinh_stretch(preview_rgb, stretch=STRETCH, black=BLACK,
                                stats=shared))
    full = _onto(_u8(asinh_stretch(native_rgb, stretch=STRETCH, black=BLACK,
                                   stats=shared)), preview.shape)
    assert _mean_abs(full, preview) > 5.0


def test_the_residual_is_the_stretch_being_non_linear_not_the_decimation(master):
    """The mechanism, isolated: on the *same* pixels, stretching then averaging
    and averaging then stretching give different answers, because asinh is
    concave. A linear "stretch" over the same path agrees exactly.

    This is why no choice of anchor can remove the residual: it is a property of
    applying a curve at one resolution and viewing it at another.
    """
    native_rgb, _ = load_stack_rgb(master, max_width=8000)
    stats = measure_asinh_stats(native_rgb)
    small = (native_rgb.shape[0] // 2, native_rgb.shape[1] // 2)

    def _shrink(a):
        return np.asarray(
            Image.fromarray(np.ascontiguousarray(a[..., 0]), mode="F")
            .resize((small[1], small[0]), Image.BOX), dtype=np.float32)

    stretched_then_averaged = _shrink(
        asinh_stretch(native_rgb, stretch=STRETCH, black=BLACK, stats=stats))
    averaged_then_stretched = asinh_stretch(
        np.repeat(_shrink(native_rgb)[..., None], 3, axis=2),
        stretch=STRETCH, black=BLACK, stats=stats)[..., 0]

    gap = float(np.mean(np.abs(stretched_then_averaged - averaged_then_stretched)))
    assert gap > 1.0 / 255.0, "the two orders should differ visibly"
    # Concave: lifting each noisy pixel and then averaging sits *above* lifting
    # the average, so the small render is systematically brighter, not merely
    # different. (This is also why the level shift does not cancel out.)
    assert float(np.mean(stretched_then_averaged - averaged_then_stretched)) > 0.0

    # The control: an affine map over the identical path commutes with the area
    # average exactly, so the same comparison gives (float32) nothing. Unclipped
    # on purpose — a clip is itself a non-linearity, and this is measuring the
    # curve's shape, not the endpoints.
    def _lin(a):
        return (a - stats.lo) / (stats.hi - stats.lo)

    lin_gap = float(np.mean(np.abs(
        _shrink(np.repeat(_lin(native_rgb[..., 0])[..., None], 3, axis=2))
        - _lin(_shrink(native_rgb)))))
    assert lin_gap < gap / 100.0
