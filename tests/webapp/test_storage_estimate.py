"""Unit tests for the pure storage-headroom growth estimator."""

from __future__ import annotations

from webapp.storage_estimate import estimate_nightly_bytes


def test_median_frames_per_night_times_amortised_bytes():
    # 3 capture nights: 100, 50, 100 frames → median 100 frames/night.
    # Library = 250 frames occupying 500 MB → 2 MB amortised per frame.
    nights = {"2026-07-18": 100, "2026-07-19": 50, "2026-07-20": 100}
    rate = estimate_nightly_bytes(nights, total_library_bytes=500 * 1024**2,
                                  total_frames=250)
    assert rate is not None
    # median(100, 50, 100) = 100 frames/night × 2 MB/frame = 200 MB/night.
    assert round(rate) == 200 * 1024**2


def test_only_the_most_recent_nights_drive_the_rate():
    # Six nights, but the estimator windows to the recent few (default 7 keeps
    # all here) — median is robust to one small/cloudy night.
    nights = {
        "2026-07-15": 200, "2026-07-16": 200, "2026-07-17": 200,
        "2026-07-18": 200, "2026-07-19": 200, "2026-07-20": 10,
    }
    rate = estimate_nightly_bytes(nights, total_library_bytes=1010 * 1024**2,
                                  total_frames=1010, recent_nights=7)
    # median of [200,200,200,200,200,10] = 200 → the dud night doesn't drag it.
    assert rate is not None
    assert round(rate / 1024**2) == 200


def test_window_excludes_old_nights():
    # With recent_nights=2, only the two newest nights count.
    nights = {"2026-01-01": 1000, "2026-07-19": 30, "2026-07-20": 30}
    rate = estimate_nightly_bytes(nights, total_library_bytes=1060 * 1024**2,
                                  total_frames=1060, recent_nights=2)
    assert rate is not None
    # median(30, 30) = 30 frames/night, not pulled up by the ancient 1000-night.
    assert round(rate / 1024**2) == 30


def test_single_night_is_not_enough_history():
    assert estimate_nightly_bytes({"2026-07-20": 100},
                                  total_library_bytes=100 * 1024**2,
                                  total_frames=100) is None


def test_no_frames_or_bytes_returns_none():
    assert estimate_nightly_bytes({}, 0, 0) is None
    assert estimate_nightly_bytes({"2026-07-19": 5, "2026-07-20": 5},
                                  total_library_bytes=0, total_frames=10) is None
    assert estimate_nightly_bytes({"2026-07-19": 5, "2026-07-20": 5},
                                  total_library_bytes=1000, total_frames=0) is None
