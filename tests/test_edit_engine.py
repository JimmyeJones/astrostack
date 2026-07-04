"""Editor engine: ops behaviour, pipeline ordering, recipe validation, proxy cache."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from seestack.edit.pipeline import apply_recipe, has_stretch
from seestack.edit.proxy import (
    PROXY_MAX_PX, build_proxy, clear_proxy, coverage_path_for, get_proxy,
    load_coverage,
)
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


def test_enum_params_carry_friendly_option_labels():
    # Every enum control shows friendly display names for *all* its raw option
    # values (e.g. "Wavelet (recommended)" not "wavelet"), so no dropdown exposes a
    # bare engine id — an invariant so a future enum op can't ship jargon options.
    for s in all_specs():
        for p in s.params:
            if p.type != "enum":
                continue
            assert p.option_labels, f"{s.id}.{p.key} enum needs friendly option_labels"
            for opt in p.options or []:
                assert p.option_labels.get(opt), \
                    f"{s.id}.{p.key} option {opt!r} needs a friendly label"


def test_wavelet_denoise_actually_runs_wavelet():
    # PyWavelets must be installed so scikit-image's denoise_wavelet works —
    # otherwise the default "Wavelet (recommended)" denoise silently fell back to
    # a (mislabelled, double-strengthed) TV denoise. Guard both: the import works,
    # and the wavelet method gives a genuinely different result from TV.
    import importlib
    assert importlib.util.find_spec("pywt") is not None, "PyWavelets must be a hard dep"
    from skimage import restoration
    norm = (np.random.default_rng(0).random((32, 32, 3)) * 0.3 + 0.1).astype("float32")
    restoration.denoise_wavelet(norm, channel_axis=-1, rescale_sigma=True,
                                method="BayesShrink", mode="soft")  # must not raise

    op = get_op("detail.denoise")
    base = np.clip(np.nan_to_num(_img(nan_band=0)), 0, 1)
    wav = op.apply(base, {"method": "wavelet", "strength": 0.6}, EditContext())
    tv = op.apply(base, {"method": "tv", "strength": 0.6}, EditContext())
    assert not np.allclose(wav, base, atol=1e-4)      # it actually denoises
    assert not np.allclose(wav, tv, atol=1e-4)        # wavelet ≠ the TV fallback


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


def test_uncovered_pixels_stay_nan_through_the_stretch():
    # "NaN = no coverage" must survive the stretch (and the whole recipe), so the
    # histogram and Levels suggestions exclude uncovered mosaic pixels instead of
    # counting them as real black. The PNG/TIFF encoders fill NaN->black at the end.
    img = _img(nan_band=8)
    # background subtract is linear and must keep NaN where uncovered
    bg = get_op("background.subtract").apply(img, {"mode": "per_channel", "box_size": 32},
                                             EditContext())
    assert np.isnan(bg[:8]).any()
    rec = Recipe(ops=validate_ops([
        OpInstance(id="background.subtract", params={"box_size": 32}),
        OpInstance(id="tone.stretch", params={"stretch": 0.5}),
    ]))
    out = apply_recipe(img, rec, EditContext())
    assert np.isnan(out[:8]).all()         # uncovered border stays NaN
    assert np.isfinite(out[8:]).all()      # covered region is finite display data
    # Same via the auto-stretch fallback (no explicit stretch op).
    out2 = apply_recipe(img, Recipe(ops=validate_ops([
        OpInstance(id="background.subtract", params={"box_size": 32})])), EditContext())
    assert np.isnan(out2[:8]).all()


def test_uncovered_pixels_excluded_from_histogram_after_stretch():
    # Regression: uncovered pixels must be EXCLUDED from the post-stretch histogram
    # (before the fix the stretch turned them into 0.0 and they piled into bin 0,
    # tripping a false "shadows are clipping" warning). The count must equal the
    # covered-pixel count, not the whole frame.
    from seestack.edit.histogram import compute_histogram
    h, w, band = 60, 80, 24            # top 24 of 60 rows uncovered = 40%
    img = _img(h=h, w=w, nan_band=band)
    covered = (h - band) * w
    rec = Recipe(ops=validate_ops([OpInstance(id="tone.stretch", params={"stretch": 0.5})]))
    out = apply_recipe(img, rec, EditContext())
    hist = compute_histogram(out)
    assert sum(hist["g"]) == covered   # would be h*w (all pixels) with the bug


def test_recipe_validation_drops_unknown_and_clamps():
    rec = recipe_from_dict({"ops": [
        {"id": "tone.stretch", "params": {"stretch": 5.0}},   # clamp to 1.0
        {"id": "nope", "params": {}},                          # dropped
        {"id": "tone.saturation", "params": {"amount": 1.5}},
    ]})
    assert [o.id for o in rec.ops] == ["tone.stretch", "tone.saturation"]
    assert rec.ops[0].params["stretch"] == 1.0


@pytest.mark.parametrize("bad_params", [["x", "y", "z"], "abc", 123, None])
def test_recipe_validation_tolerates_non_mapping_params(bad_params):
    # A malformed body (or hand-built recipe) can send ``params`` as a list /
    # string / number instead of an object. It must not raise (that was an
    # unhandled 500 in put_recipe / create_preset / the export jobs) — the op is
    # kept with its schema defaults, exactly as if params were omitted.
    rec = recipe_from_dict({"ops": [{"id": "tone.curves", "params": bad_params}]})
    assert [o.id for o in rec.ops] == ["tone.curves"]
    assert rec.ops[0].params == get_op("tone.curves").defaults()


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


def test_auto_recipe_saturation_eases_off_on_noisy_stacks():
    """Auto's saturation boost should be data-driven — a noisy stack gets a
    gentler boost (chroma noise scales with saturation) than a clean one, not the
    same fixed 1.2. Falls back to 1.2 when the image can't be measured."""
    from seestack.edit.presets import auto_recipe

    rng = np.random.default_rng(11)
    base = np.full((80, 100, 3), 0.05, np.float32)
    base[30:50, 40:60] += 0.5
    clean = base.copy()
    noisy = base + rng.normal(0, 0.06, base.shape).astype("float32")

    def sat_amount(rgb):
        op = next(o for o in auto_recipe(rgb).ops if o.id == "tone.saturation")
        return float(op.params["amount"])

    s_clean = sat_amount(clean)
    s_noisy = sat_amount(noisy)
    assert s_noisy < s_clean          # noisy → gentler colour boost
    assert 1.05 <= s_noisy <= 1.25    # stays within a sensible band
    assert 1.05 <= s_clean <= 1.25
    # No image to measure → the neutral 1.2 fallback.
    op = next(o for o in auto_recipe(None).ops if o.id == "tone.saturation")
    assert float(op.params["amount"]) == 1.2


