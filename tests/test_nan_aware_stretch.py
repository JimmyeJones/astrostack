"""
NaN-aware autostretch + linear TIFF normalization.

The mosaic union canvas has large uncovered (NaN) regions. The export/stretch
code must compute its statistics over the *covered* pixels only — otherwise
those NaN-as-zero regions drag the per-channel black point to ~0 and corrupt
the colour balance (the "extremely red mosaic" bug).
"""

import numpy as np
import pytest

from seestack.gui.thumbnail import autostretch
from seestack.stack.output import _autostretch_for_export, _to_uint16_linear


def _covered_image_with_nan_gaps(h=200, w=300, *, gap_fraction=0.5):
    """A neutral-grey 'sky' image where ``gap_fraction`` of the canvas is NaN."""
    rng = np.random.default_rng(0)
    # Neutral sky: all 3 channels at ~1000 ADU with matched noise.
    img = rng.normal(1000.0, 30.0, size=(h, w, 3)).astype(np.float32)
    # A few bright neutral stars.
    for _ in range(20):
        y = int(rng.integers(10, h - 10))
        x = int(rng.integers(10, w - 10))
        img[y - 2:y + 3, x - 2:x + 3, :] += 8000.0
    # Carve a big NaN region (uncovered canvas).
    gap_cols = int(w * gap_fraction)
    img[:, :gap_cols, :] = np.nan
    return img


def test_autostretch_ignores_nan_gaps_keeps_color_neutral():
    """A neutral image with NaN gaps must stretch to a neutral (grey) result —
    the NaN region must not introduce a colour cast."""
    img = _covered_image_with_nan_gaps(gap_fraction=0.5)
    out = autostretch(img)
    # Covered region only.
    covered = np.isfinite(img[..., 0])
    r = out[..., 0][covered]
    g = out[..., 1][covered]
    b = out[..., 2][covered]
    # The three channels' medians should be close — neutral sky stays neutral.
    mr, mg, mb = np.median(r), np.median(g), np.median(b)
    spread = max(mr, mg, mb) - min(mr, mg, mb)
    assert spread < 0.06, f"channel medians diverged: R={mr:.3f} G={mg:.3f} B={mb:.3f}"
    # And the sky should land near the target_bg (0.20 default), not crushed to 0.
    assert 0.08 < mg < 0.45


def test_autostretch_without_nan_still_works():
    """Regression: a fully-covered image (no NaN) still stretches sanely."""
    rng = np.random.default_rng(1)
    img = rng.normal(1000.0, 30.0, size=(100, 120, 3)).astype(np.float32)
    out = autostretch(img)
    assert out.shape == img.shape
    assert np.isfinite(out).all()
    assert 0.0 <= out.min() and out.max() <= 1.0


