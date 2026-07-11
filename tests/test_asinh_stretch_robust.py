"""Regression: the editor's default asinh stretch must be robust to a single
extreme outlier pixel.

`render/thumbnail.py::asinh_stretch` used to normalize its dynamic range over the
raw `[nanmin, nanmax]`. A single surviving hot/warm pixel (bloom, bright column,
un-rejected cosmic ray) then inflated the max, divided the whole image down, and —
because the asinh gain is fixed by the slider, not adaptive — crushed the faint
nebulosity to near-black. This is the exact "my stack looks black/broken" moment
on the editor's default view. The fix scales the top of the range by a robust
99.5th percentile (bright stars still saturate to white via the final clip),
mirroring the sibling scaling in `edit/ops/detail.py`.
"""

import numpy as np

from seestack.render.thumbnail import asinh_stretch


def _nebula_scene(h=180, w=220, seed=0):
    """A linear stacked-image proxy: faint sky, a soft central nebula, and a
    handful of bright star cores that set the (sane) dynamic-range ceiling."""
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 40.0, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    neb = 500.0 * np.exp(-(((xx - w * 0.5) / 40) ** 2 + ((yy - h * 0.5) / 40) ** 2))
    img[..., 0] += neb
    img[..., 1] += neb * 0.7
    img[..., 2] += neb * 0.4
    for _ in range(15):
        img[rng.integers(0, h), rng.integers(0, w)] += rng.uniform(9000.0, 30000.0)
    return img


def _nebula_brightness(out: np.ndarray, h=180, w=220) -> float:
    """Mean rendered luminance over the central nebula patch."""
    cy, cx = h // 2, w // 2
    return float(out[cy - 8:cy + 8, cx - 8:cx + 8].mean())


def test_asinh_survives_a_single_hot_outlier_pixel():
    scene = _nebula_scene()
    baseline = _nebula_brightness(asinh_stretch(scene))

    # One pathological hot pixel ~100x the star cores (the un-rejected outlier).
    hot = scene.copy()
    hot[5, 5, :] = np.nanmax(scene) * 100.0
    with_hot = _nebula_brightness(asinh_stretch(hot))

    # The nebula must stay clearly visible — before the fix a single outlier
    # collapsed it toward black. Require the rendered nebula to stay well within
    # range of the outlier-free render (and simply not blacked out).
    assert with_hot > 0.5 * baseline, (
        f"one hot pixel crushed the nebula: {baseline:.3f} -> {with_hot:.3f}"
    )
    assert with_hot > 0.05, "nebula effectively blacked out by a single outlier"


def test_asinh_normal_image_unharmed():
    """A normal image still renders sanely: finite, in-range, nebula visible,
    star cores saturating to white."""
    scene = _nebula_scene(seed=3)
    out = asinh_stretch(scene)
    assert out.shape == scene.shape
    assert np.isfinite(out).all()
    assert 0.0 <= out.min() and out.max() <= 1.0
    # Nebula clearly lifted above the sky floor.
    assert _nebula_brightness(out) > 0.1
    # The brightest star cores still peg to (near) white despite the robust hi.
    assert out.max() > 0.95


def test_asinh_near_flat_image_falls_back_gracefully():
    """A near-constant image (99.5th pct == min) must not divide-by-zero to a
    blank frame — the max fallback keeps it from collapsing."""
    img = np.full((40, 50, 3), 1000.0, dtype=np.float32)
    img[0, 0, :] = 5000.0                    # a lone bright pixel above the flat
    out = asinh_stretch(img)
    assert np.isfinite(out).all()
    assert out.max() > 0.0                   # not a blank/all-zero frame
