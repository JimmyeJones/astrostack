"""Tests for the offline 'Tonight' night planner (``seestack.nightplan``).

Deterministic: fixed date + site → known altitude/window, so these pin the
astronomy, not a snapshot. Altitude tolerances allow for refraction and the
5-minute sampling grid.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from seestack import nightplan as np_plan
from seestack.nightplan import (
    LibraryTarget,
    Observer,
    load_catalog,
    moon_illumination,
    plan_tonight,
)

# A clear January evening in London — Orion season, small waning Moon.
LONDON = Observer(lat_deg=51.5, lon_deg=-0.13, elevation_m=30.0)
JAN_EVENING = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)


def _transit_altitude(lat_deg: float, dec_deg: float) -> float:
    """Geometric upper-culmination altitude of a target at a given latitude."""
    return 90.0 - abs(lat_deg - dec_deg)


def test_catalog_loads_full_messier():
    cat = load_catalog()
    assert len(cat) == 110
    ids = {o.id for o in cat}
    assert "M1" in ids and "M42" in ids and "M110" in ids
    m42 = next(o for o in cat if o.id == "M42")
    assert m42.name == "Orion Nebula"
    # Every coordinate is sane.
    for o in cat:
        assert 0.0 <= o.ra_deg < 360.0
        assert -90.0 <= o.dec_deg <= 90.0


def test_dark_window_is_astronomical_in_winter():
    plan = plan_tonight(LONDON, JAN_EVENING)
    dw = plan.dark_window
    assert dw is not None
    assert dw["sun_alt_threshold_deg"] == -18.0
    assert dw["start_utc"] < dw["end_utc"]
    # London mid-January astronomical night is roughly 11.5 h.
    assert 600.0 < dw["duration_minutes"] < 780.0


def test_high_latitude_summer_degrades_then_vanishes():
    # London midsummer: no −18 darkness, so it falls back to a shallower window.
    w = np_plan._find_dark_window(LONDON, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc))
    assert w is not None
    assert w.sun_alt_threshold_deg > -18.0
    # Svalbard midsummer: polar day, the Sun never sets → no window at all.
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    assert np_plan._find_dark_window(
        svalbard, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc)) is None


def test_transit_altitude_matches_geometry():
    # A library target whose transit falls inside the dark window: its max
    # altitude over the night must equal the geometric culmination altitude.
    m42 = LibraryTarget(safe="M42", name="Orion Nebula", ra_deg=83.82,
                        dec_deg=-5.39, frames_accepted=100, total_exposure_s=1000.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[m42])
    entry = next(p for p in plan.targets if p.id == "M42")
    expected = _transit_altitude(LONDON.lat_deg, m42.dec_deg)  # ≈ 33.1°
    assert abs(entry.max_altitude_deg - expected) < 1.0
    assert entry.already_targeted is True
    assert entry.transit_utc is not None


def test_library_target_dedupes_matching_catalog_object():
    m42 = LibraryTarget(safe="M42", name="Orion Nebula", ra_deg=83.82,
                        dec_deg=-5.39, frames_accepted=100, total_exposure_s=1000.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[m42])
    m42_entries = [p for p in plan.targets if abs(p.ra_deg - 83.82) < 0.5
                   and abs(p.dec_deg - (-5.39)) < 0.5]
    assert len(m42_entries) == 1
    assert m42_entries[0].already_targeted is True


def test_never_rising_target_scores_zero():
    # A deep-southern target can never clear 30° from London.
    south = LibraryTarget(safe="deep-south", name="Deep South", ra_deg=90.0,
                         dec_deg=-70.0, frames_accepted=0, total_exposure_s=0.0)
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[south],
                        include_catalog=False, min_altitude_deg=30.0)
    entry = next(p for p in plan.targets if p.id == "deep-south")
    assert entry.score == 0.0
    assert entry.minutes_above_min_alt == 0.0
    assert entry.transit_utc is None


def test_high_target_outranks_low_target():
    plan = plan_tonight(LONDON, JAN_EVENING)
    # Sorted best-first, and a near-zenith circumpolar target beats a low one.
    scores = [p.score for p in plan.targets]
    assert scores == sorted(scores, reverse=True)
    best = plan.targets[0]
    assert best.score > 50.0
    assert best.max_altitude_deg > 60.0


def test_moon_illumination_range_and_known_phase():
    illum = moon_illumination(JAN_EVENING)
    assert 0.0 <= illum <= 1.0
    # New Moon was ~2026-01-18, so a few days before it is a thin waning crescent.
    assert illum < 0.25
    # A full Moon (~2026-01-03) reads near-fully-lit.
    full = moon_illumination(datetime(2026, 1, 3, 22, 0, tzinfo=timezone.utc))
    assert full > 0.9


def test_plan_is_deterministic():
    a = plan_tonight(LONDON, JAN_EVENING)
    b = plan_tonight(LONDON, JAN_EVENING)
    assert [(p.id, p.score, p.max_altitude_deg) for p in a.targets] == \
           [(p.id, p.score, p.max_altitude_deg) for p in b.targets]


def test_polar_day_returns_empty_plan_gracefully():
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    plan = plan_tonight(svalbard, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc))
    assert plan.dark_window is None
    assert plan.targets == []
    # Still reports the Moon and observer so the UI can explain why it's empty.
    assert 0.0 <= plan.moon_illumination <= 1.0
    assert plan.observer["lat_deg"] == pytest.approx(78.2)
