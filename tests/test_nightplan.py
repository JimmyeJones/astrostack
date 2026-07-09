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
    HorizonProfile,
    LibraryTarget,
    Observer,
    load_catalog,
    moon_illumination,
    moon_is_waxing,
    plan_tonight,
)

# A clear January evening in London — Orion season, small waning Moon.
LONDON = Observer(lat_deg=51.5, lon_deg=-0.13, elevation_m=30.0)
JAN_EVENING = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)


def _transit_altitude(lat_deg: float, dec_deg: float) -> float:
    """Geometric upper-culmination altitude of a target at a given latitude."""
    return 90.0 - abs(lat_deg - dec_deg)


# The 88 canonical IAU three-letter constellation abbreviations. A catalog entry
# whose ``con`` isn't in here is a typo (and would render as junk in the UI).
_IAU_CONSTELLATIONS = {
    "And", "Ant", "Aps", "Aqr", "Aql", "Ara", "Ari", "Aur", "Boo", "Cae", "Cam",
    "Cnc", "CVn", "CMa", "CMi", "Cap", "Car", "Cas", "Cen", "Cep", "Cet", "Cha",
    "Cir", "Col", "Com", "CrA", "CrB", "Crv", "Crt", "Cru", "Cyg", "Del", "Dor",
    "Dra", "Equ", "Eri", "For", "Gem", "Gru", "Her", "Hor", "Hya", "Hyi", "Ind",
    "Lac", "Leo", "LMi", "Lep", "Lib", "Lup", "Lyn", "Lyr", "Men", "Mic", "Mon",
    "Mus", "Nor", "Oct", "Oph", "Ori", "Pav", "Peg", "Per", "Phe", "Pic", "Psc",
    "PsA", "Pup", "Pyx", "Ret", "Sge", "Sgr", "Sco", "Scl", "Sct", "Ser", "Sex",
    "Tau", "Tel", "Tri", "TrA", "Tuc", "UMa", "UMi", "Vel", "Vir", "Vol", "Vul",
}

# Types the planner/UI understand (shared with the Messier catalog vocabulary).
_KNOWN_TYPES = {
    "asterism", "double star", "galaxy", "globular cluster", "nebula",
    "open cluster", "planetary nebula", "star cloud", "supernova remnant",
}


def test_catalog_loads_messier_plus_curated_extras():
    cat = load_catalog()
    ids = {o.id for o in cat}
    # The full Messier catalog is still present and canonical.
    messier = [o for o in cat if o.id.startswith("M") and o.id[1:].isdigit()]
    assert len(messier) == 110
    assert "M1" in ids and "M42" in ids and "M110" in ids
    m42 = next(o for o in cat if o.id == "M42")
    assert m42.name == "Orion Nebula"
    # The curated non-Messier set widens the catalog with popular NGC/IC targets.
    assert len(cat) > 110
    for expected in ("NGC 7000", "NGC 869", "NGC 6960", "NGC 7293", "IC 1805"):
        assert expected in ids, expected
    # Every coordinate is sane across the whole combined catalog.
    for o in cat:
        assert 0.0 <= o.ra_deg < 360.0
        assert -90.0 <= o.dec_deg <= 90.0


def test_curated_catalog_is_well_formed_and_disjoint_from_messier():
    """The bundled non-Messier file has unique, valid, non-duplicating entries."""
    cat = load_catalog()
    extras = [o for o in cat if not (o.id.startswith("M") and o.id[1:].isdigit())]
    assert len(extras) >= 40  # a curated set worth having

    # Ids are unique across the whole catalog (the loader de-dups; verify no
    # accidental Messier/NGC id collision slipped through).
    ids = [o.id for o in cat]
    assert len(ids) == len(set(ids))

    for o in extras:
        assert o.id.startswith(("NGC ", "IC ")), o.id
        assert o.name, o.id  # every curated target carries a recognisable name
        assert o.type in _KNOWN_TYPES, (o.id, o.type)
        assert o.con in _IAU_CONSTELLATIONS, (o.id, o.con)

    # No curated object sits on top of a Messier object (they should be a genuine
    # widening, not a rename) — nothing closer than 0.2° to any Messier entry.
    messier = [o for o in cat if o.id.startswith("M") and o.id[1:].isdigit()]
    for e in extras:
        for m in messier:
            assert np_plan._angular_sep_deg(e.ra_deg, e.dec_deg,
                                            m.ra_deg, m.dec_deg) > 0.2, (e.id, m.id)