def test_noise_fraction_crossfade_math():
    """The crossfade weight is 0 at/below the clean end, 1 at/above the noisy end,
    and monotone linear in between."""
    from seestack.edit.presets import _NOISE_HI, _NOISE_LO, _noise_fraction

    assert _noise_fraction(0.0) == 0.0
    assert _noise_fraction(_NOISE_LO) == 0.0
    assert _noise_fraction(_NOISE_HI) == 1.0
    assert _noise_fraction(1.0) == 1.0
    mid = _noise_fraction((_NOISE_LO + _NOISE_HI) / 2)
    assert 0.4 < mid < 0.6
    xs = [0.0, 0.005, _NOISE_LO, 0.016, 0.02, 0.024, _NOISE_HI, 0.04]
    fracs = [_noise_fraction(x) for x in xs]
    assert fracs == sorted(fracs)  # non-decreasing


def test_auto_recipe_denoise_sharpen_crossfade():
    """A mildly-noisy stack should get *both* a light denoise and a light sharpen
    (the crossfade band), and as the noise rises the denoise strength increases
    while the sharpen amount decreases — no abrupt one-or-the-other cliff."""
    from seestack.edit.presets import auto_recipe

    base = np.full((80, 100, 3), 0.05, np.float32)
    base[30:50, 40:60] += 0.5

    def ops_for(sig):
        rng = np.random.default_rng(3)
        img = base + rng.normal(0, sig, base.shape).astype("float32")
        recipe = auto_recipe(img)
        dn = next((o for o in recipe.ops if o.id == "detail.denoise"), None)
        sh = next((o for o in recipe.ops if o.id == "detail.sharpen"), None)
        return (None if dn is None else float(dn.params["strength"]),
                None if sh is None else float(sh.params["amount"]))

    # A mid-band stack carries BOTH ops (the whole point of the crossfade).
    dn_mid, sh_mid = ops_for(0.03)
    assert dn_mid is not None and sh_mid is not None
    assert dn_mid > 0 and sh_mid > 0

    # Sweep the band: denoise rises, sharpen falls (both monotone).
    sigs = [0.025, 0.03, 0.035]
    dns = [ops_for(s)[0] for s in sigs]
    shs = [ops_for(s)[1] for s in sigs]
    assert all(a is not None for a in dns) and all(a is not None for a in shs)
    assert dns == sorted(dns)              # denoise strengthens with noise
    assert shs == sorted(shs, reverse=True)  # sharpen weakens with noise


