"""A mosaic panel shot far shallower than the rest is still levelled.

The Scout's 2026-11-15 finding: ``level_by_coverage`` bins by *depth*, but its
structure guard (``_region_sky_mask``) judged every level against the
**canvas's** retained sky σ — a number the deep panels set. Grain falls as
1/√depth, so a panel ≥ 9× shallower than the bulk read its own honest grain as
"structure", was refused, fell to the neighbour fill and kept its whole sky
offset: a bright rectangle through the stack *and* Auto. Each level is now
judged against its *own* expected grain, ``√(bulk / level)`` × the canvas
yardstick (the rule v0.470.0 gave the grain-band caller).
"""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.bg import coverage_leveling
from seestack.bg.coverage_leveling import level_by_coverage

_THIN = slice(1200, 1800)


def _strip(k, n_sigma, *, seed=0, h=600, w=3000):
    """Five 600-px panels at 30 subs, the middle one at ``k`` subs carrying a
    sky offset of ``n_sigma`` × the deep panels' grain (σ_deep = 1)."""
    rng = np.random.default_rng(seed)
    cov = np.full((h, w), 30, dtype=np.int32)
    cov[:, _THIN] = k
    sig = np.sqrt(30.0 / cov.astype(np.float32))
    rgb = 100.0 + rng.normal(size=(h, w, 3)).astype(np.float32) * sig[..., None]
    rgb[:, _THIN, :] += np.float32(n_sigma)
    return rgb.astype(np.float32), cov


def _step(out):
    thin = float(np.median(out[:, 1250:1750, 1]))
    deep = float(np.median(out[:, 100:1100, 1]))
    return thin - deep


@pytest.mark.parametrize("k", [3, 2])
@pytest.mark.parametrize("n_sigma", [5.0, 20.0])
def test_a_panel_nine_times_shallower_is_levelled(k, n_sigma):
    rgb, cov = _strip(k, n_sigma)
    out = level_by_coverage(rgb, cov, frame_coverage=cov)
    # Before the fix: 5.0 and 20.0 σ_deep left in place.
    assert abs(_step(out)) < 1.0


def test_the_preview_proxy_levels_the_thin_panel_too():
    """The same canvas strided ×3 (the live preview) agrees with the export."""
    rgb, cov = _strip(3, 20.0)
    full = level_by_coverage(rgb, cov, frame_coverage=cov)
    prev = level_by_coverage(rgb[::3, ::3], cov[::3, ::3],
                             frame_coverage=cov[::3, ::3], proxy_scale=3.0)
    assert abs(_step(full)) < 1.0
    thin = float(np.median(prev[:, 1250 // 3:1750 // 3, 1]))
    deep = float(np.median(prev[:, 100 // 3:1100 // 3, 1]))
    assert abs(thin - deep) < 1.0


def test_a_shallow_level_filled_by_structure_is_still_refused():
    """The allowance is the level's *own* expected grain, so a thin panel that
    is genuinely full of nebula (spread far beyond 3× its own grain) is still
    not read as sky: it is shifted by its neighbours' offset, its flux intact."""
    rgb, cov = _strip(3, 0.0, seed=4)
    ramp = np.linspace(400.0, 4000.0, 600, dtype=np.float32)[None, :, None]
    rgb[:, _THIN, :] += ramp
    before = rgb.copy()
    out = level_by_coverage(rgb, cov, frame_coverage=cov)
    shifted = float(np.median(before[:, _THIN, 1]) - np.median(out[:, _THIN, 1]))
    # The deep sky sits at 100: the structured panel moves by that, not by its
    # own ~2200 "level".
    assert abs(shifted - 100.0) < 2.0


def _panel_scene(seed=3, h=600, w=800):
    rng = np.random.default_rng(seed)
    cov = np.zeros((h, w), dtype=np.int32)
    for i, cols in enumerate(np.array_split(np.arange(w), 4)):
        cov[:, cols] = (4, 5, 6, 7)[i]
    rgb = rng.normal(0.0, 2.0, size=(h, w, 3)).astype(np.float32)
    for lvl, off in zip((4, 5, 6, 7), (0.0, 15.0, 30.0, 45.0)):
        rgb[cov == lvl] += off
    for _ in range(200):
        y, x = int(rng.integers(6, h - 6)), int(rng.integers(6, w - 6))
        rgb[y - 2:y + 3, x - 2:x + 3, :] += float(rng.uniform(200, 4000))
    return rgb, cov


@pytest.mark.parametrize("scene", ["panels", "strip_k20", "strip_k6"])
def test_byte_identical_wherever_no_level_was_refused(scene, monkeypatch):
    """The allowance only ever loosens a refusal, so a canvas on which the old
    canvas yardstick refused nothing is levelled bit-for-bit as before."""
    if scene == "panels":
        rgb, cov = _panel_scene()
    else:
        rgb, cov = _strip(int(scene.rsplit("k", 1)[1]), 5.0)
    new = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    monkeypatch.setattr(coverage_leveling, "_depth_sigma_allowance",
                        lambda level, bulk: 1.0)
    old = level_by_coverage(rgb.copy(), cov, frame_coverage=cov)
    assert np.array_equal(new, old)


def test_depth_allowance_is_one_at_or_above_the_bulk():
    f = coverage_leveling._depth_sigma_allowance
    assert f(30, 30.0) == 1.0
    assert f(60, 30.0) == 1.0
    assert f(0, 30.0) == 1.0
    assert f(3, float("nan")) == 1.0
    assert f(3, 27.0) == pytest.approx(3.0)
