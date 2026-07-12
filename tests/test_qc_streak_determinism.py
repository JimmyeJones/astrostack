"""The streak detector must be deterministic.

``detect_streaks`` fits line segments with ``probabilistic_hough_line``, a
Monte-Carlo transform. Without a fixed seed it returns a different segment count
run-to-run, and ``streak_count`` is written to the project DB — so re-running QC
on the same frame would store a different value each time (breaking the QC
idempotency contract) and, on a marginal streak, could even flip the
reject-driving ``streak_detected`` boolean. This pins determinism.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("skimage")

from seestack.qc.streaks import detect_streaks


def _frame_with_streak() -> np.ndarray:
    """A frame with a long, bright, elongated streak that lands in the
    Monte-Carlo-sensitive regime (the unseeded Hough count varies for it)."""
    rng = np.random.default_rng(1)
    img = rng.normal(100.0, 5.0, (540, 960)).astype(np.float32)
    for i in range(300):
        x = 150 + i
        y = 120 + i // 3
        img[y, x] = 950.0
        img[y + 1, x] = 950.0
    return img


def test_detect_streaks_is_deterministic():
    img = _frame_with_streak()
    results = [detect_streaks(img, sky_median=100.0, sky_std=5.0) for _ in range(8)]
    # Every repeat must agree — no run-to-run drift in the stored count.
    assert len(set(results)) == 1, f"non-deterministic streak detection: {results}"
    detected, count = results[0]
    # Sanity: the Monte-Carlo path is actually exercised (a streak is found),
    # so the test would catch an unseeded regression rather than trivially pass.
    assert detected is True
    assert count > 0