def test_auto_recipe_levels_coverage_only_for_mosaics():
    """Auto prepends a coverage-leveling pass (before the gradient fit) only when
    the run is a mosaic (coverage_max > coverage_min); a single-field stack
    (uniform coverage) and an unknown span leave the recipe unchanged."""
    from seestack.edit.presets import auto_recipe

    clean = np.full((80, 100, 3), 0.05, np.float32)
    clean[30:50, 40:60] += 0.5

    def ids(span):
        return [o.id for o in auto_recipe(clean, coverage_span=span).ops]

    # Mosaic: the pass is present and runs on linear data, before the gradient
    # removal and the stretch.
    mosaic_ids = ids((1, 6))
    assert "background.level_coverage" in mosaic_ids
    assert mosaic_ids.index("background.level_coverage") < mosaic_ids.index("background.final_gradient")
    assert mosaic_ids.index("background.level_coverage") < mosaic_ids.index("tone.stretch")

    # Single-field (uniform coverage) and unknown span → unchanged (no leveling).
    assert "background.level_coverage" not in ids((3, 3))
    assert "background.level_coverage" not in ids(None)


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


def test_deconv_understates_flag_matches_the_weak_preview():
    """The deconvolution live preview genuinely understates the full-res export
    on a heavily-decimated proxy — its PSF collapses to the floor and the
    Richardson-Lucy kernel barely acts. ``deconv_understates_on_proxy`` must
    flag exactly that case so the editor can caption it honestly.

    Regression for the top editor bug: preview shows almost nothing while the
    export changes a lot, with no notice to the user.
    """
    from seestack.edit.ops.detail import deconv_understates_on_proxy

    # A star field, so there's real sub-pixel structure for deconv to sharpen.
    rng = np.random.default_rng(1)
    full = np.full((60, 60, 3), 0.2, np.float32)
    for _ in range(25):
        y, x = rng.integers(3, 57, size=2)
        full[y - 1:y + 2, x - 1:x + 2] += 0.5
    spec = get_op("detail.deconvolve")
    params = {"iterations": 10, "psf_sigma": 1.5}  # the defaults

    # Export (proxy_scale=1): a real, visible deconvolution.
    exported = spec.apply(full.copy(), params, EditContext(proxy_scale=1.0))
    export_effect = float(np.nanmean(np.abs(exported - full)))

    # Heavily-decimated preview proxy (proxy_scale=4, e.g. a wide mosaic): the
    # PSF collapses and the effect is a fraction of the export's.
    proxy = full[::4, ::4].copy()
    previewed = spec.apply(
        proxy, params, EditContext(proxy_scale=4.0, is_proxy=True))
    preview_effect = float(np.nanmean(np.abs(previewed - proxy)))

    assert export_effect > 0.005                       # export clearly deconvolves
    assert preview_effect < export_effect * 0.5        # preview understates it a lot
    # ...and the helper flags exactly this misleading case, but not the export.
    assert deconv_understates_on_proxy(1.5, 4.0) is True
    assert deconv_understates_on_proxy(1.5, 1.0) is False


