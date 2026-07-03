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


def test_ops_and_key_params_carry_plain_help():
    specs = {s.id: s for s in all_specs()}
    # Every op carries user-facing help text (surfaced in the editor menu/panel).
    for s in specs.values():
        assert s.help and len(s.help) > 10, s.id
    # The formerly-jargon detail/levels ops now explain their key sliders in plain
    # language, so the param panel shows a hint under each control.
    expected_param_help = {
        "detail.denoise": ["method", "strength"],
        "detail.sharpen": ["amount", "radius"],
        "detail.deconvolve": ["iterations", "psf_sigma"],
        "detail.hot_pixels": ["sigma"],
        "tone.levels": ["black", "white", "gamma"],
        "tone.saturation": ["amount"],
        "tone.scnr": ["amount"],
        "tone.color_calibrate": ["mode"],
        "stars.reduce": ["amount", "size"],
        "stars.boost_nebula": ["amount"],
        "background.subtract": ["mode", "box_size"],
        "background.final_gradient": ["mode", "box_size", "detect_sigma", "dilate_px"],
    }
    for op_id, keys in expected_param_help.items():
        params = {p.key: p for p in specs[op_id].params}
        for k in keys:
            assert params[k].help, f"{op_id}.{k} needs plain-language help"

    # Stronger invariant: every editor control carries a plain-language hint, so a
    # beginner never faces a bare slider. The only exception is the curve-editor
    # widget, whose op-level help explains the whole control.
    no_param_help = {("tone.curves", "points")}
    for s in specs.values():
        for p in s.params:
            if (s.id, p.key) in no_param_help:
                continue
            assert p.help, f"{s.id}.{p.key} needs plain-language help"


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


def test_every_op_renders_in_preview():
    # A live preview must show EVERY enabled action — including the heavy
    # deconvolution op, which used to be skipped. What you see = what you export.
    img = _img(nan_band=0)
    decon = OpInstance(id="detail.deconvolve", params={"iterations": 5, "psf_sigma": 1.2})
    stretch = OpInstance(id="tone.stretch", params={})
    with_decon = Recipe(ops=validate_ops([decon, stretch]))
    without = Recipe(ops=validate_ops([stretch]))

    assert get_op("detail.deconvolve").proxy_safe is True  # now previewable

    ctx = lambda: EditContext(is_proxy=True, proxy_scale=3.0)  # noqa: E731
    prev_with = apply_recipe(img, with_decon, ctx(), for_preview=True)
    prev_without = apply_recipe(img, without, ctx(), for_preview=True)
    # The deconvolution visibly changes the preview (it's no longer skipped).
    assert not np.allclose(prev_with, prev_without, atol=1e-4)
    assert np.isfinite(prev_with).all()


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


def test_auto_recipe_adapts_to_noise():
    """Auto-process must read the image, not emit a constant recipe."""
    from seestack.edit.presets import analyze_proxy, auto_recipe

    rng = np.random.default_rng(1)
    smooth = np.full((80, 100, 3), 0.05, np.float32)
    smooth[30:50, 40:60] += 0.5
    noisy = smooth + rng.normal(0, 0.08, smooth.shape).astype("float32")

    assert analyze_proxy(noisy)["noisy"] is True
    assert analyze_proxy(smooth)["noisy"] is False

    s_ids = [o.id for o in auto_recipe(smooth).ops]
    n_ids = [o.id for o in auto_recipe(noisy).ops]
    assert s_ids != n_ids                                  # genuinely adaptive
    assert "detail.denoise" in n_ids and "detail.denoise" not in s_ids
    # denoise (linear) must precede the stretch
    assert n_ids.index("detail.denoise") < n_ids.index("tone.stretch")
    # auto uses the proven per-channel STF, not a hardcoded asinh
    stretch = next(o for o in auto_recipe(noisy).ops if o.id == "tone.stretch")
    assert stretch.params["mode"] == "stf"
    # SCNR (green-cast removal) is always applied, after the stretch and before the
    # saturation boost (so the boost lifts real colour, not the residual green).
    for ids in (s_ids, n_ids):
        assert "tone.scnr" in ids
        assert ids.index("tone.stretch") < ids.index("tone.scnr") < ids.index("tone.saturation")


