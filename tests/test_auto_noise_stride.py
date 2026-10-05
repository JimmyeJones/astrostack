"""Auto's noise measurement must not depend on the proxy's *stride*.

``analyze_proxy`` reads the background σ with a **lag-1** estimator (the MAD of
adjacent-pixel differences, ``noise.estimate_noise_sigma``), and the live editor
always measures a **decimated** proxy — ``build_proxy`` strides whatever is
bigger than ``PROXY_MAX_PX``, which is every mosaic this owner shoots. "Adjacent"
therefore means ``step`` full-resolution pixels apart, and the stacker's
reprojection leaves the grain correlated over about a pixel, so the *same sky*
reads systematically higher through a bigger stride:
``Var(Iᵢ₊ₗ − Iᵢ) = 2σ²(1 − ρ(l))`` and ``ρ`` has not died out at lag 1.

Measured on the scene below, σ reads **0.0159 → 0.0229 → 0.0246** at steps
1 / 2 / 3 — the same pixels — which flips the ``noisy`` verdict and moves Auto's
denoise/sharpen crossfade weight **0.243 → 0.789**. Worse, the recipe built from
the strided measurement is applied to the **full-resolution** export, whose grain
is the smaller number, so the error is in the *over*-denoising direction on
exactly the thin mosaic panels that can least afford it.

The correction is ``noise.grain_lag_ratio`` — ``σ(lag 1) / σ(lag step)`` measured
on un-strided pixels of the master, which is dimensionless, so the normalization
divides out and nothing has to be calibrated between the two grids. Two
properties make it a correction rather than a tuning, and both are pinned here:
on **white** noise it is exactly 1.0 (σ does not depend on separation), and at
**step 1** it is 1.0 without measuring anything — so an ordinary single-field
stack's one-click Auto is byte-for-byte what it was.
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from seestack.edit.noise import (
    estimate_noise_sigma,
    grain_lag_ratio,
    suggest_denoise_strength,
)
from seestack.edit.presets import _noise_fraction, analyze_proxy, auto_recipe
from seestack.edit.proxy import source_grain_ratio

#: The width of the stacker's reprojection kernel, in full-resolution pixels.
#: Drizzle/reproject spread one input sample over its neighbours, so the output's
#: noise is correlated over about this far — the entire reason a lag-1 estimator
#: answers differently on a strided grid. ``0`` is the control (white noise).
_REPROJECTION_CORR_PX = 0.7

#: σ chosen so the *uncorrected* reading crosses ``analyze_proxy``'s 0.02 "noisy"
#: bar between step 1 and step 2. A fixture whose σ sits far from the bar cannot
#: show the consequence, only the ratio.
_BAND_SIGMA = 0.024


def _stacked_scene(h: int = 1500, w: int = 1500, *, sigma: float = _BAND_SIGMA,
                   corr_px: float = _REPROJECTION_CORR_PX,
                   seed: int = 3) -> np.ndarray:
    """A linear stack-shaped canvas: sky, one extended object, stars, and noise
    carrying a reprojection's pixel-to-pixel correlation.

    The extended object is not decoration. σ is reported in units of the image's
    own 0.5–99.5th-percentile range, and on a canvas of *only* sky and sparse
    stars that range is set by the noise's own tail — which makes the reported σ
    nearly independent of the noise level and parks every fixture at the same
    number. A real stack has a target filling a few percent of the frame, and
    that is what puts the reading somewhere the bars can be crossed.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sky = np.full((h, w), 0.10, dtype=np.float32)
    r2 = ((yy - h * 0.5) / (0.17 * h)) ** 2 + ((xx - w * 0.5) / (0.17 * w)) ** 2
    sky += (0.55 * np.exp(-r2)).astype(np.float32)
    for _ in range(600):
        cy, cx = int(rng.integers(12, h - 12)), int(rng.integers(12, w - 12))
        amp, star_sigma = float(rng.uniform(0.1, 0.9)), 1.7
        ys, xs = slice(cy - 7, cy + 8), slice(cx - 7, cx + 8)
        g = np.exp(-(((yy[ys, xs] - cy) ** 2 + (xx[ys, xs] - cx) ** 2)
                     / (2 * star_sigma * star_sigma)))
        sky[ys, xs] += (amp * g).astype(np.float32)
    n = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    if corr_px > 0:
        n = gaussian_filter(n, corr_px)
        n /= float(n.std())  # keep σ the *pixel* σ, whatever the smoothing did
    return np.repeat((sky + (sigma * n).astype(np.float32))[:, :, None], 3, axis=2)