def test_deconv_understates_on_proxy_rule():
    from seestack.edit.ops.detail import deconv_understates_on_proxy

    # Export (scale <= 1) never understates.
    assert deconv_understates_on_proxy(1.5, 1.0) is False
    assert deconv_understates_on_proxy(0.5, 1.0) is False
    # Default PSF on a 4x-decimated proxy collapses (1.5/4 = 0.375 < 0.4 floor).
    assert deconv_understates_on_proxy(1.5, 4.0) is True
    # A mild 2x proxy keeps the default PSF above the floor (1.5/2 = 0.75).
    assert deconv_understates_on_proxy(1.5, 2.0) is False
    # A wide PSF survives even heavy decimation (3.0/4 = 0.75 >= 0.4).
    assert deconv_understates_on_proxy(3.0, 4.0) is False
    # Degenerate inputs are safe (no false alarms).
    assert deconv_understates_on_proxy(0.0, 4.0) is False
    assert deconv_understates_on_proxy(float("nan"), 4.0) is False
    assert deconv_understates_on_proxy(1.5, float("inf")) is False


def test_hot_pixels_works_on_mosaic_nan_image():
    """The hot-pixel editor op must remove hot pixels even on a partial-coverage
    (NaN) mosaic — and preserve NaN. Regression: it used to derive its threshold
    from the whole-image residual median, which is NaN when any pixel is
    uncovered, silently turning the op into a no-op on every mosaic."""
    rng = np.random.default_rng(0)
    img = (rng.random((40, 40, 3), dtype=np.float32) * 0.2)
    img[10, 10] = 5.0                          # a hot pixel, far above its neighbours
    img[:5, :, :] = np.nan                      # uncovered mosaic border
    spec = get_op("detail.hot_pixels")

    out = spec.apply(img.copy(), {"sigma": 5.0}, EditContext())
    assert out[10, 10, 0] < 1.0                 # the hot pixel was actually suppressed
    assert np.isnan(out[:5]).all()              # uncovered border stays NaN
    assert not np.isnan(out[5:]).any()          # NaN never leaks into covered pixels

    # Still a faithful suppressor on a fully-covered image (unchanged behaviour).
    full = (rng.random((40, 40, 3), dtype=np.float32) * 0.2)
    full[20, 25] = 5.0
    out_full = spec.apply(full.copy(), {"sigma": 5.0}, EditContext())
    assert out_full[20, 25, 0] < 1.0


@pytest.mark.parametrize("op_id,params", [
    ("detail.denoise", {"method": "wavelet", "strength": 0.7}),
    ("detail.sharpen", {"amount": 1.0, "radius": 2.0}),
    ("detail.deconvolve", {"iterations": 3, "psf_sigma": 1.2}),
])
def test_detail_ops_preserve_nan_on_partial_coverage(op_id, params):
    """Every spatial detail op runs on a NaN-filled copy (skimage can't tolerate
    NaN) and must restore the uncovered border as NaN — never bleeding a filled
    value into an uncovered pixel, and never leaving NaN inside covered pixels.
    Guards the fragile fill→process→restore contract in `_with_nan_filled`."""
    rng = np.random.default_rng(1)
    img = (rng.random((30, 40, 3), dtype=np.float32) * 0.3)
    img[:6, :, :] = np.nan                      # uncovered (mosaic) border
    out = get_op(op_id).apply(img.copy(), params, EditContext())
    assert np.isnan(out[:6]).all()              # uncovered border stays NaN
    assert not np.isnan(out[6:]).any()          # covered region is fully finite


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


