"""
Per-coverage sky leveling: panel-step removal for mosaic stacks.

The bug it fixes: in a mosaic, each distinct coverage value can end up at
a slightly different mean sky brightness for various reasons (reproject
edge effects, residual bg-flatten bias, real sky differences between
panels). The visible result is rectangle-shaped brightness steps tracing
the coverage map. This pass equalises sky brightness across coverage
values.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.bg.coverage_leveling import level_by_coverage
from seestack.stackhealth import seam_verdict


def _mosaic_image_with_panel_steps(h=200, w=300, levels=(2, 5, 9)):
    """
    Synthesise a mosaic-like result with three coverage regions, each at a
    different mean brightness. Add a few stars so the object mask has work
    to do.
    """
    rng = np.random.default_rng(0)
    rgb = rng.normal(0.0, 5.0, size=(h, w, 3)).astype(np.float32)
    coverage = np.zeros((h, w), dtype=np.int32)
    # Three vertical bands with different coverage values + sky offsets.
    bands = np.array_split(np.arange(w), len(levels))
    offsets = (10.0, 30.0, -15.0)  # per-band sky offsets
    for cols, lvl, off in zip(bands, levels, offsets):
        coverage[:, cols] = lvl
        rgb[:, cols, :] += off
    # Plant some stars across the canvas.
    for _ in range(25):
        y = int(rng.integers(8, h - 8))
        x = int(rng.integers(8, w - 8))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += 1500.0
    return rgb, coverage, offsets


def test_panel_steps_disappear_after_leveling():
    rgb, coverage, offsets = _mosaic_image_with_panel_steps()
    out = level_by_coverage(rgb, coverage)
    # The median sky in each band must collapse to the same value (≈ 0)
    # after leveling, regardless of the input offsets.
    for lvl, off in zip((2, 5, 9), offsets):
        region = (coverage == lvl)
        # Same object-masking the function applies internally.
        for c in range(3):
            sky_pixels = out[region, c]
            # Drop the brightest 10% to ignore stars.
            sky_pixels = sky_pixels[sky_pixels < np.percentile(sky_pixels, 90)]
            med = float(np.median(sky_pixels))
            assert abs(med) < 2.0, (
                f"coverage {lvl} (input offset {off}): "
                f"channel {c} median = {med:.2f} (should be ~0)"
            )


def test_leveling_preserves_relative_star_brightness_within_band():
    rgb, coverage, _ = _mosaic_image_with_panel_steps()
    # Note the brightness of one star before…
    star_y, star_x = 100, 50
    rgb[star_y - 2:star_y + 3, star_x - 2:star_x + 3, :] += 4000.0
    before = float(rgb[star_y, star_x, 1])
    before_bg = float(rgb[star_y - 10, star_x - 10, 1])  # nearby sky

    out = level_by_coverage(rgb, coverage)
    after = float(out[star_y, star_x, 1])
    after_bg = float(out[star_y - 10, star_x - 10, 1])
    # The (star - nearby-sky) contrast is unchanged — leveling subtracts a
    # constant from the whole region.
    assert abs((before - before_bg) - (after - after_bg)) < 1.0


def test_leveling_skips_thinly_covered_levels():
    """Coverage values with too few sky pixels are left alone (no median
    can be reliably computed)."""
    rgb = np.zeros((40, 60, 3), dtype=np.float32)
    coverage = np.full((40, 60), 5, dtype=np.int32)
    # A handful of pixels at a different coverage — too few to level.
    coverage[0, :5] = 1
    rgb[0, :5, :] = 99.0  # would otherwise be subtracted
    out = level_by_coverage(rgb, coverage, min_pixels_per_level=200)
    # Those pixels are unchanged.
    np.testing.assert_array_equal(out[0, :5, :], rgb[0, :5, :])


def test_proxy_scale_matches_full_res_level_selection():
    """Preview↔export parity: a mosaic coverage level that is leveled in the
    full-resolution export must also be leveled on the strided live-preview proxy.

    The proxy is decimated by ``step = round(proxy_scale)`` (exactly how
    ``build_proxy``/``load_coverage`` stride), so a level with N full-res sky
    pixels has only ~N/step² on the proxy. With a fixed ``min_pixels_per_level``
    floor a thin panel leveled in the export (N ≥ 200) is *skipped* on a ×4 proxy
    (~N/16 < 200), leaving a visible panel-step in the preview that the export
    doesn't have. Passing ``proxy_scale`` scales the floor by 1/step² so the same
    levels are selected at both resolutions.
    """
    rng = np.random.default_rng(0)
    h = w = 240
    rgb = rng.normal(0.0, 0.03, size=(h, w, 3)).astype(np.float32)
    coverage = np.full((h, w), 6, dtype=np.int32)
    # A thin panel at a distinct coverage: 60×12 = 720 full-res sky pixels
    # (≥200 → leveled in the export), but only 15×3 = 45 after striding by 4.
    coverage[0:60, 0:12] = 3
    rgb[0:60, 0:12, :] += 0.02  # its sky sits above the rest of the canvas
    panel_full = coverage == 3

    proxy = rgb[::4, ::4].copy()
    cov_proxy = coverage[::4, ::4]
    panel_proxy = cov_proxy == 3
    assert int(panel_proxy.sum()) == 45  # below the fixed 200 floor, above 200/16

    # Full-res export levels the thin panel's sky to ~0.
    export = level_by_coverage(rgb.copy(), coverage, object_sigma=5.0)
    assert abs(float(np.median(export[panel_full]))) < 0.005

    # Old behaviour (no proxy_scale): the strided panel drops below the fixed 200
    # floor and is skipped, so its offset survives — the preview↔export mismatch.
    skipped = level_by_coverage(proxy.copy(), cov_proxy,
                                object_sigma=5.0, proxy_scale=1.0)
    assert float(np.median(skipped[panel_proxy])) > 0.015

    # With the proxy scale, the floor is scaled to full-res-equivalent pixels, so
    # the same panel is leveled on the proxy — matching the export.
    fixed = level_by_coverage(proxy.copy(), cov_proxy,
                              object_sigma=5.0, proxy_scale=4.0)
    assert abs(float(np.median(fixed[panel_proxy]))) < 0.005


def _heavy_stride_scene(h=600, w=900, patch=18, seed=3):
    """Two big panels plus one small overlap patch, sized for a ×6 proxy.

    ``patch``² full-res pixels clears the export's 200-pixel floor but strides
    down to fewer than the 12 the proxy needs to *measure* a median — the exact
    band where the preview used to diverge from the export.
    """
    rng = np.random.default_rng(seed)
    cov = np.ones((h, w), dtype=np.int32)
    cov[:, w // 2:] = 2
    x0 = w // 2 - patch // 2
    cov[10:10 + patch, x0:x0 + patch] = 3
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for lvl, sky in ((1, 100.0), (2, 130.0), (3, 160.0)):
        region = cov == lvl
        for c in range(3):
            rgb[..., c][region] = sky + c * 2.0
    rgb += rng.normal(0.0, 1.0, rgb.shape).astype(np.float32)
    return rgb, cov


def test_a_heavily_strided_proxy_still_levels_a_panel_the_export_levels():
    """Preview↔export parity at heavy decimation (step ≥ 5, i.e. a mosaic canvas
    over ~7500 px — exactly the deep mosaics this op exists for).

    The floor that keeps a per-level median off a handful of pixels
    (``_MIN_STRIDED_PIXELS``) stops scaling past ~×4, so beyond that the proxy
    demanded *more* full-res-equivalent pixels than the export. A level in that
    band used to drop out of the level set entirely — neither measured **nor
    filled** — so the preview left the whole panel step in place while the export
    removed most of it. It is now still *considered*, and takes the same
    neighbour-interpolated offset the export gives a level it can't measure
    either.
    """
    rgb, cov = _heavy_stride_scene()
    assert int((cov == 3).sum()) == 324           # clears the export's 200 floor

    export = level_by_coverage(rgb.copy(), cov.astype(np.float32))
    export_residual = float(np.median(export[..., 1][cov == 3]))

    step = 6
    proxy = np.ascontiguousarray(rgb[::step, ::step])
    cov_proxy = np.ascontiguousarray(cov[::step, ::step])
    # 9 strided pixels: above the export-equivalent floor (200/36 ≈ 6), below the
    # 12 a median needs — the band the fix is about.
    assert int((cov_proxy == 3).sum()) == 9

    preview = level_by_coverage(
        proxy.copy(), cov_proxy.astype(np.float32), proxy_scale=float(step),
        dilate_object_mask_px=max(0, round(4 / step)))
    preview_residual = float(np.median(preview[..., 1][cov_proxy == 3]))

    # Before the fix the preview left the panel's full ~162 ADU offset while the
    # export cut it to ~30; they now agree to well inside the 1 ADU noise.
    assert abs(preview_residual - export_residual) < 3.0
    # And both are far below the untouched offset, so this isn't passing by both
    # sides doing nothing.
    assert preview_residual < 60.0


def test_a_sliver_below_the_export_floor_stays_untouched_at_heavy_stride():
    """The lower, export-equivalent floor is still a floor: a level too small to
    clear it is a sliver, not a panel, and is left byte-for-byte alone at any
    stride. (Without this the fix would read as "the pixel floor was removed".)"""
    rgb, cov = _heavy_stride_scene(patch=6)       # 36 full-res px, under 200
    step = 6
    proxy = np.ascontiguousarray(rgb[::step, ::step])
    cov_proxy = np.ascontiguousarray(cov[::step, ::step])
    sliver = cov_proxy == 3
    assert sliver.any()
    # 36/36 = 1 strided pixel, under the export-equivalent floor of ~6.
    assert int(sliver.sum()) < 6

    out = level_by_coverage(
        proxy.copy(), cov_proxy.astype(np.float32), proxy_scale=float(step),
        dilate_object_mask_px=max(0, round(4 / step)))
    np.testing.assert_array_equal(out[sliver], proxy[sliver])


def test_smoothing_does_not_extrapolate_a_seam_onto_a_gapped_overlap_level():
    """A sparsely-sampled deep-overlap coverage level must not have a wrong
    offset *extrapolated* onto it from the dense single-panel levels.

    Coverage levels are typically gapped: dense single-panel frame-counts, then a
    jump to the far smaller 2×/3× overlap counts. The cross-level smoothing fits a
    single global polynomial weighted by sky-pixel count, which is dominated by the
    high-pixel-count cluster; without a bound it *extrapolates* that cluster's trend
    across the gap onto an isolated overlap level and overrides its well-measured
    offset with a value far outside the measured range — subtracting a bright/dark
    seam over that region, i.e. the very panel step this pass exists to remove.
    """
    rng = np.random.default_rng(11)
    h = w = 700
    coverage = np.zeros((h, w), dtype=np.int32)
    # Four dense single-panel coverage bands (4..7) with a gentle, slightly-curved
    # residual sky trend, plus one sparsely-sampled deep-overlap level (18) far up
    # the coverage axis — a big gap the global fit would extrapolate across.
    coverage[0:175, :] = 4
    coverage[175:350, :] = 5
    coverage[350:525, :] = 6
    coverage[525:700, :] = 7
    coverage[360:376, 300:316] = 18  # ~256 sky px — just above the 200 floor
    band_off = {4: 0.0, 5: 1.2, 6: 2.6, 7: 4.2, 18: 3.0}
    base, sig = 100.0, 1.0
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for lvl, off in band_off.items():
        m = coverage == lvl
        for c in range(3):
            rgb[..., c][m] = base + off + rng.normal(0, sig, size=int(m.sum()))

    out = level_by_coverage(rgb.copy(), coverage)

    def band_median(res, lvl):
        return float(np.median(res[..., 1][coverage == lvl]))

    dense_levels = (4, 5, 6, 7)
    dense_mean = float(np.mean([band_median(out, lvl) for lvl in dense_levels]))
    overlap_med = band_median(out, 18)
    # The overlap level's leveled sky must land near the dense levels' sky (all ~0),
    # not be driven tens of ADU away by an unbounded extrapolation. Before the fix
    # this seam is ~28 ADU; the clamp holds it to the measured per-level spread.
    assert abs(overlap_med - dense_mean) < 5.0, (
        f"overlap coverage level leveled to {overlap_med:.2f} vs dense sky "
        f"{dense_mean:.2f} — a {overlap_med - dense_mean:.1f} ADU seam"
    )


def test_bins_by_true_frame_count_not_the_weighted_sum():
    """Under quality weighting the accumulator's ``coverage`` is a Σ-of-weights,
    not the frame count, so rounding it fuzzes the coverage bins: part of a single
    real panel (same frame count everywhere) can round into a *separate* bin that
    then falls below the per-level pixel floor and is skipped — leaving its panel
    step in the image. Passing the true integer ``frame_coverage`` bins by real
    coverage, so the whole single-count panel is one level and levels cleanly.
    """
    rng = np.random.default_rng(7)
    h, w = 200, 300
    # One real panel: every pixel is covered by exactly 6 frames (no true step).
    frame_cov = np.full((h, w), 6, dtype=np.int32)
    # Weighted coverage: the bulk sits at Σ≈6.0 (rounds to bin 6); a thin strip's
    # frames were slightly downweighted to Σ≈5.4 (rounds to bin 5). Same 6 frames
    # everywhere — the weighted map is the only thing that splits the strip off,
    # and it's small enough (8×20 = 160 px) to fall below the 200-pixel floor.
    coverage = np.full((h, w, 3), 6.0, dtype=np.float32)
    strip = (slice(0, 8), slice(0, 20))
    coverage[strip[0], strip[1], :] = 5.4
    # A single uniform sky offset across the whole single-count panel.
    rgb = (rng.normal(0.0, 3.0, size=(h, w, 3)).astype(np.float32) + 40.0)

    # Old behaviour (bin by the weighted coverage): the strip rounds to bin 5,
    # falls below the 200-pixel floor, is skipped, and keeps its +40 sky offset.
    old = level_by_coverage(rgb.copy(), coverage)
    assert float(np.median(old[strip[0], strip[1], 1])) > 30.0

    # With the true frame count: the strip is part of the single 6-frame bin and
    # is leveled with the rest of the panel → its sky lands at ~0.
    new = level_by_coverage(rgb.copy(), coverage, frame_coverage=frame_cov)
    assert abs(float(np.median(new[strip[0], strip[1], 1]))) < 3.0
    assert abs(float(np.median(new[..., 1]))) < 3.0


def test_frame_coverage_matches_coverage_on_the_unweighted_path():
    """Byte-for-byte guard: on an unweighted stack ``frame_coverage`` equals the
    (integer) coverage map, so passing it must not change the result at all."""
    rng = np.random.default_rng(3)
    h, w = 160, 220
    rgb = rng.normal(0.0, 5.0, size=(h, w, 3)).astype(np.float32)
    coverage = np.zeros((h, w), dtype=np.int32)
    for cols, lvl, off in zip(np.array_split(np.arange(w), 3),
                              (2, 5, 9), (10.0, 30.0, -15.0)):
        coverage[:, cols] = lvl
        rgb[:, cols, :] += off
    without = level_by_coverage(rgb.copy(), coverage)
    withfc = level_by_coverage(rgb.copy(), coverage, frame_coverage=coverage)
    np.testing.assert_array_equal(without, withfc)


def test_uncovered_region_is_left_alone():
    """coverage == 0 pixels (uncovered canvas) must not be touched."""
    rng = np.random.default_rng(1)
    h, w = 80, 100
    rgb = rng.normal(0.0, 5.0, size=(h, w, 3)).astype(np.float32)
    rgb[:, :30, :] = np.nan  # uncovered band
    coverage = np.full((h, w), 4, dtype=np.int32)
    coverage[:, :30] = 0
    # Make the covered region have a known offset.
    rgb[:, 30:, :] += 25.0
    out = level_by_coverage(rgb, coverage)
    # Uncovered region: still NaN.
    assert np.all(np.isnan(out[:, :30, 0]))


def _seam_scene(seam_offset=12.0, seam_width=2, h=400, w=400, seed=0):
    """A mosaic-like canvas whose highest-coverage region is a thin seam strip.

    Four coverage levels rising left to right, each with the residual sky offset
    that this pass exists to cancel. The 4-frame overlap is a *thin strip* — the
    shape a real panel overlap takes — so the canvas-wide object mask, dilated by
    its default 4 px, swallows it whole.
    """
    rng = np.random.default_rng(seed)
    cov = np.ones((h, w), dtype=np.int32)
    cov[:, 100:200] = 2
    cov[:, 200:] = 3
    cov[:, 300:300 + seam_width] = 4
    sky = {1: 100.0, 2: 100.0 + seam_offset / 3.0,
           3: 100.0 + 2.0 * seam_offset / 3.0, 4: 100.0 + seam_offset}
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for lvl, level_sky in sky.items():
        m = cov == lvl
        for c in range(3):
            rgb[..., c][m] = level_sky + rng.normal(0.0, 1.0, size=int(m.sum()))
    return rgb, cov


def test_a_seam_the_object_mask_swallowed_is_still_leveled():
    """Regression: the object mask thresholds against the *canvas-wide* median,
    so a coverage level whose residual sky sits above it reads as one big
    "object" and loses its sky sample — and that is precisely the level with the
    most offset to remove. Left un-leveled while its neighbours are pushed to
    zero, it kept its full residual: a bright step at the seam, in every channel,
    manufactured by the pass that exists to remove seams.
    """
    rgb, cov = _seam_scene(seam_offset=12.0)
    seam = cov == 4
    neighbour = cov == 3
    # The premise: the global mask really does starve this level. It clears the
    # 200-pixel floor on region size (800 px) yet keeps far fewer sky pixels.
    assert int(seam.sum()) >= 200

    out = level_by_coverage(rgb, cov, frame_coverage=cov)

    seam_sky = float(np.median(out[..., 1][seam]))
    neighbour_sky = float(np.median(out[..., 1][neighbour]))
    # The seam is leveled with everything else rather than stranded at +12.
    assert abs(seam_sky) < 1.0
    assert abs(seam_sky - neighbour_sky) < 1.0


def test_the_seam_step_is_removed_in_every_channel():
    """The offsets are per channel, so a stranded level keeps a *coloured* step.
    Check all three, not just the green the other assertions read."""
    rgb, cov = _seam_scene(seam_offset=9.0)
    seam = cov == 4
    neighbour = cov == 3
    out = level_by_coverage(rgb, cov, frame_coverage=cov)
    for c in range(3):
        step = (float(np.median(out[..., c][seam]))
                - float(np.median(out[..., c][neighbour])))
        assert abs(step) < 1.0, f"channel {c} still steps by {step:.2f} ADU"


def test_an_unmeasurable_level_takes_the_offset_interpolated_from_its_neighbours():
    """The fill is an interpolation, not a nearest-neighbour copy: a level that
    can't be measured sits between two that can, and takes the value *between*
    their offsets. ``np.interp`` is flat outside the measured range, so a filled
    offset can never leave the envelope of what was actually measured."""
    rng = np.random.default_rng(23)
    h, w = 240, 300
    cov = np.zeros((h, w), dtype=np.int32)
    cov[:, :100] = 2
    cov[:, 100:200] = 4
    cov[:, 200:] = 6
    rgb = rng.normal(0.0, 1.0, size=(h, w, 3)).astype(np.float32)
    rgb[:, :100, :] += 100.0
    rgb[:, 200:, :] += 130.0
    # The middle (4-frame) level is filled by structured nebulosity, so it can't
    # be measured — its own retained spread is far wider than the canvas sky's.
    ramp = np.linspace(500.0, 5000.0, 100, dtype=np.float32)[None, :, None]
    rgb[:, 100:200, :] = ramp + rng.normal(0.0, 40.0, size=(h, 100, 3)).astype(np.float32)
    before = rgb.copy()

    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)

    # The two measured levels land at zero sky.
    assert abs(float(np.median(out[..., 1][cov == 2]))) < 1.5
    assert abs(float(np.median(out[..., 1][cov == 6]))) < 1.5
    # The middle level is shifted by the *interpolated* 115 — halfway between
    # its neighbours' 100 and 130 — not by either neighbour's value and not by
    # its own ~2750 ADU level.
    shifted = float(np.median(before[..., 1][cov == 4])
                    - np.median(out[..., 1][cov == 4]))
    assert abs(shifted - 115.0) < 2.0


def test_a_sliver_below_the_pixel_floor_is_still_left_untouched():
    """The fill applies only to levels big enough to be worth correcting. A
    handful of pixels at their own coverage value is a sliver, not a panel, and
    stays byte-for-byte untouched (the long-standing contract)."""
    rgb = np.zeros((40, 60, 3), dtype=np.float32)
    coverage = np.full((40, 60), 5, dtype=np.int32)
    coverage[0, :5] = 1
    rgb[0, :5, :] = 99.0
    # Give the bulk level a real offset, so a fill would visibly move the sliver.
    rgb[1:, :, :] += 20.0
    rgb[0, 5:, :] += 20.0
    out = level_by_coverage(rgb.copy(), coverage, min_pixels_per_level=200)
    np.testing.assert_array_equal(out[0, :5, :], rgb[0, :5, :])


def test_uniform_coverage_is_unchanged_by_the_rescue_path():
    """A single-field stack has one coverage level that always has plenty of sky,
    so neither the rescue nor the fill can reach it — the ordinary
    non-mosaic result must be byte-for-byte what it always was."""
    rng = np.random.default_rng(11)
    h, w = 120, 160
    rgb = rng.normal(0.0, 4.0, size=(h, w, 3)).astype(np.float32) + 30.0
    for _ in range(15):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += 900.0
    coverage = np.full((h, w), 7, dtype=np.int32)
    out = level_by_coverage(rgb.copy(), coverage)
    # Sky at zero, stars intact and shifted by exactly the same constant.
    assert abs(float(np.median(out[..., 1]))) < 1.0
    delta = rgb[..., 1] - out[..., 1]
    # One constant subtracted everywhere (to float32 resolution at star peaks).
    assert float(delta.max() - delta.min()) < 1e-3


def test_a_level_filled_by_a_bright_object_is_not_re_measured_as_sky():
    """The level-local rescue must not fire on a coverage region that is filled
    by real structure. Re-measuring one would read the *object's* own level as a
    sky offset and subtract it — eating real flux. Such a level falls through to
    the interpolated fill (the neighbours' offset), so its structure survives.
    """
    rng = np.random.default_rng(17)
    h = w = 200
    cov = np.full((h, w), 3, dtype=np.int32)
    cov[:, :40] = 6
    rgb = rng.normal(0.0, 1.0, size=(h, w, 3)).astype(np.float32) + 50.0
    # A steep, highly structured "nebula" filling the whole 6-frame level: far
    # more spread than the canvas sky, so it can't pass for sky.
    ramp = np.linspace(400.0, 4000.0, 40, dtype=np.float32)[None, :, None]
    rgb[:, :40, :] = ramp + rng.normal(0.0, 30.0, size=(h, 40, 3)).astype(np.float32)
    before = rgb.copy()

    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)

    # The sky level is leveled to zero as always.
    assert abs(float(np.median(out[..., 1][cov == 3]))) < 1.0
    # The object level was shifted by the sky offset (50), not by its own
    # ~2200 ADU "level" — its flux is intact.
    shifted = float(np.median(before[..., 1][cov == 6])
                    - np.median(out[..., 1][cov == 6]))
    assert abs(shifted - 50.0) < 2.0


def test_panel_offsets_do_not_float_the_object_threshold_above_the_objects():
    """Regression (root cause): the object threshold used to be one canvas-wide
    ``median + σ``. On the mosaic this pass exists for, that σ is set by the
    panel-to-panel level offsets — the very thing about to be subtracted — not by
    the noise, so it floats far above the grain and stops masking objects at all.
    Every level's "sky" median then picks up whatever nebulosity crosses it, and
    the levels the object sits on are over-subtracted: a coloured panel step
    survives the pass that exists to remove it.

    Measured on this scene before the fix: 5.2 ADU of residual spread across the
    four levels, on a 2 ADU noise floor.
    """
    rng = np.random.default_rng(3)
    h, w, noise = 600, 800, 2.0
    cov = np.zeros((h, w), dtype=np.int32)
    for i, cols in enumerate(np.array_split(np.arange(w), 4)):
        cov[:, cols] = i + 1
    rgb = rng.normal(0.0, noise, size=(h, w, 3)).astype(np.float32)
    # Realistic panel-to-panel level offsets (15 ADU per step).
    for lvl, off in {1: 0.0, 2: 15.0, 3: 30.0, 4: 45.0}.items():
        m = cov == lvl
        for c in range(3):
            rgb[..., c][m] += off
    # A nebula across the middle panels, and stars everywhere.
    yy, xx = np.mgrid[0:h, 0:w]
    neb = 60.0 * np.exp(-(((yy - h / 2) / 120.0) ** 2 + ((xx - w / 2) / 200.0) ** 2))
    for c, k in enumerate((1.0, 0.7, 0.5)):
        rgb[..., c] += (neb * k).astype(np.float32)
    for _ in range(300):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += float(rng.uniform(200, 4000))

    out = level_by_coverage(rgb, cov, frame_coverage=cov)

    # Read each level's sky on a nebula-free, star-sparse strip along the top.
    from astropy.stats import sigma_clipped_stats
    strip = slice(0, 40)
    resid = []
    for lvl in (1, 2, 3, 4):
        vals = out[strip][..., 1][(cov == lvl)[strip]]
        _, med, _ = sigma_clipped_stats(vals, sigma=3.0, maxiters=5)
        resid.append(float(med))
    spread = max(resid) - min(resid)
    # Comfortably inside the noise, and far below the 5.2 ADU it used to leave.
    assert spread < 1.0, f"panel steps survive leveling: {spread:.2f} ADU"


def test_a_single_coverage_level_detects_objects_exactly_as_before():
    """On a uniform-coverage image the per-level detrend is one constant
    subtracted from both the pixels and the threshold, so the object mask — and
    therefore the whole result — is exactly what it has always been. Pinned as
    an invariance: shifting the entire input by a constant must not change a
    single output pixel."""
    rng = np.random.default_rng(29)
    h, w = 150, 200
    rgb = rng.normal(0.0, 3.0, size=(h, w, 3)).astype(np.float32) + 20.0
    for _ in range(20):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += 800.0
    coverage = np.full((h, w), 4, dtype=np.int32)

    base = level_by_coverage(rgb.copy(), coverage)
    lifted = level_by_coverage(rgb.copy() + np.float32(500.0), coverage)
    # Equal to float32 resolution at the lifted magnitude (~3e-5 relative on
    # 500 ADU) — a changed mask decision would move a level's median by orders
    # of magnitude more than this.
    np.testing.assert_allclose(base, lifted, rtol=0, atol=1e-2)


# ---- did the joins actually come out flat? --------------------------------
#
# The leveling pass above can't always succeed — an unreadable level takes a
# neighbour's interpolated offset, and one filled by real structure is left
# alone on purpose — and nothing downstream ever checked the result. That is why
# the owner's "multicolour grid" had to be reported by a human looking at an
# export. ``measure_seam_residual`` measures what survived, in units of the
# picture's own grain, so the app can say it out loud.

def _panel_scene(offsets=(0.0, 15.0, 30.0, 45.0), noise=2.0, neb_amp=60.0,
                 stars=300, h=600, w=800, seed=3):
    """The realistic 4-panel canvas the v0.232.3 fix was measured on: rising
    per-panel sky offsets, a nebula across the middle panels, stars everywhere.
    """
    rng = np.random.default_rng(seed)
    cov = np.zeros((h, w), dtype=np.int32)
    for i, cols in enumerate(np.array_split(np.arange(w), 4)):
        cov[:, cols] = i + 1
    rgb = rng.normal(0.0, noise, size=(h, w, 3)).astype(np.float32)
    for lvl, off in zip((1, 2, 3, 4), offsets):
        m = cov == lvl
        for c in range(3):
            rgb[..., c][m] += off
    yy, xx = np.mgrid[0:h, 0:w]
    neb = neb_amp * np.exp(-(((yy - h / 2) / 120.0) ** 2
                             + ((xx - w / 2) / 200.0) ** 2))
    for c, k in enumerate((1.0, 0.7, 0.5)):
        rgb[..., c] += (neb * k).astype(np.float32)
    for _ in range(stars):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(6, w - 6))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += float(rng.uniform(200, 4000))
    return rgb, cov


def test_a_correctly_leveled_mosaic_measures_a_seam_residual_inside_its_noise():
    from seestack.bg.coverage_leveling import measure_seam_residual

    rgb, cov = _panel_scene()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    residual = measure_seam_residual(out, cov, frame_coverage=cov)
    assert residual is not None
    assert residual.n_levels == 4
    # Comfortably inside the grain — the "panels evened out" verdict's territory
    # (the health check calls anything under 1.0 flat).
    assert residual.ratio < 1.0, residual


def test_panel_offsets_left_in_place_measure_a_large_seam_residual():
    """The measurement has to *catch* the failure it exists for: the same scene
    with its per-panel offsets never leveled reads many times the grain."""
    from seestack.bg.coverage_leveling import measure_seam_residual

    rgb, cov = _panel_scene()
    residual = measure_seam_residual(rgb, cov, frame_coverage=cov)
    assert residual is not None
    assert residual.ratio > 5.0, residual
    # And the yardstick stayed honest: the noise it divides by is the grain
    # *within* a level (~2 ADU here), not a canvas-wide sigma that the very
    # offsets being measured would have inflated.
    assert residual.noise_sigma < 2.0 * 3.0, residual


def test_one_stranded_coverage_level_is_caught():
    """The realistic shape of the bug: everything levels except one region,
    which keeps a step. Two grain-widths of step is already reportable."""
    from seestack.bg.coverage_leveling import measure_seam_residual

    rgb, cov = _panel_scene()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    flat = measure_seam_residual(out, cov, frame_coverage=cov)
    stranded = out.copy()
    stranded[cov == 3] += 6.0            # 3× the scene's true 2 ADU noise
    seamed = measure_seam_residual(stranded, cov, frame_coverage=cov)
    assert flat is not None and seamed is not None
    assert seamed.ratio > 1.5 > flat.ratio, (flat, seamed)


def test_a_single_coverage_level_has_no_seam_to_measure():
    """An ordinary single-field stack has one coverage level, so there is no
    join to compare — the measurement declines to invent a verdict (and costs
    the stacker nothing, since it never runs there)."""
    from seestack.bg.coverage_leveling import measure_seam_residual

    rng = np.random.default_rng(5)
    rgb = rng.normal(50.0, 2.0, size=(200, 200, 3)).astype(np.float32)
    cov = np.full((200, 200), 6, dtype=np.int32)
    assert measure_seam_residual(rgb, cov, frame_coverage=cov) is None


def test_the_seam_residual_is_unchanged_by_rescaling_the_picture():
    """It is a ratio of a step to the grain, so it has to mean the same thing at
    any exposure, gain or normalisation — otherwise a single threshold could not
    be read as "about one grain-width" on every stack."""
    from seestack.bg.coverage_leveling import measure_seam_residual

    rgb, cov = _panel_scene()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    base = measure_seam_residual(out, cov, frame_coverage=cov)
    after = measure_seam_residual(out * np.float32(37.0), cov, frame_coverage=cov)
    assert base is not None and after is not None
    assert after.ratio == pytest.approx(base.ratio, rel=1e-3)


def test_a_nebula_crossing_the_panels_does_not_read_as_a_seam():
    """Real large-scale structure spanning panels is the obvious false positive.
    A canvas with no panel offsets at all — only a bright nebula across it —
    must still read as flat, whatever the nebula's strength."""
    from seestack.bg.coverage_leveling import measure_seam_residual

    for amp in (60.0, 400.0):
        rgb, cov = _panel_scene(offsets=(0.0, 0.0, 0.0, 0.0), neb_amp=amp)
        out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
        residual = measure_seam_residual(out, cov, frame_coverage=cov)
        assert residual is not None and residual.ratio < 1.0, (amp, residual)


def test_an_unmeasurable_canvas_reports_nothing_rather_than_guessing():
    from seestack.bg.coverage_leveling import measure_seam_residual

    blank = np.full((40, 40, 3), np.nan, dtype=np.float32)
    cov = np.ones((40, 40), dtype=np.int32)
    assert measure_seam_residual(blank, cov, frame_coverage=cov) is None
    # No covered pixels at all.
    rgb = np.zeros((40, 40, 3), dtype=np.float32)
    zero = np.zeros((40, 40), dtype=np.int32)
    assert measure_seam_residual(rgb, zero, frame_coverage=zero) is None


def _curved_trend_scene(unmeasurable_level=4, seed=19):
    """Seven coverage levels whose sky follows a *curved* trend with the level,
    with one middle level filled by structure so it can't be measured.

    Sky-vs-coverage is one physical trend, and the pass already fits a quadratic
    across the levels it measured. A level it could not measure has to land on
    that same curve; a straight line drawn between its neighbours instead sits
    off it wherever the trend bends.
    """
    rng = np.random.default_rng(seed)
    h, w = 400, 700
    cov = np.zeros((h, w), dtype=np.int32)
    bands = np.array_split(np.arange(w), 7)
    for i, cols in enumerate(bands):
        cov[:, cols] = i + 1
    rgb = rng.normal(0.0, 1.5, size=(h, w, 3)).astype(np.float32)
    for lvl in range(1, 8):
        for c in range(3):
            rgb[..., c][cov == lvl] += 100.0 + 3.0 * lvl + 0.8 * lvl * lvl
    cols = bands[unmeasurable_level - 1]
    ramp = np.linspace(500.0, 5000.0, len(cols), dtype=np.float32)[None, :, None]
    rgb[:, cols, :] = ramp + rng.normal(
        0.0, 40.0, size=(h, len(cols), 3)).astype(np.float32)
    return rgb, cov


def test_an_unmeasurable_level_lands_on_the_same_curve_as_the_measured_ones():
    """Regression: the fill used to draw a straight line between the neighbouring
    *measured* offsets while every measured level was moved onto the fitted
    quadratic — so on a curved sky-vs-coverage trend a filled level ended up
    slightly off the curve its neighbours sit on. That is a low-frequency
    inconsistency tracing exactly the coverage map this pass exists to erase.

    On this scene the true offset at the unmeasurable level 4 is 124.8; the
    straight line between neighbours gives 125.6 (0.8 ADU on a 1.5 ADU noise
    floor), the fitted curve gives 124.8.
    """
    rgb, cov = _curved_trend_scene()
    before = rgb.copy()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)

    shifted = float(np.median(before[..., 1][cov == 4])
                    - np.median(out[..., 1][cov == 4]))
    assert shifted == pytest.approx(124.8, abs=0.15), shifted
    # And the levels that *were* measured did not move as a side effect — each
    # still lands at zero sky.
    for lvl in (1, 2, 3, 5, 6, 7):
        assert abs(float(np.median(out[..., 1][cov == lvl]))) < 0.5, lvl


