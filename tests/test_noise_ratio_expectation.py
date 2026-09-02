"""Is a measured noise reduction *good*? The √N yardstick the reveal card reads.

The "One frame vs your stack" card now says what a stack's frame count should
have bought (``noiseVsExpectedNote`` in ``frontend/src/components/oneFrameVsStack.ts``),
and nudges when the measurement lands below ``NOISE_EXPECTED_LOW_FRACTION`` (0.7)
of √N. That threshold is a claim about *this* estimator's behaviour on real
stacking, so it is pinned here rather than only in the copy that quotes it:

* an **ideal** mean stack of independent-noise subs must read ~1.00·√N — if the
  estimator were biased low on healthy data the nudge would fire on good stacks;
* a **weighted** mean reads lower *honestly* (its effective frame count really
  is smaller), and must still sit far above 0.7;
* a stack whose subs share **correlated** noise — the shape soft alignment, a
  drifting gradient or a duplicated sub produces — must fall below 0.7, which is
  the case the nudge exists to catch.

These run the real averaging (not a simulated single frame at σ/√N), over a
scene with sky gradient, stars and a bright extended object, so they also
exercise the estimator's object rejection.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.qc.noise_ratio import noise_ratio

# Mirrors NOISE_EXPECTED_LOW_FRACTION in oneFrameVsStack.ts. A stack measuring
# below this share of √N is what the card calls "came in nearer …".
LOW_FRACTION = 0.7

SHAPE = (320, 320)
SIGMA = 0.02


def _scene(seed: int) -> np.ndarray:
    """A linear frame: sky with a gradient, a bright extended object, stars."""
    rng = np.random.default_rng(seed)
    h, w = SHAPE
    yy, xx = np.mgrid[0:h, 0:w]
    img = 0.10 + 0.004 * (xx / w) + 0.003 * (yy / h)
    img = img + 0.08 * np.exp(-(((xx - w // 2) ** 2 + (yy - h // 2) ** 2)
                                / (2 * 35.0 ** 2)))
    for _ in range(50):
        y = int(rng.integers(0, h))
        x = int(rng.integers(0, w))
        img[max(0, y - 2):y + 3, max(0, x - 2):x + 3] += rng.uniform(0.05, 0.5)
    return img.astype(np.float32)


def _measure(sub: np.ndarray, stack: np.ndarray) -> float:
    ratio = noise_ratio(np.stack([sub] * 3, axis=-1), np.stack([stack] * 3, axis=-1))
    assert ratio is not None
    return ratio


def _stack(base: np.ndarray, n: int, *, seed: int,
           shared_var: float = 0.0,
           weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """One sub and the stack of ``n`` of them.

    ``shared_var`` is the fraction of each sub's noise variance that is *common*
    to every sub — averaging cannot reduce it, so it is how an underperforming
    stack is modelled.
    """
    rng = np.random.default_rng(seed)
    shared = rng.normal(0.0, SIGMA * np.sqrt(shared_var), SHAPE).astype(np.float32)
    indep = SIGMA * np.sqrt(1.0 - shared_var)
    subs = np.stack([
        base + shared + rng.normal(0.0, indep, SHAPE).astype(np.float32)
        for _ in range(n)
    ])
    if weights is None:
        stack = subs.mean(axis=0)
    else:
        w = np.asarray(weights, dtype=np.float32)[:, None, None]
        stack = (subs * w).sum(axis=0) / w.sum()
    return subs[0], stack.astype(np.float32)


@pytest.mark.parametrize("n", [12, 25, 100])
def test_healthy_stack_reads_as_expected(n: int) -> None:
    """An ideal mean stack measures ~1.00·√N, comfortably clear of the nudge."""
    base = _scene(seed=3)
    sub, stack = _stack(base, n, seed=100 + n)
    share = _measure(sub, stack) / np.sqrt(n)
    assert share == pytest.approx(1.0, abs=0.05)
    assert share > LOW_FRACTION


def test_quality_weighting_stays_well_above_the_nudge() -> None:
    """Weights as spread as U(0.1, 1) lower the *effective* frame count — and the
    measurement follows that honestly, landing near the theoretical prediction
    and still far above the threshold. This is the false-alarm case that matters:
    the walk-away path turns quality weighting on by default."""
    n = 60
    base = _scene(seed=4)
    w = np.random.default_rng(9).uniform(0.1, 1.0, n)
    effective_n = float(w.sum() ** 2 / (w ** 2).sum())
    sub, stack = _stack(base, n, seed=77, weights=w)
    share = _measure(sub, stack) / np.sqrt(n)
    # The honest prediction for a weighted mean, and the measurement agrees.
    assert share == pytest.approx(np.sqrt(effective_n / n), abs=0.05)
    assert share > LOW_FRACTION + 0.15


@pytest.mark.parametrize("n,shared_var", [(100, 0.02), (100, 0.10)])
def test_correlated_subs_fall_below_the_nudge(n: int, shared_var: float) -> None:
    """Noise the subs share cannot be averaged away, so the stack lands well
    under √N — the underperforming case the card nudges about."""
    base = _scene(seed=5)
    sub, stack = _stack(base, n, seed=200, shared_var=shared_var)
    share = _measure(sub, stack) / np.sqrt(n)
    assert share < LOW_FRACTION