def test_background_ops_surface_fit_failure_in_editor(monkeypatch):
    """A failed Background2D fit must surface as an editor op error, not a silent
    no-op. Regression: the editor bg wrappers used to return the input unchanged
    (or partially subtract, colour-shifting) when the fit failed, so the
    v0.61.11 "surface failed ops" contract never saw the bg ops' likeliest
    failure."""
    import photutils.background as pb

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("degenerate tile")

    monkeypatch.setattr(pb, "Background2D", _Boom)
    img = _img(nan_band=0)

    # Every editor bg op (both modes) raises so apply_recipe collects the failure.
    for op_id, params in (
        ("background.subtract", {"mode": "per_channel"}),
        ("background.subtract", {"mode": "luminance"}),
        ("background.final_gradient", {"mode": "per_channel"}),
        ("background.final_gradient", {"mode": "luminance"}),
    ):
        with pytest.raises(RuntimeError):
            get_op(op_id).apply(img.copy(), params, EditContext(use_gpu=False))

    # Surfaced through the pipeline's error collector, not swallowed.
    rec = Recipe(ops=validate_ops([OpInstance(id="background.subtract", params={})]))
    errors: list[str] = []
    apply_recipe(img.copy(), rec, EditContext(use_gpu=False), errors=errors)
    assert any("fit failed" in e.lower() for e in errors)


def test_background_stack_path_stays_best_effort_on_fit_failure(monkeypatch):
    """The stack path (no errors collector) keeps its resilient skip-and-continue
    behaviour when a fit fails — the opt-in surfacing must not change it."""
    import photutils.background as pb

    from seestack.bg.per_frame import BackgroundOptions, subtract_background

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("degenerate tile")

    monkeypatch.setattr(pb, "Background2D", _Boom)
    img = _img(nan_band=0)
    # No errors= → returns an array without raising (best-effort, unchanged).
    out = subtract_background(
        img.copy(), BackgroundOptions(mode="per_channel", enabled=True), use_gpu=False)
    assert out.shape == img.shape and np.isfinite(out).any()


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


def test_rotate_expand_param_controls_canvas_size():
    """The rotate op's ``expand`` param must actually control whether the canvas
    grows to fit the rotated frame (default) or keeps the original size — it's a
    registered param, not a dead read."""
    spec = get_op("geometry.rotate")
    assert any(p.key == "expand" for p in spec.params)  # the param is exposed
    img = _img(80, 120, nan_band=0)
    # Default (expand=True): a 30° rotation grows the canvas to fit the frame.
    grown = spec.apply(img, {"angle": 30.0}, EditContext())
    assert grown.shape[0] > img.shape[0] and grown.shape[1] > img.shape[1]
    # expand=False keeps the original size (rotated corners fall outside).
    same = spec.apply(img, {"angle": 30.0, "expand": False}, EditContext())
    assert same.shape[:2] == img.shape[:2]


def test_scaled_px_shrinks_on_proxy_only():
    """proxy_scale rescales full-res pixel measures for the preview, no-op on export."""
    assert EditContext(proxy_scale=1.0).scaled_px(4.0) == 4.0      # export: unchanged
    assert EditContext(proxy_scale=4.0).scaled_px(4.0) == 1.0      # 4x proxy: 1/4
    # A proxy_scale below 1 never *grows* a radius (guarded at 1.0).
    assert EditContext(proxy_scale=0.5).scaled_px(4.0) == 4.0


def test_sharpen_radius_scaled_to_proxy(monkeypatch):
    """The sharpen radius is a full-res pixel measure; on the decimated preview
    proxy it must be shrunk by proxy_scale so the preview matches the full-res
    export (preview↔export parity). We capture the sigma handed to the Gaussian
    (sharpen is a per-channel unsharp mask, so it blurs each channel once)."""
    import scipy.ndimage as ndi

    seen: list[float] = []
    real_gaussian = ndi.gaussian_filter

    def fake_gaussian(img, *, sigma, **kw):
        seen.append(float(sigma))
        return real_gaussian(img, sigma=sigma, **kw)

    monkeypatch.setattr(ndi, "gaussian_filter", fake_gaussian)
    spec = get_op("detail.sharpen")
    img = _img(20, 20, nan_band=0)

    spec.apply(img, {"amount": 1.0, "radius": 4.0}, EditContext(proxy_scale=1.0))
    spec.apply(img, {"amount": 1.0, "radius": 4.0}, EditContext(proxy_scale=2.0))
    spec.apply(img, {"amount": 1.0, "radius": 4.0}, EditContext(proxy_scale=4.0))
    # full-res keeps radius 4; a 2x proxy halves it; a 4x proxy quarters it.
    # Three channels per apply → the same sigma three times each.
    assert seen == [4.0] * 3 + [2.0] * 3 + [1.0] * 3