def test_the_fill_falls_back_to_a_straight_line_when_no_curve_was_fitted():
    """With smoothing off there is no fitted trend to sit on, so the fill must
    still work — straight between the measured neighbours, as it always did."""
    rgb, cov = _curved_trend_scene()
    before = rgb.copy()
    out = level_by_coverage(rgb.copy(), cov, frame_coverage=cov,
                            smooth_across_levels=False)
    shifted = float(np.median(before[..., 1][cov == 4])
                    - np.median(out[..., 1][cov == 4]))
    # Halfway between the measured level-3 (116.2) and level-5 (135.0) offsets —
    # the straight line, which is exactly the 125.6 that sits 0.8 ADU off the
    # true 124.8 when a curve *was* fitted.
    assert shifted == pytest.approx(125.6, abs=0.5), shifted


# --- the seam residual has to mean the same thing at 8 subs and at 800 --------
#
# Every fixture above builds four fat coverage bands of 120,000 pixels each, so
# each level's sky is pinned down to a thousandth of the grain and the estimate's
# own noise is invisible. A real deep mosaic looks nothing like that: the Seestar
# dithers, so the coverage map ramps from one frame at the fringe to hundreds in
# a panel body, and the measurement ends up comparing dozens of thin, low-coverage
# levels whose sky is both the noisiest (σ ∝ 1/√coverage) and the least sampled.