def test_autostretch_is_hot_pixel_robust():
    """A single un-rejected hot/cosmic pixel must not darken the STF picture.

    ``autostretch`` normalises the whole image by its top-of-range before
    fitting the per-channel MTF. Using the raw ``nanmax`` let one surviving hot
    pixel inflate that top, compress the sky median toward 0, and — once the
    MTF midtone clamp is hit — crush the whole result to near-black (the sibling
    ``asinh_stretch`` was already fixed for exactly this). Using a robust 99.5th
    percentile keeps the sky anchored at ``target_bg`` regardless of the outlier.
    """
    rng = np.random.default_rng(7)
    h, w = 400, 400
    sky = 0.02
    base = np.abs(rng.normal(sky, 0.002, size=(h, w))).astype(np.float32)
    # A realistic bright-star population so hi/sky is already large, like real data.
    for _ in range(60):
        y = int(rng.integers(20, h - 20))
        x = int(rng.integers(20, w - 20))
        amp = float(10 ** rng.uniform(-1.0, 1.3)) * sky * 50.0
        yy, xx = np.mgrid[y - 6:y + 7, x - 6:x + 7]
        base[y - 6:y + 7, x - 6:x + 7] += (
            amp * np.exp(-((yy - y) ** 2 + (xx - x) ** 2) / 4.0)
        ).astype(np.float32)
    rgb = np.stack([base, base, base], axis=-1)

    sky_mask = base < (sky + 0.01)  # pixels that are genuinely background

    def sky_median(out):
        return float(np.median(out[..., 0][sky_mask]))

    clean = sky_median(autostretch(rgb))
    # Clean sky lands near the 0.20 target.
    assert 0.12 < clean < 0.28, clean

    # A hot pixel far brighter than the brightest star must not move the sky.
    for mult in (2.0, 20.0, 200.0):
        contaminated = rgb.copy()
        contaminated[h // 2, w // 2, :] = float(base.max()) * mult
        got = sky_median(autostretch(contaminated))
        # Before the fix this collapsed toward 0 (0.10 → 0.011 → 0.001); after,
        # it holds within a small tolerance of the clean sky level.
        assert abs(got - clean) < 0.02, f"hot pixel {mult}x moved sky {clean:.3f}->{got:.3f}"


def test_autostretch_all_nan_returns_zeros():
    img = np.full((20, 20, 3), np.nan, dtype=np.float32)
    out = autostretch(img)
    assert out.shape == img.shape
    assert np.all(out == 0.0)


def test_autostretch_accepts_2d_mono_like_asinh():
    """A 2-D (mono) input must stretch as a grey image, not raise an AxisError.

    ``asinh_stretch`` already expands a 2-D array to 3 channels; ``autostretch``
    is documented to behave the same way, so a mono array must produce a 3-channel
    result whose channels are identical (neutral grey). Before the guard this
    raised ``AxisError: axis 2 is out of bounds`` at the ``any(axis=2)`` stat.
    """
    from seestack.render.thumbnail import asinh_stretch

    rng = np.random.default_rng(3)
    mono = rng.normal(1000.0, 30.0, size=(80, 100)).astype(np.float32)
    # A couple of bright sources so the stretch has real signal to lift.
    mono[20:24, 30:34] += 8000.0

    out = autostretch(mono)
    assert out.ndim == 3 and out.shape == (80, 100, 3)
    assert np.isfinite(out).all()
    assert 0.0 <= out.min() and out.max() <= 1.0
    # Mono in → the three output channels must be identical (no colour cast).
    assert np.array_equal(out[..., 0], out[..., 1])
    assert np.array_equal(out[..., 1], out[..., 2])
    # And a mono array is treated exactly like its 3-channel expansion.
    expanded = autostretch(np.stack([mono, mono, mono], axis=-1))
    assert np.array_equal(out, expanded)
    # Sibling parity: asinh_stretch has always accepted 2-D — so does this now.
    assert asinh_stretch(mono).shape == (80, 100, 3)


def test_to_uint16_linear_skips_nan_for_percentiles():
    """The linear TIFF percentile range must come from covered pixels only."""
    img = _covered_image_with_nan_gaps(gap_fraction=0.6)
    u16 = _to_uint16_linear(img)
    assert u16.dtype == np.uint16
    covered = np.isfinite(img[..., 0])
    # Uncovered region → 0 (black).
    assert np.all(u16[~covered] == 0)
    # Covered sky should use a healthy chunk of the 16-bit range, not be
    # crushed near zero by the NaN-region zeros.
    covered_vals = u16[covered]
    assert covered_vals.max() > 30000  # bright stars reach high
    assert np.median(covered_vals) > 200  # sky isn't crushed to black


def test_autostretch_for_export_passes_nan_through():
    """_autostretch_for_export must not pre-zero NaN — it should rely on
    autostretch's nan-awareness."""
    img = _covered_image_with_nan_gaps(gap_fraction=0.5)
    out = _autostretch_for_export(img)
    covered = np.isfinite(img[..., 0])
    # Same neutrality check as the direct autostretch test.
    mr = np.median(out[..., 0][covered])
    mg = np.median(out[..., 1][covered])
    mb = np.median(out[..., 2][covered])
    spread = max(mr, mg, mb) - min(mr, mg, mb)
    assert spread < 0.06
