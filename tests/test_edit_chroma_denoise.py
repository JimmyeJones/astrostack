"""Pixel-level tests for the ``detail.chroma_denoise`` colour-blotch smoother.

The op exists because the visible defect a thin OSC stack's sky shows *after*
ordinary wavelet denoise isn't fine grain but a low-frequency colour drift —
patches of sky wandering green/magenta over tens of pixels — which the wavelet
pass can't reach (it only shrinks fine scales). The guarantees that make it safe
to run on the one-click Auto path are all asserted here:

  * strength 0 is an exact identity,
  * the **luminance is bit-identical** to the input, so it can never soften a
    star, an edge or the grain — only colour moves,
  * an actual colour blotch is measurably flattened,
  * uncovered (NaN) mosaic pixels stay NaN and never bleed a fill value inward,
  * ``protect_stars`` keeps a coloured star's own colour instead of smearing it
    into the surrounding sky, and
  * genuinely extended colour (a faint nebula) survives.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("scipy")

from seestack.edit.registry import EditContext, get_op, luminance

OP = "detail.chroma_denoise"


def _sky_with_colour_blotch(h=180, w=240, seed=4):
    """A flat, mildly noisy sky carrying a smooth ~25 px-scale green/magenta drift
    — the defect the op targets — plus fine per-pixel grain (which it must not be
    judged on, since that lives in the luminance)."""
    from scipy.ndimage import gaussian_filter

    rng = np.random.default_rng(seed)
    low = gaussian_filter(rng.normal(0, 1, (h, w)).astype(np.float32), 25.0)
    low /= float(np.std(low))
    rgb = np.full((h, w, 3), 0.12, dtype=np.float32)
    rgb[..., 1] += 0.02 * low            # green drifts one way…
    rgb[..., 0] -= 0.012 * low           # …red/blue the other → green/magenta patches
    rgb[..., 2] -= 0.008 * low
    rgb += rng.normal(0, 0.012, (h, w, 3)).astype(np.float32)
    return rgb.astype(np.float32)


def _chroma_spread(rgb: np.ndarray) -> list[float]:
    """Per-channel spread of the colour offset ``C − Y`` over the frame — the
    blotch itself, measured independently of brightness."""
    y = luminance(rgb)
    return [float(np.nanstd(rgb[..., c] - y)) for c in range(3)]


def test_strength_zero_is_an_exact_identity():
    rgb = _sky_with_colour_blotch()
    out = get_op(OP).apply(rgb, {"strength": 0.0}, EditContext())
    assert np.array_equal(out, rgb)


def test_luminance_is_preserved_exactly():
    """The defining property: the op rewrites colour only. Rec.709 weights sum to
    1, so ``Σ wc·(C − Y) ≡ 0``; the smoothing is linear with one shared kernel, so
    the recombined luminance is the input's to float32 rounding."""
    rgb = _sky_with_colour_blotch()
    out = get_op(OP).apply(rgb, {"strength": 1.0}, EditContext())
    assert float(np.max(np.abs(luminance(out) - luminance(rgb)))) < 1e-6


def test_it_flattens_a_colour_blotch():
    rgb = _sky_with_colour_blotch()
    out = get_op(OP).apply(rgb, {"strength": 1.0}, EditContext())
    before, after = _chroma_spread(rgb), _chroma_spread(out)
    for b, a in zip(before, after, strict=True):
        assert a < 0.75 * b, (b, a)   # measured ~0.6–0.7× on this scene


def test_strength_scales_the_effect_monotonically():
    rgb = _sky_with_colour_blotch()
    op = get_op(OP)
    spreads = [
        _chroma_spread(op.apply(rgb, {"strength": s}, EditContext()))[1]
        for s in (0.0, 0.25, 0.5, 1.0)
    ]
    assert spreads == sorted(spreads, reverse=True)
    assert spreads[0] > spreads[-1]