def _deep_dither_scene(n_per_panel, *, frame_sigma=40.0, dither=6, seed=0,
                       h=400, w=700):
    """A two-panel mosaic with **no** panel offset at all, built from
    ``n_per_panel`` dithered subs per panel.

    Every pixel's sky is exactly the same number; only the noise differs, and it
    falls as 1/√coverage exactly as stacking makes it. So a seam measurement on
    this canvas has nothing to find at any depth — the only thing that changes
    with ``n_per_panel`` is how many coverage levels the dither ramp splits into
    and how unequal their precision is.
    """
    rng = np.random.default_rng(seed)
    cov = np.zeros((h, w), dtype=np.float64)
    for x0, x1 in ((40, 400), (340, 660)):
        for _ in range(n_per_panel):
            dx = int(rng.integers(-dither, dither + 1))
            dy = int(rng.integers(-dither, dither + 1))
            cov[max(0, 40 + dy):min(h, 360 + dy),
                max(0, x0 + dx):min(w, x1 + dx)] += 1
    covered = cov > 0
    sig = frame_sigma / np.sqrt(np.maximum(cov, 1.0))
    rgb = np.full((h, w, 3), np.nan, dtype=np.float32)
    for c in range(3):
        noise = rng.normal(0.0, 1.0, size=(h, w)) * sig
        rgb[..., c] = np.where(covered, 100.0 + noise, np.nan)
    return rgb, cov.astype(np.float32)


