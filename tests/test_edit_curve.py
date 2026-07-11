"""Data-driven starting tone curve for the Curves op (seestack/edit/curve.py)."""

from __future__ import annotations

import numpy as np

from seestack.edit.curve import CURVE_TARGET_BG, suggest_tone_curve


def _scene(black_floor=0.10, h=120, w=160, seed=0):
    """A realistic display-space (stretched) image: a dark sky floor, a broad
    extended object filling much of the frame, and a handful of bright stars — so
    the low/median/high percentiles are well separated (dark sky → faint object →
    bright cores), the way a typical Seestar OSC stack looks after a stretch."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    sky = black_floor + rng.normal(0.0, 0.02, (h, w))
    obj = 0.4 * np.exp(-(((xx - w / 2) / 40.0) ** 2 + ((yy - h / 2) / 30.0) ** 2))
    img = sky + obj
    for _ in range(15):  # a few near-saturated stars set the highlight end
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        img[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2] = 0.95
    return np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, 1.0).astype("float32")


def _is_strictly_monotone(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (all(b > a for a, b in zip(xs, xs[1:], strict=False))
            and all(b > a for a, b in zip(ys, ys[1:], strict=False)))


def test_curve_lifts_the_midtone_and_anchors_the_ends():
    pts = suggest_tone_curve(_scene(black_floor=0.10))
    assert pts is not None
    # Endpoints pinned; a strictly-monotone (never posterising/inverting) curve.
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]
    assert _is_strictly_monotone(pts)
    # The sky and highlight anchors sit on the identity; the midtone is lifted.
    sky, mid, high = pts[1], pts[2], pts[3]
    assert sky[1] == sky[0]           # sky floor stays put
    assert high[1] == high[0]         # highlight shoulder rolls off (on identity)
    assert mid[1] > mid[0]            # midtone lifted upward


def test_midtone_lift_aims_toward_the_target_grey():
    pts = suggest_tone_curve(_scene(black_floor=0.10))
    assert pts is not None
    mid = pts[2]
    # The lift is gentle (a fraction of the way to the target), so the lifted
    # midtone lands strictly between the original tone and the target grey.
    assert mid[0] < mid[1] < CURVE_TARGET_BG + 1e-6


def test_points_are_clamped_and_rounded():
    pts = suggest_tone_curve(_scene())
    assert pts is not None
    for x, y in pts:
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        assert round(x, 3) == x and round(y, 3) == y


def test_nan_uncovered_pixels_are_ignored():
    img = _scene()
    img[:20, :, :] = np.nan  # a mosaic-edge NaN band
    pts = suggest_tone_curve(img)
    assert pts is not None
    assert all(np.isfinite(x) and np.isfinite(y) for x, y in pts)


def test_returns_none_when_range_is_degenerate():
    # A flat image (no dynamic range) → anchors collide → no useful curve.
    flat = np.full((60, 60, 3), 0.3, dtype="float32")
    assert suggest_tone_curve(flat) is None
    # All-NaN (uncovered) → too few finite pixels.
    allnan = np.full((60, 60, 3), np.nan, dtype="float32")
    assert suggest_tone_curve(allnan) is None


def test_returns_none_when_typical_tone_already_at_or_above_target():
    # A bright-midtone image: the median already sits at/above the target grey,
    # so there is nothing pleasant to lift — leave the identity line.
    rng = np.random.default_rng(1)
    img = np.clip(0.6 + rng.normal(0.0, 0.02, (80, 80, 3)), 0.0, 1.0).astype("float32")
    assert suggest_tone_curve(img) is None


def test_saturated_highlight_p99_5_rounding_does_not_drop_the_curve():
    """Regression: a stretched image whose 99.5th percentile sits just below 1.0
    (0.9998) but *rounds* to 1.0 must still yield a valid midtone-lift curve — the
    high anchor is dropped (it would duplicate the pinned [1,1] endpoint), not the
    whole suggestion. Before the fix the rounded anchor collided with the endpoint
    and the strict-monotone guard bailed to None."""
    rng = np.random.default_rng(4)
    # Dark sky floor + a broad object with a bright, near-saturated highlight tail
    # so p99.5 lands at ~0.9998 (rounds to 1.0) while the median stays below target.
    yy, xx = np.mgrid[0:120, 0:160]
    img = 0.08 + rng.normal(0.0, 0.015, (120, 160))
    img += 0.25 * np.exp(-(((xx - 80) / 45.0) ** 2 + ((yy - 60) / 35.0) ** 2))
    img[50:70, 70:90] = 0.9998                  # a bright saturated patch (>0.5% of px)
    img = np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, 1.0).astype("float32")
    high = float(np.percentile(img[np.isfinite(img)], 99.5))
    assert high < 1.0 and round(high, 3) == 1.0  # the exact rounding-collision case
    pts = suggest_tone_curve(img)
    assert pts is not None, "a valid curve must survive a p99.5 that rounds to 1.0"
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]
    assert _is_strictly_monotone(pts)


def test_the_curve_applied_by_the_op_preserves_nan_and_stays_in_range():
    # The suggested points must produce a sane LUT through the real Curves op:
    # covered pixels stay in [0, 1] and NaN (uncovered) is preserved.
    from seestack.edit.ops.tone import _curves

    img = _scene(black_floor=0.10)
    img[:10, :, :] = np.nan
    pts = suggest_tone_curve(img)
    assert pts is not None
    out = _curves(img, {"points": pts}, None)
    covered = np.isfinite(out)
    assert np.all(out[covered] >= 0.0) and np.all(out[covered] <= 1.0)
    # NaN coverage is exactly preserved (no lost/spurious coverage).
    assert np.array_equal(np.isnan(out), np.isnan(img))