def test_uncovered_pixels_stay_nan_and_do_not_bleed_inward():
    """A mosaic gap must survive as NaN, and — because the blur is normalised by
    the coverage map rather than run over a filled array — the covered pixels
    beside it must not be dragged toward a fill value."""
    rgb = _sky_with_colour_blotch()
    gapped = rgb.copy()
    gapped[:20, :, :] = np.nan
    out = get_op(OP).apply(gapped, {"strength": 1.0}, EditContext())
    assert np.all(np.isnan(out[:20, :, :]))
    assert np.all(np.isfinite(out[20:, :, :]))
    # The covered rows next to the gap keep the input's luminance exactly, and
    # their colour stays within the sky's own range (no fill-value pull).
    band = slice(20, 40)
    assert float(np.max(np.abs(luminance(out[band]) - luminance(gapped[band])))) < 1e-6
    for c in range(3):
        d_in = gapped[band, :, c] - luminance(gapped[band])
        d_out = out[band, :, c] - luminance(out[band])
        assert float(np.max(np.abs(d_out))) <= float(np.max(np.abs(d_in))) + 1e-3


def test_protect_stars_keeps_a_coloured_star_from_bleeding():
    """A wide chroma kernel would otherwise smear a strongly-coloured star's hue
    across its surroundings. With the default protection on, the star keeps its
    own colour; with it off, it visibly loses it."""
    rgb = _sky_with_colour_blotch()
    h, w = rgb.shape[:2]
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    star = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 1.5 ** 2)))
    rgb = rgb + (0.9 * star)[..., None] * np.array([1.0, 0.6, 0.35], np.float32)
    op = get_op(OP)
    protected = op.apply(rgb, {"strength": 1.0}, EditContext())
    bled = op.apply(rgb, {"strength": 1.0, "protect_stars": False}, EditContext())

    def rg(img):
        return float(img[cy, cx, 0] / img[cy, cx, 1])

    assert abs(rg(protected) - rg(rgb)) < 0.01 * rg(rgb)
    assert abs(rg(bled) - rg(rgb)) > 0.03 * rg(rgb)


def test_faint_extended_colour_survives():
    """Real, broad colour (a faint nebula only ~1σ above the sky, so the star
    protection barely engages) must keep most of its own hue — the op flattens
    patchiness, it does not desaturate the target."""
    rgb = _sky_with_colour_blotch()
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    neb = np.exp(-(((xx - w * 0.5) ** 2 + (yy - h * 0.5) ** 2) / (2 * 45.0 ** 2)))
    rgb = rgb + neb[..., None] * np.array([0.032, 0.010, 0.008], np.float32)
    out = get_op(OP).apply(rgb, {"strength": 0.5}, EditContext())
    core = neb > 0.9
    before = float(np.mean((rgb[..., 0] - luminance(rgb))[core]))
    after = float(np.mean((out[..., 0] - luminance(out))[core]))
    assert after > 0.8 * before, (before, after)


def test_radius_is_scaled_for_the_preview_proxy():
    """The radius is a *full-resolution* pixel measure, so on the decimated live
    preview it must shrink by ``proxy_scale`` — otherwise the preview would smooth
    a physically wider area than the export it is supposed to predict."""
    rgb = _sky_with_colour_blotch()
    op = get_op(OP)
    full = op.apply(rgb, {"strength": 1.0, "radius": 24.0}, EditContext())
    on_proxy = op.apply(rgb, {"strength": 1.0, "radius": 24.0},
                        EditContext(proxy_scale=4.0, is_proxy=True))
    matched = op.apply(rgb, {"strength": 1.0, "radius": 6.0}, EditContext())
    # The proxy render matches the *scaled* radius, not the raw one.
    assert np.allclose(on_proxy, matched, atol=1e-6)
    assert not np.allclose(on_proxy, full, atol=1e-4)


def test_degenerate_and_all_nan_inputs_are_left_alone():
    sliver = np.full((1, 40, 3), 0.1, dtype=np.float32)
    assert np.array_equal(get_op(OP).apply(sliver, {"strength": 1.0}, EditContext()),
                          sliver)
    empty = np.full((20, 20, 3), np.nan, dtype=np.float32)
    assert np.all(np.isnan(get_op(OP).apply(empty, {"strength": 1.0}, EditContext())))