def test_a_flat_mosaic_does_not_grow_a_seam_as_the_sub_count_rises():
    """Regression: the residual used to be a monotone function of the sub count
    on a canvas with no seam in it.

    ``spread_adu`` was a plain max−min over the per-level sky modes, so every
    level's own estimation noise was charged to the seam. That noise does not
    shrink with the yardstick: the thin low-coverage ramp levels carry ~√N times
    the grain of a panel body on a fraction of the pixels, and there are more of
    them the deeper the stack goes, while the yardstick (the median level's
    grain) falls as 1/√N. Measured on this scene the ratio climbed 0.27 (4 subs
    a panel) → 0.76 (32) → 1.38 (64) → **1.56 (128)**, i.e. straight past the
    1.5 bar at which "How's my stack?" tells the owner *"the panels of this
    mosaic didn't fully even out … faint seams may show"* — about a mosaic whose
    panels are, by construction, identical.
    """
    from seestack.bg.coverage_leveling import measure_seam_residual

    shallow = measure_seam_residual(*_deep_dither_scene(8))
    deep = measure_seam_residual(*_deep_dither_scene(128))
    assert shallow is not None and deep is not None
    # Both canvases are flat, so both must read flat — the health check's own bar.
    assert seam_verdict(round(shallow.ratio, 4)) == "flat", shallow
    assert seam_verdict(round(deep.ratio, 4)) == "flat", deep
    # And the depth must not be what decides it: the deep read may not be a
    # multiple of the shallow one just because there is more data behind it.
    assert deep.ratio < max(0.5, 2.0 * shallow.ratio), (shallow, deep)


def test_a_real_step_on_a_deep_dithered_mosaic_is_still_caught():
    """The other half: the slack each level's estimate now gets must not blunt a
    genuine seam. A panel body stranded by 3× the picture's own grain — the same
    size of step ``test_one_stranded_coverage_level_is_caught`` uses — still
    reads well past the "check" bar at every depth, because a level measured
    from thousands of sky pixels has a standard error far below the grain."""
    from seestack.bg.coverage_leveling import measure_seam_residual

    for n in (8, 128):
        rgb, cov = _deep_dither_scene(n)
        grain = 40.0 / np.sqrt(n)                    # the stacked picture's noise
        rgb = rgb.copy()
        rgb[np.rint(cov).astype(int) >= int(0.8 * n)] += np.float32(3.0 * grain)
        seamed = measure_seam_residual(rgb, cov)
        assert seamed is not None
        assert seam_verdict(round(seamed.ratio, 4)) == "check", (n, seamed)
