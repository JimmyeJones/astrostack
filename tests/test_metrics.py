"""QC metrics — star detection, FWHM, sky background, eccentricity, streaks."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("skimage")

from seestack.qc.metrics import (  # noqa: E402
    compute_frame_metrics,
    detect_stars,
    estimate_sky,
    green_channel,
    median_eccentricity,
    median_fwhm,
)
from tests.synth import make_star_field, write_seestar_fits  # noqa: E402


def test_green_channel_shape():
    mosaic = np.zeros((40, 60), dtype=np.float32)
    g = green_channel(mosaic, pattern="RGGB")
    assert g.shape == (20, 30)


def test_estimate_sky_recovers_level():
    rng = np.random.default_rng(1)
    img = rng.normal(loc=1500.0, scale=20.0, size=(200, 300)).astype(np.float32)
    med, std = estimate_sky(img)
    assert abs(med - 1500.0) < 5.0
    assert 15 < std < 25


def test_full_qc_on_synthetic(tmp_path):
    p = write_seestar_fits(tmp_path / "good.fit", n_stars=60, seed=7)
    m = compute_frame_metrics(p, detect_streaks=False)
    # Synthetic field has 60 stars; detection on the green channel should find
    # a healthy fraction.
    assert m.star_count >= 30
    # Sky level was 1000 with ~50 noise; sigma-clipped median is close to 1000.
    assert 900 < m.sky_adu_median < 1100
    # Synthetic FWHM is 4 px on the *full* mosaic, so on the half-res green
    # channel it's ~2 px. Allow a wide window for fitter noise.
    assert m.fwhm_px is not None and 1.0 < m.fwhm_px < 4.0
    # Stars are round, so eccentricity should be modest.
    assert m.eccentricity_median is not None and m.eccentricity_median < 0.6


def test_streak_detection_on_streaked_frame(tmp_path):
    # Frame with a diagonal streak
    p_streak = write_seestar_fits(tmp_path / "streak.fit", seed=3, streak=True)
    m_streak = compute_frame_metrics(p_streak)
    # Frame without
    p_clean = write_seestar_fits(tmp_path / "clean.fit", seed=4, streak=False)
    m_clean = compute_frame_metrics(p_clean)

    assert m_streak.streak_detected is True
    assert m_streak.streak_count >= 1
    assert m_clean.streak_detected is False


def test_detect_stars_returns_none_on_empty():
    img = np.full((100, 100), 1000.0, dtype=np.float32)
    sky_med, sky_std = estimate_sky(img)
    sources = detect_stars(img, sky_median=sky_med, sky_std=max(sky_std, 1.0))
    assert sources is None or len(sources) == 0
    assert median_fwhm(img, sources) is None
    assert median_eccentricity(sources) is None
