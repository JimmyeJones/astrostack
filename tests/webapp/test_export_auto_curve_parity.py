"""The editor export applies the auto-contrast curve the live preview showed.

``tone.curves`` with ``auto`` on — the last tonal op of every one-click Auto
recipe — derives its control points at apply time from the image entering it,
and :func:`seestack.edit.curve.suggest_tone_curve`'s midtone lift is gated on the
median sitting ``_MIN_GAP`` above the sky's histogram mode. The preview measures
that on the strided proxy and the export measured it again on the full canvas;
the mode wobbles by ~0.01 between two samplings of one picture, and on a mosaic
the gap lands right on the gate, so the two took different branches. Measured on
a 2×2 mosaic canvas (1800×2600, proxy step 2) with two taste profiles: the export's
median came out **0.028 brighter** than the preview the user approved, while
every other op agreed to ≤0.002. ``_render_recipe_fullres`` now measures the
curve on the preview's own proxy view and freezes it into the export.

The fixture here makes the two samplings disagree *deterministically* rather than
by noise: the pixels the proxy samples carry an object, the rest are sky, so the
proxy's median clears the gate and the full canvas's does not.
"""
from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.edit.curve import fallback_tone_curve, suggest_tone_curve
from seestack.edit.ops.tone import _curves
from seestack.edit.proxy import PROXY_MAX_PX, build_proxy, proxy_step
from seestack.edit.recipe import OpInstance, Recipe
from seestack.edit.registry import EditContext
from seestack.stack.output import DISPLAY_SPACE_CARD
from webapp.pipeline import _preview_curve_fits, _render_recipe_fullres

_W = PROXY_MAX_PX + 100  # just over the cap ⇒ the proxy strides by 2
_H = 60


def _split_scene(seed: int = 0) -> np.ndarray:
    """Display-space RGB whose proxy grid (``[::2, ::2]``) is half object, half sky,
    while the other three quarters of the pixels are all sky."""
    rng = np.random.default_rng(seed)
    img = 0.15 + rng.normal(0.0, 0.01, (_H, _W)).astype(np.float32)
    grid = img[::2, ::2]
    obj = rng.random(grid.shape) < 0.55
    grid[obj] += rng.uniform(0.05, 0.25, int(obj.sum())).astype(np.float32)
    img[::2, ::2] = grid
    img[:2, :40] = 0.95  # a few saturated "stars" set the highlight end
    return np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, 1.0).astype(np.float32)


def _write(tmp_path, rgb: np.ndarray, *, display: bool = True) -> str:
    hdr = fits.Header()
    if display:
        hdr[DISPLAY_SPACE_CARD] = True
    path = tmp_path / "edit.fits"
    fits.writeto(path, np.transpose(rgb, (2, 0, 1)), hdr, overwrite=True)
    return str(path)


def _auto_curve_recipe(points=None) -> Recipe:
    return Recipe(ops=[OpInstance(id="tone.curves", params={
        "points": points or [[0.0, 0.0], [1.0, 1.0]], "auto": True})])


def test_the_fixture_puts_preview_and_full_canvas_on_different_branches():
    """The premise: without it the parity test below could pass on the bug."""
    rgb = _split_scene()
    step = proxy_step(*rgb.shape[:2])
    assert step == 2
    assert suggest_tone_curve(rgb[::step, ::step]) is not None
    assert suggest_tone_curve(rgb) is None


def test_export_applies_the_preview_s_auto_contrast_curve(tmp_path):
    rgb = _split_scene()
    path = _write(tmp_path, rgb)
    proxy, scale = build_proxy(path)
    assert scale == 2.0

    recipe = _auto_curve_recipe()
    # What the live preview applies: the curve measured on the proxy.
    preview_pts = suggest_tone_curve(proxy)
    expected = _curves(rgb, {"points": preview_pts}, EditContext())

    out, _ = _render_recipe_fullres(path, recipe.to_dict(), lambda *a: None)

    # Before the fix the export measured its own (fallback) curve on the full canvas.
    wrong = _curves(rgb, {"points": fallback_tone_curve(rgb)}, EditContext())
    assert not np.allclose(expected, wrong, atol=1e-3)
    np.testing.assert_allclose(out, expected, atol=1e-6)
    # And it is the preview's *look*: the median the user approved, not 0.0x off.
    assert abs(float(np.median(out[::2, ::2])) - float(np.median(
        _curves(proxy, {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True},
                EditContext(proxy_scale=scale, is_proxy=True))))) < 1e-6


def test_a_hand_shaped_curve_is_not_replaced(tmp_path):
    """Auto-contrast only engages on the untouched identity line; a curve the user
    drew is applied as drawn, and nothing is measured for it."""
    rgb = _split_scene()
    path = _write(tmp_path, rgb)
    pts = [[0.0, 0.0], [0.3, 0.4], [1.0, 1.0]]
    recipe = _auto_curve_recipe(pts)
    assert _preview_curve_fits(rgb, recipe, None, None, True) is None
    out, _ = _render_recipe_fullres(path, recipe.to_dict(), lambda *a: None)
    np.testing.assert_allclose(out, _curves(rgb, {"points": pts}, EditContext()),
                               atol=1e-6)


def test_no_auto_curve_means_no_proxy_pass():
    recipe = Recipe(ops=[OpInstance(id="tone.saturation", params={"amount": 1.2})])
    assert _preview_curve_fits(_split_scene(), recipe, None, None, True) is None
    off = Recipe(ops=[OpInstance(id="tone.curves", enabled=False, params={
        "points": [[0.0, 0.0], [1.0, 1.0]], "auto": True})])
    assert _preview_curve_fits(_split_scene(), off, None, None, True) is None


def test_only_the_curve_points_are_frozen():
    """Every other op still measures itself at full size — the carry is the curve
    and nothing else, keyed to that op instance."""
    rgb = _split_scene()
    recipe = Recipe(ops=[
        OpInstance(id="tone.levels", params={"black": 0.0, "white": 1.0, "gamma": 1.0}),
        OpInstance(id="tone.curves", params={
            "points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}),
    ])
    fits_ = _preview_curve_fits(rgb, recipe, None, None, True)
    assert fits_ is not None
    assert set(fits_) == {f"{recipe.ops[1].uid}:points"}
    assert fits_[f"{recipe.ops[1].uid}:points"] == suggest_tone_curve(rgb[::2, ::2])


def test_a_failed_measurement_falls_back_to_full_size(monkeypatch, tmp_path):
    import seestack.edit.pipeline as pl

    def boom(*a, **k):
        raise RuntimeError("no proxy today")

    monkeypatch.setattr(pl, "apply_recipe", boom)
    rgb = _split_scene()
    path = _write(tmp_path, rgb)
    out, _ = _render_recipe_fullres(path, _auto_curve_recipe().to_dict(),
                                    lambda *a: None)
    np.testing.assert_allclose(
        out, _curves(rgb, {"points": fallback_tone_curve(rgb)}, EditContext()),
        atol=1e-6)


def test_proxy_step_is_the_stride_build_proxy_uses(tmp_path):
    for shape in [(100, 200), (PROXY_MAX_PX, 10), (10, PROXY_MAX_PX + 1),
                  (3 * PROXY_MAX_PX + 1, 50)]:
        arr = np.zeros(shape + (3,), dtype=np.float32)
        path = _write(tmp_path, arr, display=False)
        _, scale = build_proxy(path)
        assert proxy_step(*shape) == int(scale)
