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


def test_wavelet_denoise_still_smooths_the_sky_with_bright_stars_present():
    # Regression: the default/recommended "wavelet" method used to be a near-no-op
    # on any real starfield. BayesShrink sets each subband's soft threshold from
    # the signal variance, so an *unclipped* bright star (norm ≫ 1) inflated that
    # variance and drove the threshold to ~0 — leaving the sky noise essentially
    # untouched (measured ~2% reduction with a star present vs ~90% without).
    # After the fix the wavelet estimate clips the highlights, so the sky is
    # denoised properly while the star pixels are reinstated unchanged.
    op = get_op("detail.denoise")
    rng = np.random.default_rng(42)
    h, w, sky, sigma = 160, 160, 80.0, 4.0
    img = (sky + rng.standard_normal((h, w, 3)) * sigma).astype("float32")
    # A realistic *sparse* set of bright single-pixel stars (< 0.5% of pixels, so
    # the 99.5th-percentile normalisation ceiling lands in the sky, and the stars
    # are the norm≫1 outliers that poisoned BayesShrink) — all in the right half,
    # leaving the left half a guaranteed star-free patch to measure sky noise over.
    star_rng = np.random.default_rng(3)
    for _ in range(12):
        cy = int(star_rng.integers(5, h - 5)); cx = int(star_rng.integers(w // 2, w - 5))
        img[cy, cx, :] = float(star_rng.uniform(3000.0, 9000.0))

    patch = (slice(10, 50), slice(0, 40))  # star-free
    in_rms = float(np.sqrt(np.mean((img[patch] - sky) ** 2)))
    out = np.asarray(op.apply(img.copy(), {"method": "wavelet", "strength": 1.0}, EditContext()))
    out_rms = float(np.sqrt(np.mean((out[patch] - sky) ** 2)))

    # Fails before the fix (~2% reduction), passes after (~75%). A conservative
    # 40% floor keeps it robust to scikit-image/PyWavelets version wobble.
    assert out_rms < 0.6 * in_rms, f"wavelet barely denoised the sky: {in_rms:.3f} -> {out_rms:.3f}"
    # The bright star pixels must be preserved, not crushed toward the clip ceiling.
    assert float(out[:, w // 2:, :].max()) >= 0.95 * float(img[:, w // 2:, :].max())


@pytest.mark.parametrize("shape", [(1, 40, 3), (40, 1, 3)])
@pytest.mark.parametrize("method", ["wavelet", "bilateral", "tv"])
def test_denoise_on_a_one_px_thin_image_is_a_safe_noop(shape, method):
    # A 1-px-thin image has no neighbourhood to denoise over: before the guard,
    # the wavelet path emitted all-NaN in the *covered* region (breaking the
    # NaN=coverage invariant) and bilateral raised IndexError. It must instead
    # return the image untouched, preserving finite coverage, like the geometry
    # ops' degenerate-size guards.
    op = get_op("detail.denoise")
    img = (np.random.default_rng(0).random(shape).astype("float32") * 0.2) + 0.1
    out = op.apply(img, {"method": method, "strength": 0.6}, EditContext())
    assert out.shape == img.shape
    assert np.isfinite(out).all()          # no NaN introduced into covered pixels
    assert np.allclose(out, img, atol=1e-6)  # a sliver is left exactly as-is


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


def _scene(scale: float = 1.0, h: int = 80, w: int = 100) -> np.ndarray:
    """A realistic linear OSC scene: faint sky + a diffuse nebula blob + a bright
    star core, in arbitrary linear ADU (multiplied by ``scale``)."""
    rng = np.random.default_rng(3)
    img = (rng.random((h, w, 3)).astype("float32") * 0.01) + 0.05   # sky ~0.05
    yy, xx = np.mgrid[0:h, 0:w]
    img += (0.15 * np.exp(-(((xx - w / 2) / 18) ** 2
                            + ((yy - h / 2) / 18) ** 2)))[..., None]  # nebula
    img[10:12, 12:14, :] = 3.0                                       # bright star
    return (img * scale).astype("float32")


def test_no_recipe_fallback_uses_adaptive_stf_autostretch():
    # The no-stretch fallback must be the adaptive per-channel STF autostretch — the
    # same stretch the stored thumbnail (render.thumbnail.autostretch) uses — not the
    # old fixed-slider asinh. Two checks pin this down:
    #   (a) the fallback output is *exactly* autostretch() of the linear scene, and
    #   (b) STF anchors each channel's sky median to a neutral target grey, so the
    #       rendered sky lands at the same grey regardless of the raw linear scale of
    #       the data. A fixed-gain asinh renders two identically-shaped-but-differently
    #       -scaled scenes to *different* sky greys (its gain doesn't re-anchor the
    #       median), so a scale-invariant sky grey is exactly what proves it's STF.
    from seestack.render.thumbnail import autostretch

    rec = Recipe(ops=[])
    assert not has_stretch(rec)
    greys = []
    for scale in (1.0, 12.0):
        scene = _scene(scale=scale)
        out = apply_recipe(scene, rec, EditContext())
        fin = out[np.isfinite(out)]
        assert fin.min() >= 0.0 and fin.max() <= 1.0                  # display range
        # (a) the fallback is exactly autostretch() of the linear scene.
        assert np.allclose(np.nan_to_num(out), np.nan_to_num(autostretch(scene)),
                           atol=1e-5)
        # Sky = the low-value bulk; its median is where STF pins ~target_bg (0.20).
        greys.append(float(np.median(out[..., 1])))
    # (b) same sky grey at both raw scales — the adaptive-STF property asinh lacks.
    assert abs(greys[0] - greys[1]) < 0.02
    assert 0.12 < greys[0] < 0.28                                     # near 0.20 grey


def test_no_recipe_fallback_preview_export_parity():
    # The editor preview runs the fallback on the strided proxy; the export runs it
    # on the full-res FITS. Both now call the same STF autostretch, and STF re-anchors
    # the sky median to the target grey regardless of the top-end scale, so the two
    # agree within the inherent decimation-sampling floor (the same ≤2% parity the
    # other spatial ops document). Simulate the two resolutions by striding the scene.
    from seestack.render.thumbnail import autostretch

    scene = _scene(scale=1.0, h=160, w=200)
    full = autostretch(scene)                       # "export" — full-res
    proxy = autostretch(scene[::2, ::2])            # "preview" — 2x strided proxy
    # Compare the sky grey (channel-median) — the value the user's eye anchors to.
    for c in range(3):
        assert abs(float(np.median(full[..., c])) - float(np.median(proxy[..., c]))) < 0.02


def test_auto_stretch_false_returns_linear_ops_output():
    # The Stretch suggestion needs the *linear* image the stretch op will receive,
    # so auto_stretch=False must suppress the default-stretch fallback and leave a
    # no-stretch recipe's output in its original (wide, un-tone-mapped) range.
    rng = np.random.default_rng(0)
    img = (rng.random((40, 50, 3)).astype("float32") * 200.0) + 1000.0  # linear ADU
    rec = Recipe(ops=[])  # no ops → the only thing that could change the range is
    assert not has_stretch(rec)  # the auto-stretch fallback
    out = apply_recipe(img, rec, EditContext(), auto_stretch=False)
    # No stretch applied → the data keeps its original linear scale, untouched.
    assert np.allclose(out, img)
    assert out[np.isfinite(out)].max() > 1.0
    # The default (auto_stretch=True) still tone-maps into display range.
    disp = apply_recipe(img, rec, EditContext())
    assert disp[np.isfinite(disp)].max() <= 1.0


def test_already_display_ctx_suppresses_the_default_stretch():
    # Re-opening an editor export (a tone-mapped display-space image) with an empty
    # recipe must NOT default-stretch it again — the re-edit double-stretch. With
    # ctx.already_display the pipeline leaves an already-display-space image alone.
    rng = np.random.default_rng(1)
    disp_img = np.clip(rng.random((40, 50, 3)).astype("float32"), 0.0, 1.0)  # [0,1]
    rec = Recipe(ops=[])
    assert not has_stretch(rec)
    same = apply_recipe(disp_img, rec, EditContext(already_display=True))
    assert np.allclose(same, disp_img)                       # verbatim, no re-stretch
    # Without the flag the fallback autostretch fires and materially changes the image.
    stretched = apply_recipe(disp_img, rec, EditContext())
    assert not np.allclose(stretched, disp_img)
    # An explicit stretch op the user adds still runs even when already_display.
    rec2 = Recipe(ops=validate_ops([OpInstance(id="tone.stretch", params={"stretch": 0.8})]))
    out2 = apply_recipe(disp_img, rec2, EditContext(already_display=True))
    assert not np.allclose(out2, disp_img)


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


def test_measure_sky_cast_neutral_background():
    # A neutral (R=G=B) sky with per-channel noise and a bright central target
    # must read as neutral: the sky-population median trick excludes the target.
    from seestack.edit.histogram import measure_sky_cast
    rng = np.random.default_rng(1)
    img = np.full((120, 120, 3), 0.20, dtype=np.float32)
    img += rng.normal(0.0, 0.02, img.shape).astype(np.float32)
    img[50:70, 50:70, :] += 0.6                     # bright target — must be excluded
    sc = measure_sky_cast(img)
    assert sc["cast"] == "neutral" and sc["neutral"] is True
    assert sc["deviation"] <= 0.01
    # Sky medians land near the true sky level, not pulled up by the target.
    for ch in "rgb":
        assert abs(sc[ch] - 0.20) < 0.02


def test_measure_sky_cast_names_green_and_magenta():
    # A green-biased sky (G median clearly above R/B) reads "green"; the mirror
    # case (G below R/B) reads its complement, "magenta".
    from seestack.edit.histogram import measure_sky_cast
    rng = np.random.default_rng(2)
    base = np.full((100, 100, 3), 0.20, dtype=np.float32)
    base += rng.normal(0.0, 0.01, base.shape).astype(np.float32)
    green = base.copy(); green[..., 1] += 0.04
    assert measure_sky_cast(green)["cast"] == "green"
    magenta = base.copy(); magenta[..., 1] -= 0.04
    assert measure_sky_cast(magenta)["cast"] == "magenta"


def test_measure_sky_cast_nan_aware_and_empty():
    # NaN "no coverage" pixels are ignored; an all-NaN frame reports "unknown".
    from seestack.edit.histogram import measure_sky_cast
    img = np.full((40, 40, 3), 0.15, dtype=np.float32)
    img[:20, :, :] = np.nan                         # half uncovered
    sc = measure_sky_cast(img)
    assert sc["cast"] == "neutral" and abs(sc["g"] - 0.15) < 0.02
    empty = np.full((40, 40, 3), np.nan, dtype=np.float32)
    assert measure_sky_cast(empty)["cast"] == "unknown"
    assert measure_sky_cast(empty)["r"] is None


def test_neutralize_background_op_drives_a_display_cast_to_neutral():
    # End-to-end (the path the one-click "Neutralize background" fix takes): a
    # re-opened editor export (already display space, so no re-stretch) whose sky
    # kept a green cast. Appending tone.neutralize_background runs it in display
    # space — exactly where the sky-cast read-out measures — and measure_sky_cast on
    # the final image must go from a cast to neutral. (A pure *linear* cast is
    # instead re-anchored to neutral by the stretch's per-channel black point, which
    # is why the read-out only fires — and this fix only applies — post-stretch.)
    from seestack.edit.histogram import measure_sky_cast
    rng = np.random.default_rng(7)
    img = np.full((120, 120, 3), 0.20, dtype=np.float32)
    img[..., 1] += 0.03                                 # a green sky cast (display space)
    img += rng.normal(0.0, 0.005, img.shape).astype(np.float32)
    img[50:70, 50:70, :] += 0.5                         # bright target (excluded from sky)

    reopened = apply_recipe(img, Recipe(ops=[]), EditContext(already_display=True))
    assert measure_sky_cast(reopened)["neutral"] is False    # cast present on re-open

    fixed = apply_recipe(
        img,
        Recipe(ops=validate_ops([
            OpInstance(id="tone.neutralize_background", params={"strength": 1.0}),
        ])),
        EditContext(already_display=True))
    assert measure_sky_cast(fixed)["neutral"] is True        # appended fix neutralises it
    assert np.isfinite(fixed).any()


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


@pytest.mark.parametrize("bad_version", ["x", None, [1], {"a": 1}])
def test_recipe_from_dict_tolerates_non_int_version(bad_version):
    # ``version`` is read straight off the unvalidated PUT body in put_recipe; a
    # non-int value (string / null / list) must not raise ``int()`` out to an
    # unhandled 500 — fall back to the current version, mirroring the params guard.
    from seestack.edit.recipe import RECIPE_VERSION

    rec = recipe_from_dict({"version": bad_version, "ops": []})
    assert rec.version == RECIPE_VERSION


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


def test_auto_recipe_appends_contrast_curve():
    """Auto must append a gentle contrast curve (tone.curves, auto=True) after the
    saturation boost — matching the built-in presets, which the previously-flat
    general Auto recipe alone lacked."""
    from seestack.edit.presets import auto_recipe

    for rgb in (None,
                np.full((80, 100, 3), 0.05, np.float32),
                np.full((80, 100, 3), 0.05, np.float32) + 0.1):
        ids = [o.id for o in auto_recipe(rgb).ops]
        assert "tone.curves" in ids
        # the contrast curve shapes tone after the colour boost
        assert ids.index("tone.saturation") < ids.index("tone.curves")
        curve = next(o for o in auto_recipe(rgb).ops if o.id == "tone.curves")
        assert curve.params["auto"] is True
        # left at the identity default so the apply-time auto derivation engages
        assert curve.params["points"] == [[0.0, 0.0], [1.0, 1.0]]


def test_auto_recipe_contrast_curve_lifts_the_rendered_result():
    """End-to-end: rendering the full Auto recipe with its auto-contrast curve
    yields a higher-midtone result than the same recipe with the curve removed —
    i.e. the curve genuinely adds contrast to the one-click output (not a no-op)."""
    from seestack.edit.presets import auto_recipe

    rng = np.random.default_rng(3)
    # A dim-ish OSC-like stack: dark sky + a faint extended blob + a few stars.
    rgb = np.full((90, 110, 3), 0.02, np.float32)
    rgb[30:60, 40:80] += 0.06
    rgb[45, 55] = rgb[20, 20] = 0.8
    rgb += rng.normal(0, 0.005, rgb.shape).astype("float32")
    rgb = np.clip(rgb, 0.0, None)

    full = auto_recipe(rgb)
    without_curve = Recipe(ops=[o for o in full.ops if o.id != "tone.curves"])
    out_full = apply_recipe(rgb.copy(), full)
    out_plain = apply_recipe(rgb.copy(), without_curve)
    assert np.all(np.isfinite(out_full))
    # The curve lifts the faint midtone structure — the finite median rises.
    assert float(np.nanmedian(out_full)) > float(np.nanmedian(out_plain)) + 1e-3


def test_analyze_auto_inputs_reports_the_causal_cues():
    """The causal-input analysis reports the *measured cues* that drove the Auto
    recipe (sky, noise, star size, mosaic trim), matching what auto_recipe uses,
    and every field degrades gracefully to None when it can't be measured."""
    from seestack.edit.presets import analyze_auto_inputs, analyze_proxy

    rng = np.random.default_rng(5)
    noisy = np.full((80, 100, 3), 0.05, np.float32)
    noisy[30:50, 40:60] += 0.5
    noisy += rng.normal(0, 0.08, noisy.shape).astype("float32")

    a = analyze_auto_inputs(noisy, median_fwhm=4.7)
    # Sky + noise mirror analyze_proxy exactly (same numbers Auto consumed).
    proxy = analyze_proxy(noisy)
    assert a["sky"] == round(float(proxy["sky"]), 3)
    assert a["noisy"] is True and a["noisy"] == proxy["noisy"]
    assert a["noise_fraction"] is not None and a["noise_fraction"] > 0.0
    # Star size is surfaced, and the reported sharpen radius equals what Auto sizes
    # from that FWHM (the same helper, whether or not a very-noisy stack keeps the op).
    assert a["median_fwhm"] == 4.7
    from seestack.edit.presets import _sharpen_radius_from_fwhm
    assert a["sharpen_radius"] == _sharpen_radius_from_fwhm(4.7)
    assert a["is_mosaic"] is False
    assert a["trim_fraction"] is None      # single-field → no trim

    # Unmeasurable image + no FWHM → all cues None, but shape intact.
    empty = analyze_auto_inputs(None, median_fwhm=None)
    assert empty["sky"] is None and empty["noise_fraction"] is None
    assert empty["median_fwhm"] is None and empty["sharpen_radius"] is None
    assert empty["trim_fraction"] is None

    # A mosaic trim rect → the fraction of the frame trimmed away (1 − kept area).
    trimmed = analyze_auto_inputs(
        noisy, median_fwhm=None, is_mosaic=True, trim_crop=(0.1, 0.0, 1.0, 1.0))
    assert trimmed["is_mosaic"] is True
    assert trimmed["trim_fraction"] == pytest.approx(0.1, abs=1e-6)


def test_auto_edit_summary_note():
    """The auto-edit note names, in pipeline order, what the Auto recipe did and the
    measured cues that drove it — so an unattended auto-edit can be explained on the
    History Info panel the way the interactive editor explains a clicked Auto."""
    from seestack.edit.presets import auto_edit_summary
    from seestack.edit.recipe import OpInstance, Recipe

    recipe = Recipe(ops=[
        OpInstance(id="background.final_gradient", params={}),
        OpInstance(id="tone.color_calibrate", params={}),
        OpInstance(id="detail.sharpen", params={}),
    ])
    note = auto_edit_summary(recipe, {"sky": 0.101, "median_fwhm": 4.7})
    assert note == (
        "Auto-edited: flattened the background, balanced the colour, then "
        "sharpened detail · measured a ~0.1 sky, 4.7 px stars."
    )

    # A disabled op is skipped, and with no measurable cues the note omits the
    # "measured …" clause entirely (degrades gracefully).
    recipe2 = Recipe(ops=[
        OpInstance(id="tone.stretch", params={}),
        OpInstance(id="detail.sharpen", params={}, enabled=False),
    ])
    assert auto_edit_summary(recipe2, None) == "Auto-edited: applied a natural stretch."
    assert auto_edit_summary(recipe2, {"sky": None}) == (
        "Auto-edited: applied a natural stretch.")

    # A noisy, trimmed mosaic surfaces the noise + trim cues too.
    recipe3 = Recipe(ops=[OpInstance(id="geometry.crop", params={})])
    note3 = auto_edit_summary(
        recipe3, {"noise_fraction": 0.8, "trim_fraction": 0.12})
    assert note3 == (
        "Auto-edited: trimmed the ragged mosaic border · measured a noisy "
        "background, 12% of ragged mosaic edge to trim."
    )

    # An empty (all-disabled / no-op) recipe has nothing to explain → None.
    assert auto_edit_summary(Recipe(ops=[]), {"sky": 0.1}) is None


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

    def ids(is_mosaic):
        return [o.id for o in auto_recipe(clean, is_mosaic=is_mosaic).ops]

    # Mosaic: the pass is present and runs on linear data, before the gradient
    # removal and the stretch.
    mosaic_ids = ids(True)
    assert "background.level_coverage" in mosaic_ids
    assert mosaic_ids.index("background.level_coverage") < mosaic_ids.index("background.final_gradient")
    assert mosaic_ids.index("background.level_coverage") < mosaic_ids.index("tone.stretch")

    # Single-field → unchanged (no leveling).
    assert "background.level_coverage" not in ids(False)


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


def test_star_reduce_overstates_on_proxy_rule():
    from seestack.edit.ops.stars import star_reduce_overstates_on_proxy

    # Export (scale <= 1) never overstates.
    assert star_reduce_overstates_on_proxy(2.0, 1.0) is False
    assert star_reduce_overstates_on_proxy(8.0, 1.0) is False
    # Default star size on a 3x/4x-decimated proxy collapses below one proxy
    # pixel (2/3 = 0.67 < 1, 2/4 = 0.5 < 1) → footprint clamps up, preview
    # over-reduces.
    assert star_reduce_overstates_on_proxy(2.0, 3.0) is True
    assert star_reduce_overstates_on_proxy(2.0, 4.0) is True
    # A mild 2x proxy keeps the default size at exactly one proxy pixel (2/2 = 1),
    # so the footprint matches the export — no overstatement.
    assert star_reduce_overstates_on_proxy(2.0, 2.0) is False
    # A large star survives moderate decimation (8/4 = 2 >= 1).
    assert star_reduce_overstates_on_proxy(8.0, 4.0) is False
    # Degenerate inputs are safe (no false alarms).
    assert star_reduce_overstates_on_proxy(0.0, 4.0) is False
    assert star_reduce_overstates_on_proxy(float("nan"), 4.0) is False
    assert star_reduce_overstates_on_proxy(2.0, float("inf")) is False


def test_star_reduce_overstates_flag_matches_the_stronger_preview():
    """The star-reduction live preview genuinely *over*-reduces on a heavily
    decimated proxy — the erosion footprint clamps to 1 proxy-pixel (= scale
    full-res px), physically larger than the export's, so the preview eats into a
    wider ring of the (extended) star structure than the full-res export does.
    ``star_reduce_overstates_on_proxy`` must flag exactly that case so the editor
    can caption it honestly.
    """
    from seestack.edit.ops.stars import star_reduce_overstates_on_proxy

    # A field of *extended* (soft, overlapping-halo) stars: the larger proxy
    # footprint has more surrounding structure to pull down, which is where the
    # over-reduction shows (a fully-isolated hard star is removed either way).
    rng = np.random.default_rng(2)
    H = W = 240
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.full((H, W), 0.12, np.float32)
    for _ in range(220):
        cy, cx = rng.uniform(0, H), rng.uniform(0, W)
        amp, sig = rng.uniform(0.3, 0.9), rng.uniform(1.2, 3.0)
        img += amp * np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sig * sig)))
    full = np.clip(np.stack([img, img, img], -1), 0.0, 1.0).astype(np.float32)
    spec = get_op("stars.reduce")
    params = {"amount": 0.6, "size": 2, "protect_nebula": False}  # the default size

    # Export (proxy_scale=1): the reference star reduction at full resolution.
    exported = spec.apply(full.copy(), params, EditContext(proxy_scale=1.0))

    # Heavily-decimated preview proxy (proxy_scale=4, e.g. a wide drizzle): the
    # footprint clamps to 1 proxy-pixel and the preview over-reduces. Compare the
    # total reduction "ink" against the export's, sampled on the same proxy grid.
    proxy = full[::4, ::4].copy()
    previewed = spec.apply(
        proxy, params, EditContext(proxy_scale=4.0, is_proxy=True))
    preview_energy = float(np.sum(np.abs(proxy - previewed)))
    export_energy = float(np.sum(np.abs(proxy - exported[::4, ::4])))

    assert export_energy > 0.0                          # export clearly reduces
    # The preview reduces materially *more* than the export (measured ~1.2×).
    assert preview_energy > export_energy * 1.05
    # ...and the helper flags exactly this misleading case, but not the export.
    assert star_reduce_overstates_on_proxy(2.0, 4.0) is True
    assert star_reduce_overstates_on_proxy(2.0, 1.0) is False


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


def test_crop_degenerate_decision_matches_between_proxy_and_fullres():
    """The crop's "too small → ignore" decision must be resolution-independent so
    the preview proxy and the full-res export agree. A tiny fractional crop that is
    a real (≥2 px) crop on the full image used to no-op on the heavily-decimated
    proxy (its <2 px guard fired in *proxy* pixels), so the preview showed the whole
    frame while the export cropped — a violation of the fractional-coord parity the
    module documents."""
    spec = get_op("geometry.crop")
    full = _img(200, 400, nan_band=0)
    proxy = full[::4, ::4]  # proxy_scale 4 → 50×100
    # Width fraction 0.01 → 4 px on the full image (a real crop) but 1 px on the
    # proxy (below the raw <2 px guard). Height fraction is large so only the width
    # is at issue.
    params = {"x0": 0.20, "y0": 0.10, "x1": 0.21, "y1": 0.90}
    cf = spec.apply(full, params, EditContext(proxy_scale=1.0))
    cp = spec.apply(proxy, params, EditContext(proxy_scale=4.0, is_proxy=True))
    # The export crops the width...
    assert cf.shape[1] < full.shape[1]
    # ...so the proxy must crop it too (before the fix it returned the whole image).
    assert cp.shape[1] < proxy.shape[1]
    # And the proxy slice is never empty (would crash the render).
    assert cp.shape[0] >= 1 and cp.shape[1] >= 1


def test_crop_truly_degenerate_is_ignored_on_both_scales():
    """A crop that is degenerate on the *full* image (<2 px either axis) is ignored
    identically on proxy and export — the guard still protects a genuinely tiny
    fractional crop, it just decides consistently."""
    spec = get_op("geometry.crop")
    full = _img(200, 400, nan_band=0)
    proxy = full[::4, ::4]
    params = {"x0": 0.500, "y0": 0.10, "x1": 0.502, "y1": 0.90}  # 0.8 px wide on full
    cf = spec.apply(full, params, EditContext(proxy_scale=1.0))
    cp = spec.apply(proxy, params, EditContext(proxy_scale=4.0, is_proxy=True))
    assert cf.shape[:2] == full.shape[:2]     # ignored on export
    assert cp.shape[:2] == proxy.shape[:2]    # and on the proxy


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


@pytest.mark.parametrize("shape", [(2, 2), (1, 5), (5, 1), (2, 3), (3, 2)])
def test_rotate_on_a_tiny_image_is_a_safe_noop(shape):
    # Rotation's order-1 NaN border fill reaches ~1 px in from every edge, so a
    # frame with <3 px on an axis has no interior to survive and — before the
    # guard — came back *entirely* NaN, turning a fully-covered image into "no
    # coverage" and breaking the NaN=coverage invariant (a <2 px crop upstream can
    # feed exactly a 2×2). It must instead leave the sliver untouched, mirroring
    # the degenerate-size guards on crop/resize/denoise.
    spec = get_op("geometry.rotate")
    img = np.full((*shape, 3), 0.5, dtype=np.float32)  # fully covered, finite
    out = spec.apply(img.copy(), {"angle": 17.0, "expand": True}, EditContext())
    assert out.shape == img.shape
    assert np.isfinite(out).all()            # no covered pixel turned into NaN
    assert np.allclose(out, img, atol=1e-6)  # a sliver is left exactly as-is


def test_rotate_full_size_is_unchanged_by_the_tiny_guard():
    # The guard must be a no-op for any real image: a normal-size rotate still
    # grows the canvas and exposes NaN corners exactly as before.
    spec = get_op("geometry.rotate")
    img = _img(80, 120, nan_band=0)
    out = spec.apply(img, {"angle": 30.0, "expand": True}, EditContext())
    assert out.shape[0] > img.shape[0] and out.shape[1] > img.shape[1]
    assert np.isnan(out).any()  # exposed corners are uncovered (NaN)


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

    rec = auto_recipe(is_mosaic=True, trim_crop=(0.1, 0.12, 0.9, 0.88))
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

    mosaic_no_trim = auto_recipe(is_mosaic=True, trim_crop=None)
    single_field = auto_recipe(is_mosaic=False, trim_crop=None)
    assert "geometry.crop" not in [op.id for op in mosaic_no_trim.ops]
    assert "geometry.crop" not in [op.id for op in single_field.ops]