def test_background_subtract_box_scaled_to_proxy(monkeypatch):
    """The background-subtract box_size is a full-res pixel measure, so on the
    decimated preview proxy it must shrink by proxy_scale to keep the gradient
    mesh at the same physical scale as the export (preview↔export parity)."""
    import seestack.bg.per_frame as pf

    seen: list[int] = []

    def fake_subtract(rgb, opts, *, use_gpu=None, errors=None):
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

    def fake_remove(rgb, opts, *, errors=None):
        seen.append((int(opts.box_size), int(opts.dilate_px)))
        return rgb

    monkeypatch.setattr(fg, "remove_final_gradient", fake_remove)
    spec = get_op("background.final_gradient")
    img = _img(20, 20, nan_band=0)

    spec.apply(img, {"box_size": 256, "dilate_px": 16}, EditContext(proxy_scale=1.0))
    spec.apply(img, {"box_size": 256, "dilate_px": 16}, EditContext(proxy_scale=4.0))
    # export unchanged; a 4x proxy quarters both spatial measures.
    assert seen == [(256, 16), (64, 4)]


def test_load_coverage_reads_sibling_and_strides_for_proxy(tmp_path):
    """The per-pixel coverage map lives in a sibling {basename}_coverage.fits; the
    editor loads it into EditContext so the Coverage-leveling op actually works,
    striding it by the proxy step so it lines up with a decimated preview."""
    cov = np.arange(80 * 60, dtype=np.float32).reshape(80, 60)
    fits_path = tmp_path / "stack_M42.fits"
    cov_path = coverage_path_for(fits_path)
    assert cov_path.name == "stack_M42_coverage.fits"
    fits.PrimaryHDU(data=cov).writeto(cov_path)

    full = load_coverage(fits_path)
    assert full is not None and full.shape == (80, 60)
    assert np.array_equal(full, cov)

    # Strided by the proxy step, exactly like build_proxy decimates the image.
    proxied = load_coverage(fits_path, step=4)
    assert proxied.shape == cov[::4, ::4].shape
    assert np.array_equal(proxied, cov[::4, ::4])


def test_load_coverage_returns_none_for_single_field_image(tmp_path):
    # No coverage sibling → the op has nothing to level against, so None (the op's
    # None-guard then makes it a clean no-op rather than a dead control).
    assert load_coverage(tmp_path / "single_field.fits") is None


def test_star_reduce_erosion_footprint_scaled_to_proxy(monkeypatch):
    """The star-reduction erosion footprint is built from a full-res `size`, so on
    the decimated preview proxy it must shrink by proxy_scale to match the full-res
    export (the star-mask gate already does — preview↔export parity). We capture
    the footprint side-length handed to grey_erosion. protect_nebula is off so the
    star mask isn't involved and only the footprint scaling is under test."""
    import scipy.ndimage as ndi

    seen: list[int] = []

    def fake_erosion(chan, *, footprint):
        seen.append(int(footprint.shape[0]))
        return chan  # identity — we only care about the footprint size

    monkeypatch.setattr(ndi, "grey_erosion", fake_erosion)
    spec = get_op("stars.reduce")
    img = _img(20, 20, nan_band=0)

    params = {"amount": 0.5, "size": 4, "protect_nebula": False}
    spec.apply(img, params, EditContext(proxy_scale=1.0))   # size 4 → (2*4+1)=9
    spec.apply(img, params, EditContext(proxy_scale=2.0))   # →2 → (2*2+1)=5
    spec.apply(img, params, EditContext(proxy_scale=4.0))   # →1 → (2*1+1)=3
    # grey_erosion runs once per channel (3×); the footprint side matches per scale.
    assert seen == [9, 9, 9, 5, 5, 5, 3, 3, 3]