def test_auto_recipe_denoise_strength_scales_with_noise():
    """Auto's denoise strength should be data-driven — a very noisy stack gets a
    stronger cut than a mildly-noisy one, not the same fixed 0.5."""
    from seestack.edit.presets import auto_recipe

    rng = np.random.default_rng(7)
    base = np.full((80, 100, 3), 0.05, np.float32)
    base[30:50, 40:60] += 0.5
    mild = base + rng.normal(0, 0.035, base.shape).astype("float32")
    heavy = base + rng.normal(0, 0.05, base.shape).astype("float32")

    def denoise_strength(rgb):
        op = next((o for o in auto_recipe(rgb).ops if o.id == "detail.denoise"), None)
        return None if op is None else float(op.params["strength"])

    s_mild = denoise_strength(mild)
    s_heavy = denoise_strength(heavy)
    assert s_mild is not None and s_heavy is not None  # both are noisy enough to denoise
    assert s_heavy > s_mild  # stronger noise → stronger denoise


def test_auto_recipe_sharpen_radius_from_fwhm():
    """Auto's sharpen radius should track the target's own star size (median FWHM
    → Gaussian σ, clamped to the op's step/range), not a fixed 2.0 guess. A clean
    (non-noisy) image gets the sharpen op."""
    import math

    from seestack.edit.presets import auto_recipe

    clean = np.full((80, 100, 3), 0.05, np.float32)
    clean[30:50, 40:60] += 0.5

    def sharpen_radius(fwhm):
        op = next((o for o in auto_recipe(clean, median_fwhm=fwhm).ops
                   if o.id == "detail.sharpen"), None)
        return None if op is None else float(op.params["radius"])

    # No FWHM → the op's neutral 2.0 default.
    assert sharpen_radius(None) == 2.0
    # A measured FWHM maps to ≈ its Gaussian σ, rounded to the op's 0.5 step.
    expected = 6.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    expected = round(round(expected / 0.5) * 0.5, 2)
    assert sharpen_radius(6.0) == expected
    # A bigger FWHM → a bigger radius (sized to the data).
    assert sharpen_radius(9.0) > sharpen_radius(3.0)


def test_denoise_identity_at_zero_and_preserves_colour():
    base = np.empty((40, 50, 3), np.float32)
    for c, lvl in enumerate((0.1, 0.2, 0.3)):
        base[..., c] = lvl
    base += np.random.default_rng(2).normal(0, 0.02, base.shape).astype("float32")
    spec = get_op("detail.denoise")

    ident = spec.apply(base, {"method": "wavelet", "strength": 0.0}, EditContext())
    assert np.allclose(ident, base, atol=1e-6)            # true no-op at 0

    den = spec.apply(base, {"method": "tv", "strength": 0.8}, EditContext())
    # Channel means stay put (no per-channel rescale destroying colour).
    for c, lvl in enumerate((0.1, 0.2, 0.3)):
        assert abs(float(den[..., c].mean()) - lvl) < 0.02


def test_deconvolve_preserves_colour_balance():
    gray = np.full((40, 48, 3), 0.3, np.float32)
    gray[15:25, 20:30] = 0.7                              # a bright blob, equal in all channels
    out = get_op("detail.deconvolve").apply(
        gray, {"iterations": 3, "psf_sigma": 1.2}, EditContext())
    means = [float(out[..., c].mean()) for c in range(3)]
    assert max(means) - min(means) < 0.01                 # no colour shift


def test_pipeline_collects_op_errors(monkeypatch):
    img = _img(nan_band=0)

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(get_op("tone.saturation"), "apply", boom)
    rec = Recipe(ops=validate_ops([
        OpInstance(id="tone.stretch", params={}),
        OpInstance(id="tone.saturation", params={"amount": 1.2}),
    ]))
    errors: list[str] = []
    out = apply_recipe(img, rec, EditContext(), errors=errors)
    assert out is not None and np.isfinite(out).any()      # render still completes
    assert any("kaboom" in e for e in errors)              # failure surfaced, not swallowed


