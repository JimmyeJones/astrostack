"""Unit tests for the shared RA-wrap helpers (seestack/coords.py).

These pin the 0°/360° boundary behaviour that three call sites
(stack/mosaic.py, stack/reference.py, io/library.py) now share, so a future
fourth site — or a regression in the helper — is caught in one place.
"""

import numpy as np
import pytest

from seestack.coords import circular_median_ra_deg, unwrap_ra_deg


def test_no_wrap_is_identity():
    ras = [10.0, 12.0, 11.0, 9.5]
    out = unwrap_ra_deg(ras)
    assert np.allclose(out, ras)


def test_straddling_zero_is_made_continuous():
    # Some frames at ~359.9°, some at ~0.1° — apparent spread ~359.8° > 180.
    ras = [359.9, 0.1, 359.8, 0.2]
    out = unwrap_ra_deg(ras)
    # High side shifted below zero → one continuous run around 0.
    assert out.max() - out.min() < 1.0
    assert np.isclose(out[0], -0.1)  # 359.9 → -0.1
    assert np.isclose(out[1], 0.1)


def test_wide_but_not_wrapped_span_left_alone():
    # A genuinely spread-out mosaic spanning <180° must not be shifted.
    ras = [10.0, 170.0, 90.0]
    out = unwrap_ra_deg(ras)
    assert np.allclose(out, ras)


def test_empty_input_is_empty():
    out = unwrap_ra_deg([])
    assert isinstance(out, np.ndarray)
    assert out.size == 0


def test_circular_median_folds_back_across_wrap():
    # 359.9/0.1/359.8/0.2 median should be ~0.0, not ~180.
    med = circular_median_ra_deg([359.9, 0.1, 359.8, 0.2])
    # Fold into [-180, 180) for the "near 0" assertion.
    assert min(med, 360.0 - med) < 0.3


def test_circular_median_no_wrap_is_plain_median():
    ras = [100.0, 101.0, 99.0, 100.5]
    assert circular_median_ra_deg(ras) == pytest.approx(float(np.median(ras)))


def test_circular_median_stays_in_0_360():
    med = circular_median_ra_deg([359.95, 0.05])
    assert 0.0 <= med < 360.0
