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