def test_curated_extras_appear_in_a_plan():
    """A widely-observable curated target surfaces as a not-yet-targeted entry."""
    # The Double Cluster (Dec +57°) is well up from London in January — it should
    # show up in the ranked plan as a catalog suggestion.
    plan = plan_tonight(LONDON, JAN_EVENING)
    by_id = {t.id: t for t in plan.targets}
    assert "NGC 869" in by_id
    dbl = by_id["NGC 869"]
    assert dbl.already_targeted is False
    assert dbl.name == "Double Cluster"
    assert dbl.max_altitude_deg > 30.0  # genuinely up that night


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


def test_high_min_altitude_does_not_crash_the_score():
    # Regression: the score's altitude term divided by ``70 - min_alt``. With a
    # ``min_altitude_deg`` of 70 (a legal Settings/query value, ge=0 le=80) and a
    # target that transits above 70°, that denominator was zero → ZeroDivisionError
    # → 500 on GET /api/plan/tonight?min_alt=70. A target near the zenith is common
    # (dec ≈ observer latitude), so this was reachable.
    high = LibraryTarget(safe="high", name="High", ra_deg=90.0, dec_deg=51.5,
                         frames_accepted=0, total_exposure_s=0.0)
    for min_alt in (70.0, 80.0):
        plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[high],
                            include_catalog=False, min_altitude_deg=min_alt)
        entry = next(p for p in plan.targets if p.id == "high")
        # It clears the floor near the zenith, so it should score above zero, and
        # the altitude term saturates to "plenty high" rather than blowing up.
        assert entry.max_altitude_deg > min_alt
        assert entry.score > 0.0


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


def test_moon_waxing_matches_the_phase_cycle():
    # Waning crescent a few days before the ~2026-01-18 new Moon.
    assert moon_is_waxing(JAN_EVENING) is False
    # Just after new Moon (2026-01-20) the Moon is growing again.
    assert moon_is_waxing(datetime(2026, 1, 20, 22, 0, tzinfo=timezone.utc)) is True
    # Rising toward the ~2026-02-01 full Moon — still waxing.
    assert moon_is_waxing(datetime(2026, 1, 25, 22, 0, tzinfo=timezone.utc)) is True
    # A day past the ~2026-01-03 full Moon — waning.
    assert moon_is_waxing(datetime(2026, 1, 4, 22, 0, tzinfo=timezone.utc)) is False


def test_plan_reports_moon_waxing_state():
    plan = plan_tonight(LONDON, JAN_EVENING)
    # The plan carries the same waxing verdict the standalone helper computes, so
    # the UI can label it "Waning crescent" rather than a bare "Crescent".
    assert plan.moon_waxing is moon_is_waxing(JAN_EVENING)
    assert plan.moon_waxing is False


def test_plan_is_deterministic():
    a = plan_tonight(LONDON, JAN_EVENING)
    b = plan_tonight(LONDON, JAN_EVENING)
    assert [(p.id, p.score, p.max_altitude_deg) for p in a.targets] == \
           [(p.id, p.score, p.max_altitude_deg) for p in b.targets]


def test_horizon_profile_from_pairs_sanitises_input():
    # Malformed / non-finite / short entries are dropped; azimuth wraps into
    # [0, 360); altitude clamps into [0, 90]; a repeated azimuth keeps the taller
    # obstruction; the survivors come out sorted by azimuth.
    prof = HorizonProfile.from_pairs([
        [370.0, 15.0],     # az wraps to 10
        ["x", "y"],        # non-numeric → dropped
        [90.0],            # too short → dropped
        [45.0, 200.0],     # alt clamps to 90
        [45.0, 30.0],      # same az → keep the taller (90)
        [180.0, -5.0],     # alt clamps to 0
        None,              # not a pair → dropped
    ])
    assert prof.points == ((10.0, 15.0), (45.0, 90.0), (180.0, 0.0))
    assert not prof.is_empty()
    assert HorizonProfile.from_pairs([]).is_empty()
    assert HorizonProfile.from_pairs(None).is_empty()


