"""Editor engine: ops behaviour, pipeline ordering, recipe validation, proxy cache."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from seestack.edit.pipeline import apply_recipe, has_stretch
from seestack.edit.proxy import PROXY_MAX_PX, build_proxy, clear_proxy, get_proxy
from seestack.edit.recipe import OpInstance, Recipe, recipe_from_dict, validate_ops
from seestack.edit.registry import EditContext, all_specs, get_op


def _img(h=60, w=80, nan_band=8):
    rng = np.random.default_rng(0)
    img = (rng.random((h, w, 3)).astype("float32") * 0.1) + 0.02
    yy, xx = np.mgrid[0:h, 0:w]
    img += (0.5 * np.exp(-(((xx - w / 2) / 6) ** 2 + ((yy - h / 2) / 6) ** 2)))[..., None]
    if nan_band:
        img[:nan_band, :, :] = np.nan
    return img


def test_registry_has_core_ops():
    ids = {s.id for s in all_specs()}
    assert {"tone.stretch", "tone.curves", "tone.levels", "tone.saturation",
            "tone.scnr", "tone.white_balance", "tone.color_calibrate",
            "background.subtract", "background.final_gradient", "detail.denoise",
            "detail.sharpen", "detail.deconvolve", "detail.hot_pixels",
            "stars.reduce", "geometry.crop", "geometry.rotate", "geometry.resize"} <= ids
    assert get_op("tone.stretch").is_stretch is True


def test_curves_identity_is_noop():
    img = _img()
    spec = get_op("tone.curves")
    out = spec.apply(np.clip(np.nan_to_num(img), 0, 1), {"points": [[0, 0], [1, 1]]}, EditContext())
    base = np.clip(np.nan_to_num(img), 0, 1)
    assert np.allclose(out, base, atol=1e-3)


def test_levels_and_saturation_neutral_noop():
    base = np.clip(np.nan_to_num(_img(nan_band=0)), 0, 1)
    lv = get_op("tone.levels").apply(base, {"black": 0.0, "white": 1.0, "gamma": 1.0}, EditContext())
    assert np.allclose(lv, base, atol=1e-3)
    sat = get_op("tone.saturation").apply(base, {"amount": 1.0}, EditContext())
    assert np.allclose(sat, base, atol=1e-3)


def test_curves_monotonic():
    spec = get_op("tone.curves")
    ramp = np.linspace(0, 1, 64, dtype="float32")[None, :, None].repeat(3, axis=2)
    out = spec.apply(ramp, {"points": [[0, 0], [0.3, 0.5], [1, 1]]}, EditContext())
    lum = out[0, :, 0]
    assert np.all(np.diff(lum) >= -1e-4)  # non-decreasing


def test_pipeline_autoinserts_stretch_and_outputs_display_range():
    img = _img()
    rec = Recipe(ops=validate_ops([OpInstance(id="tone.saturation", params={"amount": 1.2})]))
    assert not has_stretch(rec)
    out = apply_recipe(img, rec, EditContext())
    fin = out[np.isfinite(out)]
    assert fin.min() >= 0.0 and fin.max() <= 1.0
    assert fin.max() > 0.0  # not blank


def test_linear_op_preserves_nan_then_stretch_blacks_border():
    img = _img(nan_band=8)
    # background subtract is linear and must keep NaN where uncovered
    bg = get_op("background.subtract").apply(img, {"mode": "per_channel", "box_size": 32},
                                             EditContext())
    assert np.isnan(bg[:8]).any()
    # after a full recipe (which ends in a stretch) the border renders black, not NaN
    rec = Recipe(ops=validate_ops([
        OpInstance(id="background.subtract", params={"box_size": 32}),
        OpInstance(id="tone.stretch", params={"stretch": 0.5}),
    ]))
    out = apply_recipe(img, rec, EditContext())
    assert not np.isnan(out).any()
    assert float(out[:8].max()) < 0.2  # border is dark


def test_recipe_validation_drops_unknown_and_clamps():
    rec = recipe_from_dict({"ops": [
        {"id": "tone.stretch", "params": {"stretch": 5.0}},   # clamp to 1.0
        {"id": "nope", "params": {}},                          # dropped
        {"id": "tone.saturation", "params": {"amount": 1.5}},
    ]})
    assert [o.id for o in rec.ops] == ["tone.stretch", "tone.saturation"]
    assert rec.ops[0].params["stretch"] == 1.0


def test_heavy_op_skipped_in_preview_only():
    img = _img(nan_band=0)
    rec = Recipe(ops=validate_ops([
        OpInstance(id="detail.deconvolve", params={"iterations": 3, "psf_sigma": 1.2}),
        OpInstance(id="tone.stretch", params={}),
    ]))
    assert get_op("detail.deconvolve").proxy_safe is False
    prev = apply_recipe(img, rec, EditContext(is_proxy=True), for_preview=True)
    full = apply_recipe(img, rec, EditContext(is_proxy=False), for_preview=False)
    assert prev.shape == full.shape  # both render; heavy op only runs in full


def test_proxy_build_cache_and_bound(tmp_path):
    h, w = 400, 4000  # wide → must be decimated under PROXY_MAX_PX
    cube = (np.random.default_rng(0).random((3, h, w)) * 0.1).astype("float32")
    fp = tmp_path / "master.fits"
    fits.writeto(fp, cube, overwrite=True)

    rgb, scale = build_proxy(fp)
    assert max(rgb.shape[:2]) <= PROXY_MAX_PX
    assert scale > 1.0

    pdir = tmp_path / "proj"
    (pdir / "cache").mkdir(parents=True)
    a, sa = get_proxy(pdir, 7, fp)
    b, sb = get_proxy(pdir, 7, fp)  # second call hits the cache
    assert a.shape == b.shape and sa == sb
    assert (pdir / "cache" / "edit_proxies" / "run_7.npy").exists()
    clear_proxy(pdir, 7)
    assert not (pdir / "cache" / "edit_proxies" / "run_7.npy").exists()


def test_crop_fraction_consistent_across_scales():
    """A fractional crop selects the same relative region at proxy and full size."""
    spec = get_op("geometry.crop")
    big = _img(120, 160, nan_band=0)
    small = big[::2, ::2]
    params = {"x0": 0.25, "y0": 0.25, "x1": 0.75, "y1": 0.75}
    cb = spec.apply(big, params, EditContext())
    cs = spec.apply(small, params, EditContext())
    # same aspect-relative selection (~half each dimension)
    assert abs(cb.shape[0] / big.shape[0] - 0.5) < 0.05
    assert abs(cs.shape[0] / small.shape[0] - 0.5) < 0.05
