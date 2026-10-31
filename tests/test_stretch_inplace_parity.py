"""The full-resolution stretch, rewritten to work in place, draws the same pixels.

The ⭐ 2026-10-28 entry's part (3): a first "Full-res PNG" of a 5000×7000 picture
spends most of its time in :func:`~seestack.render.thumbnail.autostretch`, and much
of that in fresh full-size temporaries — every ``(a - b) / c`` on a 35 M-pixel
channel allocates and first-touches another 140 MB. The rewrite gathers each
channel's covered pixels once and runs the curve on that one array.

The stored preview, the share JPEG and every Full-res PNG already on disk were
drawn by the old code, so "about the same" is not good enough: a download that
no longer matches its thumbnail is the bug the whole entry is about. Each test
below therefore keeps the **pre-rewrite** per-channel loop verbatim, as a replica,
and asserts the shipped function returns the identical array — ``array_equal``,
not ``allclose``.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from seestack.render import thumbnail as T

# ---- the pre-rewrite code, verbatim ------------------------------------------

def _old_robust_median_sigma(values):
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    sigma = 1.4826 * mad if mad > 0 else float(values.std() or 1e-3)
    return med, sigma


def _old_mtf(x, m):
    if abs(m - 0.5) < 1e-9:
        return x
    return (m - 1.0) * x / ((2.0 * m - 1.0) * x - m)


def _old_rolloff(x, knee):
    out = np.clip(x, 0.0, knee)
    over = x > knee
    if np.any(over):
        span = 1.0 - knee
        t = (x[over] - knee) / span
        out[over] = knee + span * (t / (1.0 + t))
    return out


def _old_autostretch(rgb, *, target_bg=0.20, sigma_factor=-2.0,
                     protect_highlights=True, highlight_protect=0.0, stats=None):
    knee = T.highlight_knee_for(highlight_protect)
    headroom = T._highlight_headroom_for(highlight_protect)
    img = rgb.astype(np.float32, copy=True)
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    finite_any = np.isfinite(img).any(axis=2)
    if not finite_any.any():
        return np.zeros_like(np.nan_to_num(img))
    bounds = (stats.lo, stats.hi) if stats is not None else T._asinh_norm_bounds(img)
    if bounds is None:
        return np.zeros_like(np.nan_to_num(img))
    lo, hi = bounds
    np.subtract(img, lo, out=img)
    np.divide(img, hi - lo, out=img)
    out = np.zeros_like(img)
    for c in range(3):
        chan = img[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            continue
        pinned = stats.channels[c] if stats is not None else None
        med, sigma = pinned if pinned is not None else _old_robust_median_sigma(chan[finite])
        shadows = max(0.0, med + sigma_factor * sigma)
        rng = max(1.0 - shadows, 1e-6)
        xr = (chan[finite] - shadows) / rng
        x = _old_rolloff(xr, knee) if protect_highlights else np.clip(xr, 0.0, 1.0)
        norm_med = max((med - shadows) / rng, 1e-6)
        m = T._midtones_for(norm_med, target_bg)
        out_chan = out[..., c]
        vals = np.clip(_old_mtf(x, m), 0.0, 1.0)
        if headroom > 0.0 and protect_highlights:
            sky_ceiling = (med + T._HIGHLIGHT_SKY_GUARD_SIGMA * sigma - shadows) / rng
            vals = T._reanchor_highlights(
                vals,
                knee_display=float(_old_mtf(knee, m)),
                anchor=float(_old_mtf(min(sky_ceiling, knee), m)),
                headroom=headroom,
            )
        out_chan[finite] = vals
    return out


def _old_asinh_stretch(rgb, *, stretch=0.5, black=0.35, protect_highlights=True,
                       highlight_protect=0.0, stats=None):
    knee = T.highlight_knee_for(highlight_protect)
    headroom = T._highlight_headroom_for(highlight_protect)
    img = rgb.astype(np.float32, copy=True)
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    finite_any = np.isfinite(img).any(axis=2)
    if not finite_any.any():
        return np.zeros_like(np.nan_to_num(img))
    bounds = (stats.lo, stats.hi) if stats is not None else T._asinh_norm_bounds(img)
    if bounds is None:
        return np.zeros_like(np.nan_to_num(img))
    lo, hi = bounds
    img = (img - lo) / (hi - lo)
    s = float(np.clip(stretch, 0.0, 1.0))
    a = float(0.004 ** s)
    denom = math.asinh(1.0 / a)
    b = float(np.clip(black, 0.0, 1.0))
    out = np.zeros_like(img)
    for c in range(3):
        chan = img[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            continue
        supplied = stats.channels[c] if stats is not None and c < len(stats.channels) else None
        med, sigma = supplied if supplied is not None else _old_robust_median_sigma(chan[finite])
        shadows = float(np.clip(med + (b * 6.0 - 2.0) * sigma, 0.0, 0.999))
        rng = max(1.0 - shadows, 1e-6)
        xr = (chan[finite] - shadows) / rng
        x = _old_rolloff(xr, knee) if protect_highlights else np.clip(xr, 0.0, 1.0)
        vals = np.clip(np.arcsinh(x / a) / denom, 0.0, 1.0)
        if headroom > 0.0 and protect_highlights:
            def curve(v):
                return float(np.clip(math.asinh(v / a) / denom, 0.0, 1.0))

            sky_ceiling = (med + T._HIGHLIGHT_SKY_GUARD_SIGMA * sigma - shadows) / rng
            vals = T._reanchor_highlights(
                vals, knee_display=curve(knee),
                anchor=curve(min(sky_ceiling, knee)), headroom=headroom,
            )
        out[..., c][finite] = vals
    return out


# ---- scenes ----------------------------------------------------------------

def _mosaic_like(seed=0, h=420, w=300, *, dtype=np.float32, bright_core=True):
    """A linear master shaped like the owner's: faint sky, stars, a blown core,
    a ragged NaN border and an uncovered corner, per-channel sky levels."""
    rng = np.random.default_rng(seed)
    sky = np.array([0.021, 0.018, 0.015], dtype=np.float64)
    img = sky + 0.004 * rng.standard_normal((h, w, 3))
    ys, xs = rng.integers(0, h, 250), rng.integers(0, w, 250)
    img[ys, xs] += rng.uniform(0.05, 4.0, (250, 1))
    if bright_core:
        yy, xx = np.mgrid[0:h, 0:w]
        img += (3.0 * np.exp(-((yy - h / 2) ** 2 + (xx - w / 2) ** 2) / 300.0))[..., None]
    img[: rng.integers(5, 30)] = np.nan
    img[:, : rng.integers(5, 30)] = np.nan
    img[h - 60:, w - 80:] = np.nan
    img[100:140, 40:41, 1] = np.nan          # a single-channel gap
    return img.astype(dtype)


SCENES = {
    "mosaic": _mosaic_like(0),
    "mosaic_no_core": _mosaic_like(1, bright_core=False),
    "all_finite": np.nan_to_num(_mosaic_like(2), nan=0.02),
    "float64_input": _mosaic_like(3, dtype=np.float64),
    "mono": _mosaic_like(4)[..., 1],
    "one_channel_empty": np.where(np.arange(3) == 2, np.nan, _mosaic_like(5)),
    "flat_mad_zero": np.full((40, 30, 3), 0.25, dtype=np.float32),
    "quantised": np.round(_mosaic_like(6) * 200) / 200,
}


@pytest.mark.parametrize("scene", sorted(SCENES))
@pytest.mark.parametrize("kw", [
    {},
    {"target_bg": 0.06, "sigma_factor": -2.8},          # the export stretch
    {"protect_highlights": False},
    {"highlight_protect": 0.8},
    {"target_bg": 0.5, "sigma_factor": 0.0},             # pushes m towards 0.5
])
def test_autostretch_is_pixel_identical_to_the_old_loop(scene, kw):
    rgb = SCENES[scene]
    expected = _old_autostretch(rgb, **kw)
    assert np.array_equal(T.autostretch(rgb, **kw), expected, equal_nan=True)
    # ``copy=False`` consumes its input and must still draw the same picture.
    owned = np.array(rgb, dtype=np.float32, copy=True)
    assert np.array_equal(T.autostretch(owned, copy=False, **kw), expected, equal_nan=True)


@pytest.mark.parametrize("scene", sorted(SCENES))
@pytest.mark.parametrize("kw", [
    {},
    {"stretch": 0.9, "black": 0.6},
    {"stretch": 0.0, "black": 0.0},
    {"protect_highlights": False},
    {"highlight_protect": 0.8},
])
def test_asinh_stretch_is_pixel_identical_to_the_old_loop(scene, kw):
    rgb = SCENES[scene]
    assert np.array_equal(T.asinh_stretch(rgb, **kw), _old_asinh_stretch(rgb, **kw),
                          equal_nan=True)


def test_pinned_stats_are_pixel_identical_too():
    """The Adjust path measures on the preview grid and applies to full res."""
    small, big = _mosaic_like(7, 120, 90), _mosaic_like(8)
    stats = T.measure_stretch_stats(small)
    assert stats is not None
    assert np.array_equal(T.autostretch(big, stats=stats),
                          _old_autostretch(big, stats=stats), equal_nan=True)
    assert np.array_equal(T.asinh_stretch(big, stats=stats),
                          _old_asinh_stretch(big, stats=stats), equal_nan=True)


@pytest.mark.parametrize("scene", sorted(SCENES))
def test_robust_median_sigma_is_unchanged_and_leaves_its_input_alone(scene):
    v = np.asarray(SCENES[scene], dtype=np.float32).ravel()
    v = v[np.isfinite(v)]
    before = v.copy()
    assert T._robust_median_sigma(v) == _old_robust_median_sigma(before)
    assert np.array_equal(v, before)     # callers reuse ``values`` afterwards


def test_rolloff_and_mtf_in_place_match_the_returning_forms():
    x = np.linspace(-0.5, 6.0, 4001, dtype=np.float32)
    for knee in (0.25, 0.7):
        got = T._highlight_rolloff(x.copy(), knee, in_place=True)
        assert np.array_equal(got, _old_rolloff(x, knee))
        assert np.array_equal(T._highlight_rolloff(x, knee), _old_rolloff(x, knee))
    for m in (0.001, 0.2, 0.5, 0.73, 0.999):
        y = x.copy()
        got = T._mtf(y, m, in_place=True)
        assert np.array_equal(got, _old_mtf(x, m))
        if abs(m - 0.5) >= 1e-9:
            assert got is y                  # it really did reuse the buffer
        assert np.array_equal(T._mtf(x, m), _old_mtf(x, m))


# ---- the bracketed median is numpy's median, not an estimate ------------------

def _sample_misses(n):
    """Every value the evenly spaced sample reads is 0 and the rest sit above
    it, so the guessed bracket cannot hold the median."""
    v = np.random.default_rng(5).uniform(1.0, 2.0, n).astype(np.float32)
    v[:: max(1, n // T._BRACKET_MEDIAN_SAMPLE)] = 0.0
    return v


def _median_cases():
    rng = np.random.default_rng(11)
    n = T._BRACKET_MEDIAN_MIN + 7                   # odd, above the threshold
    yield "gauss_odd", (0.02 + 0.004 * rng.standard_normal(n)).astype(np.float32)
    yield "gauss_even", (0.02 + 0.004 * rng.standard_normal(n + 1)).astype(np.float32)
    yield "float64", rng.standard_normal(n + 3)
    # Heavy ties: a 16-bit-quantised sky, so the middle ranks share values.
    yield "quantised", (np.round(rng.normal(900, 30, n)) / 65535).astype(np.float32)
    yield "all_equal", np.full(n + 1, 0.25, dtype=np.float32)
    # Sorted input: an evenly spaced sample is then perfectly placed …
    yield "sorted", np.sort(rng.standard_normal(n).astype(np.float32))
    # … and a sample that lands on one lump while the median sits in another
    # forces the bracket to miss and the numpy fallback to answer.
    yield "sample_misses", _sample_misses(n)
    yield "stars", np.concatenate([
        (0.02 + 0.004 * rng.standard_normal(n)).astype(np.float32),
        rng.uniform(0.5, 50, n // 3).astype(np.float32)])
    with_nan = (0.02 + 0.004 * rng.standard_normal(n)).astype(np.float32)
    with_nan[::1000] = np.nan
    yield "nan", with_nan
    with_inf = (0.02 + 0.004 * rng.standard_normal(n)).astype(np.float32)
    with_inf[::997] = np.inf
    yield "inf", with_inf
    yield "ints", rng.integers(0, 1000, n)
    yield "small", rng.standard_normal(1001).astype(np.float32)


@pytest.mark.parametrize("name,values", list(_median_cases()), ids=lambda x: x if isinstance(x, str) else "")
def test_exact_median_is_numpys_median_bit_for_bit(name, values):
    want = float(np.median(values))
    got = T._exact_median(values)
    assert (math.isnan(want) and math.isnan(got)) or got == want, (name, got, want)
    # Read-only unless told otherwise: the stretch reuses ``values`` afterwards.
    snapshot = values.copy()
    T._exact_median(values)
    assert np.array_equal(values, snapshot, equal_nan=True)
    scratch = values.copy()
    got_overwrite = T._exact_median(scratch, overwrite_input=True)
    assert (math.isnan(want) and math.isnan(got_overwrite)) or got_overwrite == want


def test_exact_median_really_takes_the_bracket(monkeypatch):
    """Guard on the guard: if every case above fell back to ``np.median`` the
    test would pass while proving nothing about the fast path."""
    calls = []
    real = np.median
    monkeypatch.setattr(T.np, "median", lambda *a, **k: calls.append(1) or real(*a, **k))
    rng = np.random.default_rng(3)
    v = (0.02 + 0.004 * rng.standard_normal(T._BRACKET_MEDIAN_MIN * 2)).astype(np.float32)
    T._exact_median(v)
    assert calls == []
    T._exact_median(_sample_misses(T._BRACKET_MEDIAN_MIN + 1))
    assert calls == [1]                       # …and the fallback is reachable


def test_full_size_channel_is_pixel_identical():
    """One channel above the bracket threshold, through the whole stretch."""
    h = w = 1100                                 # 1.21 M px per channel
    rng = np.random.default_rng(21)
    img = (np.array([0.021, 0.018, 0.015]) + 0.004 * rng.standard_normal((h, w, 3)))
    img[:40] = np.nan
    img[:, -33:] = np.nan
    img = img.astype(np.float32)
    assert np.isfinite(img[..., 0]).sum() > T._BRACKET_MEDIAN_MIN
    assert np.array_equal(T.autostretch(img, target_bg=0.06, sigma_factor=-2.8),
                          _old_autostretch(img, target_bg=0.06, sigma_factor=-2.8),
                          equal_nan=True)
    assert np.array_equal(T.asinh_stretch(img), _old_asinh_stretch(img), equal_nan=True)