def test_white_balance_is_linear_stage():
    assert get_op("tone.white_balance").stage == "linear"


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


def test_scaled_px_shrinks_on_proxy_only():
    """proxy_scale rescales full-res pixel measures for the preview, no-op on export."""
    assert EditContext(proxy_scale=1.0).scaled_px(4.0) == 4.0      # export: unchanged
    assert EditContext(proxy_scale=4.0).scaled_px(4.0) == 1.0      # 4x proxy: 1/4
    # A proxy_scale below 1 never *grows* a radius (guarded at 1.0).
    assert EditContext(proxy_scale=0.5).scaled_px(4.0) == 4.0


def test_sharpen_radius_scaled_to_proxy(monkeypatch):
    """The sharpen radius is a full-res pixel measure; on the decimated preview
    proxy it must be shrunk by proxy_scale so the preview matches the full-res
    export (preview↔export parity). We capture the radius handed to unsharp_mask."""
    import skimage.filters as skf

    seen: list[float] = []

    def fake_unsharp(img, *, radius, amount, channel_axis):
        seen.append(float(radius))
        return img  # identity — we only care about the radius here

    monkeypatch.setattr(skf, "unsharp_mask", fake_unsharp)
    spec = get_op("detail.sharpen")
    img = _img(20, 20, nan_band=0)

    spec.apply(img, {"amount": 1.0, "radius": 4.0}, EditContext(proxy_scale=1.0))
    spec.apply(img, {"amount": 1.0, "radius": 4.0}, EditContext(proxy_scale=2.0))
    spec.apply(img, {"amount": 1.0, "radius": 4.0}, EditContext(proxy_scale=4.0))
    # full-res keeps radius 4; a 2x proxy halves it; a 4x proxy quarters it.
    assert seen == [4.0, 2.0, 1.0]


def test_background_subtract_box_scaled_to_proxy(monkeypatch):
    """The background-subtract box_size is a full-res pixel measure, so on the
    decimated preview proxy it must shrink by proxy_scale to keep the gradient
    mesh at the same physical scale as the export (preview↔export parity)."""
    import seestack.bg.per_frame as pf

    seen: list[int] = []

    def fake_subtract(rgb, opts, *, use_gpu=None):
        seen.append(int(opts.box_size))
        return rgb

    monkeypatch.setattr(pf, "subtract_background", fake_subtract)
    spec = get_op("background.subtract")
    img = _img(20, 20, nan_band=0)

    spec.apply(img, {"box_size": 128}, EditContext(proxy_scale=1.0))
    spec.apply(img, {"box_size": 128}, EditContext(proxy_scale=2.0))
    spec.apply(img, {"box_size": 128}, EditContext(proxy_scale=4.0))
    # export keeps 128; a 2x proxy halves it; a 4x proxy quarters it.
    assert seen == [128, 64, 32]


def test_final_gradient_box_and_dilate_scaled_to_proxy(monkeypatch):
    """The final-gradient box_size AND dilate_px are full-res pixel measures, so
    both shrink by proxy_scale on the preview proxy for export parity."""
    import seestack.bg.final_gradient as fg

    seen: list[tuple[int, int]] = []

    def fake_remove(rgb, opts):
        seen.append((int(opts.box_size), int(opts.dilate_px)))
        return rgb

    monkeypatch.setattr(fg, "remove_final_gradient", fake_remove)
    spec = get_op("background.final_gradient")
    img = _img(20, 20, nan_band=0)

    spec.apply(img, {"box_size": 256, "dilate_px": 16}, EditContext(proxy_scale=1.0))
    spec.apply(img, {"box_size": 256, "dilate_px": 16}, EditContext(proxy_scale=4.0))
    # export unchanged; a 4x proxy quarters both spatial measures.
    assert seen == [(256, 16), (64, 4)]