def test_horizon_profile_interpolates_with_wraparound():
    prof = HorizonProfile.from_pairs([[0.0, 10.0], [180.0, 40.0]])
    # Exact points, the linear midpoint, and the wrap-around seam (180→360≡0).
    assert float(prof.altitude_at(0.0)) == pytest.approx(10.0)
    assert float(prof.altitude_at(180.0)) == pytest.approx(40.0)
    assert float(prof.altitude_at(90.0)) == pytest.approx(25.0)
    assert float(prof.altitude_at(270.0)) == pytest.approx(25.0)
    # Empty profile blocks nothing (0° everywhere), array in / array out.
    empty = HorizonProfile.from_pairs([])
    assert list(empty.altitude_at([12.0, 200.0])) == [0.0, 0.0]


# Orion transits around 33° from London — high enough to clear a 20° floor for
# hours, but a wall raised above its peak hides it entirely.
_M42 = LibraryTarget(safe="M42", name="Orion Nebula", ra_deg=83.82, dec_deg=-5.39,
                     frames_accepted=1, total_exposure_s=1.0)


def _m42_entry(horizon, min_alt=20.0):
    plan = plan_tonight(LONDON, JAN_EVENING, library_targets=[_M42],
                        include_catalog=False, min_altitude_deg=min_alt,
                        horizon=horizon)
    return plan, next(p for p in plan.targets if p.id == "M42")


def test_empty_horizon_matches_no_horizon():
    # An empty / absent mask must leave the plan byte-for-byte unchanged.
    base_plan, base = _m42_entry(None)
    empty_plan, empty = _m42_entry(HorizonProfile.from_pairs([]))
    assert base_plan.horizon_active is False
    assert empty_plan.horizon_active is False
    assert (empty.minutes_above_min_alt, empty.score, empty.max_altitude_deg) == \
           (base.minutes_above_min_alt, base.score, base.max_altitude_deg)


def test_horizon_below_min_altitude_changes_nothing():
    # A wall lower than the numeric min-altitude floor is subsumed by it.
    _, base = _m42_entry(None)
    plan, low = _m42_entry(HorizonProfile.from_pairs([[0.0, 10.0]]))
    assert plan.horizon_active is True  # a mask *is* set …
    # … but it doesn't touch a target that already clears the min-altitude floor.
    assert low.minutes_above_min_alt == base.minutes_above_min_alt
    assert low.score == base.score


def test_horizon_wall_trims_usable_window_and_score():
    # A 30° wall (above the 20° floor, below Orion's ~33° peak) leaves only the
    # slice of the night Orion spends above 30° — fewer minutes, lower score,
    # but the honest physical peak altitude is unchanged.
    _, base = _m42_entry(None)
    _, walled = _m42_entry(HorizonProfile.from_pairs([[0.0, 30.0]]))
    assert walled.max_altitude_deg == base.max_altitude_deg
    assert 0.0 < walled.minutes_above_min_alt < base.minutes_above_min_alt
    assert 0.0 < walled.score < base.score
    assert walled.transit_utc is not None


def test_horizon_wall_above_peak_hides_target():
    # A 40° wall everywhere is above Orion's transit, so it never clears the
    # trees tonight: no usable window, no transit, score 0.
    plan, hidden = _m42_entry(HorizonProfile.from_pairs([[0.0, 40.0]]))
    assert plan.horizon_active is True
    assert hidden.minutes_above_min_alt == 0.0
    assert hidden.score == 0.0
    assert hidden.transit_utc is None
    assert hidden.max_altitude_deg == pytest.approx(33.1, abs=1.0)


def test_polar_day_returns_empty_plan_gracefully():
    svalbard = Observer(lat_deg=78.2, lon_deg=15.6, elevation_m=0.0)
    plan = plan_tonight(svalbard, datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc))
    assert plan.dark_window is None
    assert plan.targets == []
    # Still reports the Moon and observer so the UI can explain why it's empty.
    assert 0.0 <= plan.moon_illumination <= 1.0
    assert plan.observer["lat_deg"] == pytest.approx(78.2)