def _write_master(path, rgb: np.ndarray) -> str:
    """Write a canvas out the way a stack run does — a 3-plane primary HDU — so
    the windowed reads under test go through the real file path."""
    from astropy.io import fits

    fits.PrimaryHDU(np.transpose(rgb, (2, 0, 1)).astype(np.float32)).writeto(path)
    return str(path)


# --- the defect, and the invariance that replaces it -------------------------

def test_uncorrected_sky_sigma_really_does_depend_on_the_stride():
    """The premise. If this ever stops holding, the fixture has gone blind and
    the invariance tests below are passing for the wrong reason."""
    full = _stacked_scene()
    raw = [analyze_proxy(full[::s, ::s])["sky_sigma"] for s in (1, 2, 3)]
    assert raw[0] < 0.02 < raw[1], raw          # the "noisy" bar is crossed
    assert raw[2] > raw[0] * 1.4, raw           # and not marginally
    assert analyze_proxy(full)["noisy"] is False
    assert analyze_proxy(full[::3, ::3])["noisy"] is True


def test_sky_sigma_is_the_same_sky_at_every_proxy_stride():
    """The fix: corrected, one canvas answers one number however it is strided."""
    full = _stacked_scene()
    answers = []
    for step in (1, 2, 3, 4):
        proxy = full[::step, ::step]
        answers.append(analyze_proxy(proxy, None, grain_lag_ratio(full, step)))
    base = answers[0]["sky_sigma"]
    assert base > 0
    for step, a in zip((1, 2, 3, 4), answers, strict=True):
        assert a["sky_sigma"] == pytest.approx(base, rel=0.05), (step, a)
        assert a["noisy"] is answers[0]["noisy"], (step, a)
        assert _noise_fraction(a["sky_sigma"]) == pytest.approx(
            _noise_fraction(base), abs=0.02), (step, a)


def test_auto_recipe_denoise_and_sharpen_stop_moving_with_the_stride():
    """What the user sees: the one-click op list, not the cue behind it. Both
    halves of the crossfade are corrected — the weight *and* the strength the
    measured-noise suggestion picks — or they disagree about which grid they are
    on."""
    full = _stacked_scene()

    def params(step: int, *, corrected: bool) -> dict[str, dict]:
        proxy = full[::step, ::step]
        ratio = grain_lag_ratio(full, step) if corrected else None
        recipe = auto_recipe(proxy, median_fwhm=3.0, grain_ratio=ratio)
        return {op.id: op.params for op in recipe.ops}

    at_1 = params(1, corrected=True)
    for step in (2, 3, 4):
        at_n = params(step, corrected=True)
        assert set(at_n) == set(at_1), (step, sorted(at_n), sorted(at_1))
        for op_id in ("detail.denoise", "detail.sharpen", "detail.chroma_denoise"):
            if op_id in at_1:
                for key, want in at_1[op_id].items():
                    if isinstance(want, (int, float)):
                        assert at_n[op_id][key] == pytest.approx(want, abs=0.05), \
                            (step, op_id, key, at_n[op_id][key], want)

    # ... and uncorrected it does move, which is the bug this pins: at step 3 the
    # same pixels buy roughly three times the denoise and a third of the sharpen.
    uncorrected = params(3, corrected=False)
    assert (uncorrected["detail.denoise"]["strength"]
            > at_1["detail.denoise"]["strength"] * 2.5), (uncorrected, at_1)
    assert (uncorrected["detail.sharpen"]["amount"]
            < at_1["detail.sharpen"]["amount"] * 0.6), (uncorrected, at_1)