# ---- apply_geometry_to_map (coverage overlay follows the recipe geometry) ----

def test_apply_geometry_to_map_crop_follows_recipe():
    """A recipe's enabled crop op reshapes a 2-D coverage map to the same
    fractional rectangle the edited image gets, preserving NaN = uncovered."""
    from seestack.edit.ops.geometry import apply_geometry_to_map

    cov = np.ones((80, 100), dtype=np.float32)
    cov[0, 0] = np.nan  # an uncovered corner that the crop removes
    rec = Recipe(ops=validate_ops([
        OpInstance(id="geometry.crop",
                   params={"x0": 0.25, "y0": 0.25, "x1": 0.75, "y1": 0.75}),
    ]))
    out = apply_geometry_to_map(cov, rec, EditContext())
    # cropped to the central 50% × 50% of a 100×80 frame
    assert out.shape == (40, 50)
    assert np.isfinite(out).all()  # the NaN corner was cropped away
    assert cov.shape == (80, 100)  # input not mutated


def test_apply_geometry_to_map_ignores_tone_ops_and_disabled_geometry():
    """Only *enabled geometry* ops move the map: tone ops and a disabled crop
    leave it unchanged (same shape, same values)."""
    from seestack.edit.ops.geometry import apply_geometry_to_map

    cov = np.arange(20 * 30, dtype=np.float32).reshape(20, 30)
    rec = Recipe(ops=validate_ops([
        OpInstance(id="tone.stretch", params={"stretch": 0.5}),
        OpInstance(id="geometry.crop", enabled=False,
                   params={"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}),
    ]))
    out = apply_geometry_to_map(cov, rec, EditContext())
    assert out.shape == cov.shape
    assert np.array_equal(out, cov)


def test_apply_geometry_to_map_rotate_fills_corners_with_nan():
    """A rotate op grows the canvas and fills exposed corners with NaN, so the
    coverage overlay's rotated corners read as uncovered (like the image)."""
    from seestack.edit.ops.geometry import apply_geometry_to_map

    cov = np.full((40, 40), 3.0, dtype=np.float32)
    rec = Recipe(ops=validate_ops([
        OpInstance(id="geometry.rotate", params={"angle": 30.0, "expand": True}),
    ]))
    out = apply_geometry_to_map(cov, rec, EditContext())
    assert out.shape[0] > 40 and out.shape[1] > 40  # expanded canvas
    assert not np.isfinite(out[0, 0])  # a corner exposed by the rotation is NaN


# ---- auto_recipe mosaic border trim -----------------------------------------

def test_auto_recipe_appends_trim_crop_last_on_a_mosaic():
    """A meaningful trim rectangle (from a mosaic's coverage) is appended as a
    final geometry.crop, so the one-click result is cleanly framed. The crop runs
    last (after the tone/detail ops) and never before the coverage-leveling op."""
    from seestack.edit.presets import auto_recipe

    rec = auto_recipe(coverage_span=(1, 5), trim_crop=(0.1, 0.12, 0.9, 0.88))
    ids = [op.id for op in rec.ops]
    assert ids[-1] == "geometry.crop"        # trim runs last
    assert ids.index("background.level_coverage") < ids.index("geometry.crop")
    crop = rec.ops[-1]
    assert crop.params["x0"] == 0.1 and crop.params["x1"] == 0.9
    assert crop.params["y0"] == 0.12 and crop.params["y1"] == 0.88


def test_auto_recipe_no_trim_crop_when_none():
    """Without a supplied trim (single-field, or nothing worth trimming) Auto adds
    no crop op — behaviour is unchanged from before the feature."""
    from seestack.edit.presets import auto_recipe

    mosaic_no_trim = auto_recipe(coverage_span=(1, 5), trim_crop=None)
    single_field = auto_recipe(coverage_span=(3, 3), trim_crop=None)
    assert "geometry.crop" not in [op.id for op in mosaic_no_trim.ops]
    assert "geometry.crop" not in [op.id for op in single_field.ops]
