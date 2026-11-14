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


def _near_black_sky_with_coloured_stars(h=160, w=200, seed=7):
    """What the op meets on the one-click Auto path, where it runs *after* the
    stretch: a display-space sky the STF has pressed against black (one channel
    at or near 0 across much of it), a colour drift on top, and a few saturated
    coloured stars — the pixels whose chroma a wide blur pulls past an edge of
    ``[0, 1]``."""
    rgb = _sky_with_colour_blotch(h, w, seed) - 0.115     # sky median ~0.005
    yy, xx = np.mgrid[0:h, 0:w]
    rng = np.random.default_rng(seed)
    for k in range(12):
        cy, cx = rng.uniform(10, h - 10), rng.uniform(10, w - 10)
        col = (np.array([1.0, 0.25, 0.05]) if k % 2 else np.array([0.1, 0.4, 1.0]))
        rgb += (np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 2.0 ** 2))[..., None]
                * col).astype(np.float32)
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


_HARD = {"strength": 1.0, "protect_stars": False, "radius": 12.0}


def test_after_the_stretch_it_never_pushes_a_channel_out_of_the_display_range():
    """Run after the stretch — where Auto puts it — the op is working on a
    display-space ``[0, 1]`` picture, and the editor export writes that picture
    as a FITS stamped "display-space [0,1]". Blurring the chroma of a near-black
    sky pulled single channels below 0 (and a saturated star's above 1), which
    the PNG/TIFF then clipped: the clip changes that pixel's luminance and hue,
    the one thing this op promises never to do. Measured before the fix on this
    picture: a min of −0.023, on about a third of its pixels."""
    rgb = _near_black_sky_with_coloured_stars()
    assert rgb.min() >= 0.0 and rgb.max() <= 1.0
    out = get_op(OP).apply(rgb, _HARD, EditContext(stage="nonlinear"))
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0
    # …and it does that by holding the colour change back, never by clipping:
    # the luminance is still the input's.
    assert float(np.max(np.abs(luminance(out) - luminance(rgb)))) < 1e-6


def test_the_range_guard_reaches_the_editor_through_a_recipe():
    """The pipeline is what tells the op it is past the stretch (``ctx.stage``),
    so pin the real path a preview and an export take, not just the op."""
    from seestack.edit.pipeline import apply_recipe
    from seestack.edit.recipe import OpInstance, Recipe

    rgb = _near_black_sky_with_coloured_stars()
    recipe = Recipe(ops=[
        OpInstance("tone.levels", {"black": 0.0, "white": 1.0, "gamma": 1.0}),
        OpInstance(OP, dict(_HARD)),
    ])
    out = apply_recipe(rgb, recipe, EditContext(already_display=True))
    assert float(np.nanmin(out)) >= 0.0 and float(np.nanmax(out)) <= 1.0

    linear = np.clip(rgb, 1e-4, None) ** 2.2
    recipe = Recipe(ops=[OpInstance("tone.stretch", {"mode": "stf"}), OpInstance(OP, dict(_HARD))])
    out = apply_recipe(linear, recipe, EditContext())
    assert float(np.nanmin(out)) >= 0.0 and float(np.nanmax(out)) <= 1.0


def test_pixels_the_range_guard_does_not_need_are_left_exactly_as_before():
    """The guard only ever holds back a pixel that would have left the range, so
    every other pixel — the whole sky of an ordinary picture — is byte-for-byte
    what the op always produced; and on linear data, before the stretch, where
    ``[0, 1]`` is no bound at all, nothing changes."""
    rgb = _near_black_sky_with_coloured_stars()
    linear_ctx = get_op(OP).apply(rgb, _HARD, EditContext())
    display = get_op(OP).apply(rgb, _HARD, EditContext(stage="nonlinear"))
    in_range = ((linear_ctx >= 0.0) & (linear_ctx <= 1.0)).all(axis=-1)
    assert in_range.mean() > 0.5 and not in_range.all()
    assert np.array_equal(display[in_range], linear_ctx[in_range])
    # Before the stretch it is the unbounded op it always was.
    assert float(linear_ctx.min()) < 0.0


def test_the_range_guard_keeps_mosaic_gaps_nan():
    rgb = _near_black_sky_with_coloured_stars()
    rgb[:, 120:140] = np.nan
    out = get_op(OP).apply(rgb, _HARD, EditContext(stage="nonlinear"))
    assert np.isnan(out[:, 120:140]).all()
    fin = out[np.isfinite(out)]
    assert np.isfinite(out[:, :120]).all() and np.isfinite(out[:, 140:]).all()
    assert fin.min() >= 0.0 and fin.max() <= 1.0