def test_denoise_suggestion_takes_the_same_stride_correction():
    """``_SIGMA_FULL`` is a full-resolution bar, so the "From your image" strength
    has to be put back on that grid too."""
    full = _stacked_scene()
    sigma_full, strength_full = suggest_denoise_strength(full)
    proxy = full[::3, ::3]
    raw_sigma, _raw_strength = suggest_denoise_strength(proxy)
    fixed_sigma, fixed_strength = suggest_denoise_strength(
        proxy, grain_lag_ratio(full, 3))
    assert raw_sigma > sigma_full * 1.4                      # the premise
    assert fixed_sigma == pytest.approx(sigma_full, rel=0.05)
    assert fixed_strength == pytest.approx(strength_full, abs=0.05)


# --- the two properties that make it a correction, not a tuning --------------

def test_white_noise_needs_no_stride_correction():
    """The control. Uncorrelated grain reads the same σ at every separation, so
    the ratio is 1 and nothing moves — exactly the images that were right."""
    full = _stacked_scene(corr_px=0.0)
    for step in (2, 3, 4):
        assert grain_lag_ratio(full, step) == pytest.approx(1.0, abs=0.02), step
        assert (analyze_proxy(full[::step, ::step], None,
                              grain_lag_ratio(full, step))["sky_sigma"]
                == pytest.approx(analyze_proxy(full[::step, ::step])["sky_sigma"],
                                 rel=0.02)), step


def test_an_undecimated_proxy_is_left_exactly_where_it_was():
    """A single-field stack small enough to need no decimation gets ``1.0``
    without any measurement at all — the §9 promise that a running install's
    one-click Auto is byte-for-byte unchanged where it was already right."""
    full = _stacked_scene(h=600, w=600)
    assert grain_lag_ratio(full, 1) == 1.0
    assert grain_lag_ratio(full, 0) == 1.0
    assert source_grain_ratio("/definitely/not/a/file.fits", 1) == 1.0
    before = analyze_proxy(full)
    assert analyze_proxy(full, None, 1.0) == before
    assert analyze_proxy(full, None, None) == before
    # (op ``uid``s are freshly generated per build, so compare what the recipe
    # *says*, not its identity.)
    def shape(recipe):
        return [(op.id, op.params) for op in recipe.ops]

    assert shape(auto_recipe(full, median_fwhm=3.0)) == \
        shape(auto_recipe(full, median_fwhm=3.0, grain_ratio=1.0))
    assert shape(auto_recipe(full, median_fwhm=3.0)) == \
        shape(auto_recipe(full, median_fwhm=3.0, grain_ratio=None))


def test_the_ratio_is_never_allowed_above_one_or_absurdly_low():
    """It is a correction *downwards* by construction (correlation can only
    shrink the short-lag difference), and the floor is a rail against a window
    that is all structure rather than sky."""
    full = _stacked_scene()
    for step in (2, 3, 4, 8):
        r = grain_lag_ratio(full, step)
        assert 0.25 <= r <= 1.0, (step, r)


def test_unmeasurable_pixels_decline_rather_than_guess():
    flat = np.zeros((200, 200, 3), dtype=np.float32)
    assert grain_lag_ratio(flat, 3) is None
    assert estimate_noise_sigma(flat) is None
    tiny = np.zeros((4, 4, 3), dtype=np.float32)
    assert grain_lag_ratio(tiny, 3) is None


# --- reading the un-strided pixels off the master ----------------------------

def test_source_grain_ratio_recovers_the_full_resolution_reading(tmp_path):
    """End to end through the file: the factor comes from windowed reads of the
    master (never the canvas), and applying it to the *strided* proxy's σ returns
    the number a full-resolution read gives."""
    full = _stacked_scene()
    path = _write_master(tmp_path / "stack.fits", full)
    want = analyze_proxy(full)["sky_sigma"]
    for step in (2, 3, 4):
        ratio = source_grain_ratio(path, step)
        assert 0.4 < ratio < 0.85, (step, ratio)
        got = analyze_proxy(full[::step, ::step], None, ratio)["sky_sigma"]
        assert got == pytest.approx(want, rel=0.06), (step, got, want)


