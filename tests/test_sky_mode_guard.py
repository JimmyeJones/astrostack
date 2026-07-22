"""The SExtractor sky-mode fallback guard (defense-in-depth).

`seestack/bg/*` estimate the per-channel sky with the SExtractor mode
approximation ``mode = 2.5·median − 1.5·mean`` and are supposed to fall back to
the plain median when the tile is too crowded for the mode to be trustworthy.
The original guard (``abs(mode − median) > 5·abs(median − mean)``) was
algebraically inert — ``mode − median`` is *by construction* ``1.5·(median −
mean)``, so ``1.5·X > 5·X`` never fires — leaving no real backstop. The guard now
uses SExtractor's own criterion (mean−median within ``0.3·σ``). These tests pin
that it (a) stays a no-op on realistic clipped sky, so the shipped result is
unchanged, and (b) actually fires on a heavily-crowded tile.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.stats import sigma_clipped_stats  # noqa: E402

from seestack.bg.per_frame import _zero_sky_per_channel  # noqa: E402


def _subtracted_sky(population: np.ndarray) -> float:
    """Run ``_zero_sky_per_channel`` on a single-channel population (broadcast to
    all three channels) and return the constant per-channel offset it subtracted."""
    ch = population.astype(np.float32)
    rgb = np.stack([ch, ch, ch], axis=-1).copy()
    before = float(rgb[0, 0, 0])
    _zero_sky_per_channel(rgb)
    after = float(rgb[0, 0, 0])
    return before - after


def _clipped(population: np.ndarray):
    mean, median, std = sigma_clipped_stats(
        population.astype(np.float32), sigma=3.0, maxiters=5
    )
    return float(mean), float(median), float(std)


def test_realistic_sky_still_uses_the_mode_not_a_blanket_median():
    """Parity: on realistic clipped sky the 3σ-clip keeps mean−median well inside
    0.3·σ, so the guard does NOT fire and the subtracted sky is the mode — exactly
    what shipped before the guard was made functional (a no-op on the default
    path)."""
    rng = np.random.default_rng(3)
    sky = rng.normal(1000.0, 15.0, size=(200, 200)).astype(np.float32)
    mean, median, std = _clipped(sky)
    assert abs(mean - median) <= 0.3 * std  # precondition: guard must not fire
    expected_mode = 2.5 * median - 1.5 * mean
    subtracted = _subtracted_sky(sky)
    # The mode is used (matches the pre-guard behaviour byte-for-byte), and it is
    # distinguishable from a plain-median fallback.
    assert subtracted == pytest.approx(expected_mode, abs=1e-3)
    assert abs(subtracted - median) == pytest.approx(abs(expected_mode - median), abs=1e-3)


def test_symmetric_sky_mode_collapses_to_median():
    """On a symmetric histogram mean≈median, so mode≈median and the sky is stable
    either way — the guard leaves it as the mode (≈ median)."""
    rng = np.random.default_rng(5)
    sym = rng.normal(500.0, 20.0, size=(200, 200)).astype(np.float32)
    mean, median, std = _clipped(sym)
    assert abs(mean - median) <= 0.3 * std
    subtracted = _subtracted_sky(sym)
    assert subtracted == pytest.approx(median, abs=0.3)


def test_heavily_crowded_tile_falls_back_to_the_median():
    """A tile dominated by bright object flux (here 35 % of pixels lifted well
    above sky, surviving the 3σ clip) pushes mean−median past 0.3·σ. The old inert
    guard would have kept the badly-biased mode; the functional guard falls back to
    the median."""
    rng = np.random.default_rng(5)
    n = 200 * 200
    crowded = np.where(rng.random(n) < 0.35, 3.0, 0.0) + rng.normal(0.0, 0.3, n)
    crowded = crowded.reshape(200, 200).astype(np.float32)
    mean, median, std = _clipped(crowded)
    assert abs(mean - median) > 0.3 * std  # precondition: this tile IS crowded
    mode = 2.5 * median - 1.5 * mean
    # The mode is meaningfully wrong here (far from the median sky), so the choice
    # is observable...
    assert abs(mode - median) > 0.05
    subtracted = _subtracted_sky(crowded)
    # ...and the guard picks the median, not the biased mode.
    assert subtracted == pytest.approx(median, abs=1e-3)
    assert abs(subtracted - mode) > 0.05


def test_flat_channel_is_a_noop():
    """A perfectly flat channel (std 0) must not fire the guard's std>0 gate and
    subtracts its constant level cleanly."""
    flat = np.full((64, 64), 7.0, dtype=np.float32)
    subtracted = _subtracted_sky(flat)
    assert subtracted == pytest.approx(7.0, abs=1e-4)