def test_source_grain_ratio_survives_a_mosaic_canvas_full_of_gaps(tmp_path):
    """The owner's shape: NaN is "no coverage", and a union canvas is ragged. A
    window that is mostly gap is skipped and the rest answer — the measurement
    must not come back ``None`` just because the corners are empty."""
    full = _stacked_scene()
    full[:260, :] = np.nan
    full[-260:, :] = np.nan
    full[:, :260] = np.nan
    full[:, -260:] = np.nan
    path = _write_master(tmp_path / "mosaic.fits", full)
    ratio = source_grain_ratio(path, 3)
    assert ratio is not None and 0.4 < ratio < 0.85, ratio
    got = analyze_proxy(full[::3, ::3], None, ratio)["sky_sigma"]
    assert got == pytest.approx(analyze_proxy(full)["sky_sigma"], rel=0.08), got


def test_source_grain_ratio_declines_on_an_unreadable_or_tiny_master(tmp_path):
    """No correction beats a wrong one: every failure path returns ``None``, and
    ``analyze_proxy`` then reports exactly today's number."""
    assert source_grain_ratio(tmp_path / "missing.fits", 3) is None
    small = _write_master(tmp_path / "small.fits", _stacked_scene(h=48, w=48))
    assert source_grain_ratio(small, 3) is None
    (tmp_path / "junk.fits").write_bytes(b"not a fits file")
    assert source_grain_ratio(tmp_path / "junk.fits", 3) is None


def test_source_grain_ratio_reads_windows_not_the_canvas(tmp_path, monkeypatch):
    """Cost is the point of the windowed read: a 150 MP mosaic must not be
    materialised to answer a question about its first few pixels."""
    from seestack.edit import proxy as proxy_mod

    full = _stacked_scene()
    path = _write_master(tmp_path / "stack.fits", full)

    def _no(*_a, **_k):  # pragma: no cover - fails the test if reached
        raise AssertionError("source_grain_ratio loaded the whole canvas")

    monkeypatch.setattr(proxy_mod, "_load_fits_rgb", _no)
    reads: list[tuple[int, int]] = []
    real_window = proxy_mod.read_window_rgb

    def _spy(fits_path, y0, x0, height, width):
        reads.append((height, width))
        return real_window(fits_path, y0, x0, height, width)

    monkeypatch.setattr(proxy_mod, "read_window_rgb", _spy)
    assert proxy_mod.source_grain_ratio(path, 3) is not None
    assert reads and all(h <= 512 and w <= 512 for h, w in reads), reads


# --- the factor is memoized where proxy_scale is ----------------------------

def test_the_grain_ratio_is_measured_once_per_run_and_cached(tmp_path, monkeypatch):
    """Both Auto endpoints ask on every click, and the answer cannot change while
    the master doesn't — so it is memoized in the proxy's own sidecar. Without
    that the ~0.4 s of windowed reads landed on the editor's main button twice
    per click."""
    from seestack.edit import proxy as proxy_mod

    full = _stacked_scene(h=1600, w=400)
    path = _write_master(tmp_path / "stack.fits", full)
    project = tmp_path / "project"
    _rgb, scale = proxy_mod.get_proxy(project, 7, path)
    step = int(round(scale))
    assert step == 2, scale

    first = proxy_mod.cached_source_grain_ratio(project, 7, path, step)
    assert first is not None and 0.4 < first < 0.85, first

    calls: list[int] = []
    real = proxy_mod.source_grain_ratio

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(proxy_mod, "source_grain_ratio", spy)
    again = proxy_mod.cached_source_grain_ratio(project, 7, path, step)
    assert again == first
    assert calls == [], "the cached factor was re-measured off the file"

    # A re-stack rewrites the master, and the sidecar is keyed on its mtime
    # exactly as the proxy is — so the stale answer is never served.
    os.utime(path, (0, 0))
    proxy_mod.get_proxy(project, 7, path)
    assert proxy_mod.cached_source_grain_ratio(project, 7, path, step) is not None
    assert calls == [1]


def test_the_grain_ratio_still_answers_without_a_sidecar(tmp_path):
    """The cache is an optimisation, never a precondition: with no proxy cached
    (and with an unwritable sidecar) the factor is simply measured."""
    from seestack.edit import proxy as proxy_mod

    full = _stacked_scene(h=1600, w=400)
    path = _write_master(tmp_path / "stack.fits", full)
    ratio = proxy_mod.cached_source_grain_ratio(tmp_path / "nothing-here", 1,
                                                path, 2)
    assert ratio is not None and 0.4 < ratio < 0.85, ratio
